"""
관리자 발주(仕入れ) — 依頼 → 資材部へメール → 発注登録 → 入荷.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from db import db, _set_setting
from security import require_admin
from schemas import (
    PurchaseReqIn, PurchaseOrderIn, PurchaseSettingsIn,
)
from services.mailer import _smtp_config, _send_purchase_email

router = APIRouter()


@router.post("/api/admin/purchase")
def admin_purchase_create(body: PurchaseReqIn, _=Depends(require_admin)):
    """発注依頼を1件作成し、資材部へメール送信(設定済みの場合)。"""
    qty = max(1, int(body.qty or 1))
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT code, name, unit FROM inv_item WHERE code=%s AND active", (body.code,))
        it = cur.fetchone()
        if not it:
            raise HTTPException(404, f"品目が見つかりません: {body.code}")
        cur.execute("""INSERT INTO purchase_order (code, item_name, unit, qty, requested_by, req_note)
                       VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (it["code"], it["name"], it["unit"], qty, body.requested_by, body.note))
        po_id = cur.fetchone()["id"]
        cfg = _smtp_config(cur)
        subject = f"【発注依頼】{it['name']} を {qty}{it['unit']}"
        lines = [
            "発注依頼が届きました。",
            "",
            f"品目コード : {it['code']}",
            f"品名       : {it['name']}",
            f"必要数      : {qty} {it['unit']}",
            f"依頼者      : {body.requested_by or '-'}",
            f"メモ       : {body.note or '-'}",
            f"依頼日時    : {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            "発注後、管理画面の「発注予定」タブで到着予定日をご入力ください。",
        ]
        sent, sent_msg = _send_purchase_email(cfg, subject, "\n".join(lines))
        if sent:
            cur.execute("UPDATE purchase_order SET emailed=TRUE WHERE id=%s", (po_id,))
        conn.commit()
    return {"ok": True, "id": po_id, "emailed": sent, "email_message": sent_msg}


@router.get("/api/admin/purchase")
def admin_purchase_list(status: str = "", limit: int = 300, _=Depends(require_admin)):
    where, params = [], []
    if status:
        where.append("p.status = %s")
        params.append(status)
    sql = ("SELECT p.* FROM purchase_order p "
           + ("WHERE " + " AND ".join(where) + " " if where else "")
           + "ORDER BY (p.status='requested') DESC, p.requested_at DESC LIMIT %s")
    params.append(limit)
    with db() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    ST_JA = {"requested": "依頼中", "ordered": "発注済", "arrived": "入荷済", "cancelled": "取消"}
    out = []
    for r in rows:
        out.append({
            "id": r["id"], "code": r["code"], "name": r["item_name"], "unit": r["unit"],
            "qty": r["qty"], "status": r["status"], "status_ja": ST_JA.get(r["status"], r["status"]),
            "requested_by": r["requested_by"],
            "requested_at": r["requested_at"].strftime("%Y-%m-%d %H:%M") if r["requested_at"] else "",
            "eta": r["eta"].strftime("%Y-%m-%d") if r["eta"] else "",
            "ordered_at": r["ordered_at"].strftime("%Y-%m-%d %H:%M") if r["ordered_at"] else "",
            "arrived_at": r["arrived_at"].strftime("%Y-%m-%d %H:%M") if r["arrived_at"] else "",
            "emailed": r["emailed"], "req_note": r["req_note"], "order_note": r["order_note"],
        })
    return out


@router.post("/api/admin/purchase/{po_id}/order")
def admin_purchase_order(po_id: int, body: PurchaseOrderIn, _=Depends(require_admin)):
    """資材部: 発注済にして到着予定日を登録(依頼中/発注済のどちらからでも更新可)。"""
    try:
        eta = datetime.strptime(body.eta.strip(), "%Y-%m-%d").date()
    except Exception:
        raise HTTPException(400, "到着予定日は YYYY-MM-DD 形式で入力してください")
    with db() as conn, conn.cursor() as cur:
        cur.execute("""UPDATE purchase_order
                       SET status='ordered', eta=%s, order_note=%s,
                           ordered_at=COALESCE(ordered_at, now())
                       WHERE id=%s AND status IN ('requested','ordered')
                       RETURNING id""", (eta, body.order_note, po_id))
        r = cur.fetchone()
        if not r:
            raise HTTPException(404, "対象の発注が見つかりません")
        conn.commit()
    return {"ok": True}


@router.post("/api/admin/purchase/{po_id}/arrive")
def admin_purchase_arrive(po_id: int, _=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        cur.execute("""UPDATE purchase_order SET status='arrived', arrived_at=now()
                       WHERE id=%s AND status='ordered' RETURNING id""", (po_id,))
        r = cur.fetchone()
        if not r:
            raise HTTPException(404, "発注済の対象が見つかりません")
        conn.commit()
    return {"ok": True}


@router.post("/api/admin/purchase/{po_id}/cancel")
def admin_purchase_cancel(po_id: int, _=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        cur.execute("""UPDATE purchase_order SET status='cancelled'
                       WHERE id=%s AND status IN ('requested','ordered') RETURNING id""", (po_id,))
        r = cur.fetchone()
        if not r:
            raise HTTPException(404, "取消できる対象が見つかりません")
        conn.commit()
    return {"ok": True}


@router.get("/api/admin/purchase/settings")
def admin_purchase_settings_get(_=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        cfg = _smtp_config(cur)
    cfg["pass_set"] = bool(cfg.pop("pass"))   # パスワードは返さず設定有無だけ
    return cfg


@router.post("/api/admin/purchase/settings")
def admin_purchase_settings_set(body: PurchaseSettingsIn, _=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        _set_setting(cur, "purchase_email_to", body.to.strip())
        _set_setting(cur, "smtp_host", body.host.strip())
        _set_setting(cur, "smtp_port", str(body.port).strip() or "587")
        _set_setting(cur, "smtp_user", body.user.strip())
        _set_setting(cur, "smtp_from", body.from_.strip())
        _set_setting(cur, "smtp_tls", (body.tls or "starttls").strip())
        if body.password:   # 入力があった時だけ更新(空欄なら既存を保持)
            _set_setting(cur, "smtp_pass", body.password)
        conn.commit()
    return {"ok": True}
