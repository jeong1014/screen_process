"""
관리자 운영 — 出荷 / 印刷ジョブ / 連携エラーログ.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from db import db
from security import require_admin
from schemas import (
    ShipIn,
)

router = APIRouter()


# ---- 出荷 ----------------------------------------------------------------
@router.get("/api/admin/shipments")
def admin_shipments(_=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        cur.execute("""SELECT s.*, o.order_no, o.customer_name FROM shipments s
                       JOIN orders o ON o.id=s.order_id ORDER BY s.created_at DESC LIMIT 200""")
        rows = cur.fetchall()
    return [{"order_no": r["order_no"], "customer_name": r["customer_name"], "shipment_no": r["shipment_no"],
             "tracking_no": r["tracking_no"], "shipping_status": r["shipping_status"],
             "bizlogi_status": r["bizlogi_status"], "package_count": r["package_count"],
             "shipped_at": r["shipped_at"].strftime("%Y-%m-%d %H:%M") if r["shipped_at"] else None}
            for r in rows]


@router.post("/api/admin/shipments")
def admin_shipment_upsert(body: ShipIn, _=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM orders WHERE order_no=%s", (body.order_no,))
        o = cur.fetchone()
        if not o:
            raise HTTPException(404, "注文が見つかりません")
        cur.execute("SELECT id FROM shipments WHERE order_id=%s ORDER BY package_no LIMIT 1", (o["id"],))
        ex = cur.fetchone()
        if ex:
            _cast = {"shipping_status": "::shipping_status", "bizlogi_status": "::bizlogi_status"}
            sets, vals = [], []
            for k in ("tracking_no", "shipping_status", "bizlogi_status", "package_count"):
                v = getattr(body, k)
                if v is not None:
                    sets.append(f"{k}=%s{_cast.get(k, '')}"); vals.append(v)
            if sets:
                cur.execute(f"UPDATE shipments SET {', '.join(sets)} WHERE id=%s", vals + [ex["id"]])
        else:
            today = date.today().strftime("%Y%m%d")
            cur.execute("SELECT count(*) AS c FROM shipments WHERE shipment_no LIKE %s", (f"SHIP-{today}-%",))
            sno = f"SHIP-{today}-{cur.fetchone()['c']+1:04d}"
            cur.execute("""INSERT INTO shipments (order_id, shipment_no, tracking_no, shipping_status,
                             bizlogi_status, package_count)
                           VALUES (%s,%s,%s,COALESCE(%s::shipping_status,'ready'),
                                   COALESCE(%s::bizlogi_status,'not_requested'),COALESCE(%s,1))""",
                        (o["id"], sno, body.tracking_no, body.shipping_status, body.bizlogi_status, body.package_count))
        conn.commit()
    return {"ok": True}


# ---- 印刷 / 連携エラー ----------------------------------------------------
@router.get("/api/admin/prints")
def admin_prints(_=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        cur.execute("""SELECT p.*, o.order_no FROM print_jobs p LEFT JOIN orders o ON o.id=p.order_id
                       ORDER BY p.id DESC LIMIT 200""")
        rows = cur.fetchall()
    return [{"id": r["id"], "order_no": r["order_no"], "target": r["target_type"], "printer": r["printer_type"],
             "status": r["status"], "error": r["error_message"],
             "printed_at": r["printed_at"].strftime("%m/%d %H:%M") if r["printed_at"] else ""} for r in rows]


@router.get("/api/admin/sync-logs")
def admin_sync_logs(status: str = "failed", _=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        if status:
            cur.execute("""SELECT s.*, o.order_no FROM sync_logs s LEFT JOIN orders o ON o.id=s.order_id
                           WHERE s.status=%s ORDER BY s.created_at DESC LIMIT 200""", (status,))
        else:
            cur.execute("""SELECT s.*, o.order_no FROM sync_logs s LEFT JOIN orders o ON o.id=s.order_id
                           ORDER BY s.created_at DESC LIMIT 200""")
        rows = cur.fetchall()
    return [{"t": r["created_at"].strftime("%m/%d %H:%M"), "order_no": r["order_no"], "system": r["system"],
             "action": r["action"], "status": r["status"], "error": r["error_message"]} for r in rows]
