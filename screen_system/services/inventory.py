"""
QR在庫 v2 — 시리얼 QR 스캔 시 재고 차감.

QR発行 = 入庫(+1) / 같은 QR 스캔 = 消尽(-1).
이미 소진된 QR을 다시 스캔해도 이중 차감하지 않는다.
테이블: inv_item / inv_unit / inv_tx

라우트(POST /api/inventory/scan)와 시리얼 스캐너 스레드가 함께 쓰므로 서비스로 둔다.
"""

from db import db


def inv_scan(code: str, worker=None) -> dict:
    """QRシリアルをスキャン → 在庫-1・個体を消尽に。二重差引はしない。"""
    serial = (code or "").strip().upper()
    if not serial:
        return {"ok": False, "reason": "空のQR", "serial": serial}
    with db() as conn, conn.cursor() as cur:
        cur.execute("""WITH upd AS (
                          UPDATE inv_unit SET status='consumed', consumed_at=now(), worker=%s
                          WHERE serial=%s AND status='in_stock' RETURNING code
                        ), dec AS (
                          UPDATE inv_item SET remain = GREATEST(0, remain - 1)
                          WHERE code = (SELECT code FROM upd)
                          RETURNING code, remain, name, unit, reorder_point
                        )
                        SELECT code, remain, name, unit, reorder_point FROM dec""",
                    (worker, serial))
        row = cur.fetchone()
        if row:
            cur.execute("INSERT INTO inv_tx (code, serial, delta, reason, balance_after, worker) "
                        "VALUES (%s,%s,-1,'consume',%s,%s)", (row["code"], serial, row["remain"], worker))
            conn.commit()
            return {"ok": True, "serial": serial, "name": row["name"], "unit": row["unit"],
                    "balance": row["remain"], "low": row["remain"] <= row["reorder_point"]}
        cur.execute("SELECT status FROM inv_unit WHERE serial=%s", (serial,))
        u = cur.fetchone()
        conn.rollback()
    if u and u["status"] == "consumed":
        return {"ok": False, "reason": "既に消尽済みのQR(二重差引なし)", "serial": serial}
    return {"ok": False, "reason": "未登録のQR", "serial": serial}
