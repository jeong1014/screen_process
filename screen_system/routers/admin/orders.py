"""
관리자 주문 — 조회/수정/취소 및 stage 강제 보정.
"""


from fastapi import APIRouter, Depends, HTTPException

from config import (
    MAX_STAGE, SHEET_SIDE_JA, STAGE_NAME,
)
from db import db
from security import require_admin
from schemas import (
    OrderPatch, StageFix,
)
from services.formatting import (
    fmt_opt, size_str, item_sides,
)

router = APIRouter()


# ---- 注文 ----------------------------------------------------------------
@router.get("/api/admin/orders")
def admin_orders(q: str = "", channel: str = "", payment: str = "", status: str = "",
                 date_from: str = "", date_to: str = "", limit: int = 100, _=Depends(require_admin)):
    where, params = ["1=1"], []
    if q:
        where.append("(o.order_no ILIKE %s OR o.customer_name ILIKE %s)")
        params += [f"%{q}%", f"%{q}%"]
    if channel:
        where.append("o.channel = %s"); params.append(channel)
    if payment:
        where.append("o.payment_status = %s"); params.append(payment)
    if status:
        where.append("o.order_status = %s"); params.append(status)
    else:
        # 状態が未指定(=「全部」)のときは取消済みをデフォルトで除外する。
        # 取消済みを見たい場合は状態フィルタで明示的に cancelled を選ぶ。
        where.append("o.order_status <> 'cancelled'")
    if date_from:
        where.append("o.ordered_at >= %s"); params.append(date_from)
    if date_to:
        where.append("o.ordered_at < (%s::date + 1)"); params.append(date_to)
    sql = f"""SELECT o.order_no, o.channel, o.customer_name, o.payment_status, o.order_status,
                     o.ordered_at, count(oi.id) AS items,
                     min(oi.current_stage) AS min_stage, max(oi.current_stage) AS max_stage
              FROM orders o LEFT JOIN order_items oi ON oi.order_id=o.id
              WHERE {' AND '.join(where)}
              GROUP BY o.id ORDER BY o.ordered_at DESC LIMIT %s"""
    params.append(limit)
    with db() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return [{"order_no": r["order_no"], "channel": r["channel"], "customer_name": r["customer_name"],
             "payment_status": r["payment_status"], "order_status": r["order_status"],
             "items": r["items"], "min_stage": r["min_stage"], "max_stage": r["max_stage"],
             "min_stage_name": STAGE_NAME.get(r["min_stage"], ""),
             "ordered_at": r["ordered_at"].strftime("%Y-%m-%d %H:%M") if r["ordered_at"] else ""} for r in rows]


@router.get("/api/admin/orders/{order_no}")
def admin_order_detail(order_no: str, _=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM orders WHERE order_no=%s", (order_no,))
        o = cur.fetchone()
        if not o:
            raise HTTPException(404, "注文が見つかりません")
        cur.execute("SELECT * FROM order_items WHERE order_id=%s ORDER BY item_no", (o["id"],))
        items = cur.fetchall()
        item_ids = [it["id"] for it in items] or [0]
        cur.execute("""SELECT se.scanned_at, se.stage_no, se.event_type, se.station, oi.barcode
                       FROM scan_events se JOIN order_items oi ON oi.id=se.order_item_id
                       WHERE se.order_item_id = ANY(%s) ORDER BY se.scanned_at DESC LIMIT 100""", (item_ids,))
        scans = cur.fetchall()
        cur.execute("SELECT * FROM shipments WHERE order_id=%s ORDER BY package_no", (o["id"],))
        ships = cur.fetchall()
        cur.execute("SELECT target_type, printer_type, status, printed_at, error_message FROM print_jobs WHERE order_id=%s ORDER BY id DESC", (o["id"],))
        prints = cur.fetchall()

    def item_out(it):
        s = item_sides(it)
        return {"barcode": it["barcode"], "product_type": it["product_type"], "fabric": it["fabric_type"],
                "size": size_str(it["width_mm"], it["height_mm"]), "quantity": it["quantity"],
                "sheet_side": SHEET_SIDE_JA.get(it.get("sheet_side")),
                "stage": it["current_stage"], "stage_name": STAGE_NAME.get(it["current_stage"], ""),
                "opts": {k: fmt_opt(kind, mm) for k, (kind, mm) in s.items()},
                "fire_cert_no": it["fire_cert_no"]}
    return {
        "order": {"order_no": o["order_no"], "channel": o["channel"], "customer_name": o["customer_name"],
                  "postal_code": o["postal_code"], "address": o["address"], "phone": o["phone"],
                  "payment_status": o["payment_status"], "order_status": o["order_status"],
                  "ordered_at": o["ordered_at"].strftime("%Y-%m-%d %H:%M") if o["ordered_at"] else ""},
        "items": [item_out(it) for it in items],
        "scans": [{"t": s["scanned_at"].strftime("%m/%d %H:%M"), "barcode": s["barcode"],
                   "stage": s["stage_no"], "stage_name": STAGE_NAME.get(s["stage_no"], ""),
                   "event": s["event_type"], "station": s["station"]} for s in scans],
        "shipments": [{"shipment_no": s["shipment_no"], "tracking_no": s["tracking_no"],
                       "shipping_status": s["shipping_status"], "bizlogi_status": s["bizlogi_status"],
                       "package_count": s["package_count"]} for s in ships],
        "prints": [{"target": p["target_type"], "printer": p["printer_type"], "status": p["status"],
                    "printed_at": p["printed_at"].strftime("%m/%d %H:%M") if p["printed_at"] else "",
                    "error": p["error_message"]} for p in prints],
    }


@router.patch("/api/admin/orders/{order_no}")
def admin_order_edit(order_no: str, body: OrderPatch, _=Depends(require_admin)):
    data = body.model_dump()
    new_no = (data.pop("order_no", None) or "").strip()
    fields = {k: v for k, v in data.items() if v is not None}
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM orders WHERE order_no=%s", (order_no,))
        o = cur.fetchone()
        if not o:
            raise HTTPException(404, "注文が見つかりません")
        # 注文番号の変更 → 製品バーコードも再生成
        if new_no and new_no != order_no:
            cur.execute("SELECT 1 FROM orders WHERE order_no=%s", (new_no,))
            if cur.fetchone():
                raise HTTPException(409, f"注文番号 {new_no} は既に使われています")
            cur.execute("UPDATE orders SET order_no=%s WHERE id=%s", (new_no, o["id"]))
            cur.execute("SELECT id, item_no, fabric_type FROM order_items WHERE order_id=%s ORDER BY item_no", (o["id"],))
            for it in cur.fetchall():
                cur.execute("UPDATE order_items SET barcode=%s WHERE id=%s",
                            (f"{new_no}{it['fabric_type']}{it['item_no']:02d}", it["id"]))
        if fields:
            sets = ", ".join(f"{k}=%s" for k in fields)
            cur.execute(f"UPDATE orders SET {sets} WHERE id=%s", list(fields.values()) + [o["id"]])
        conn.commit()
    final_no = new_no if (new_no and new_no != order_no) else order_no
    return {"ok": True, "order_no": final_no}


@router.post("/api/admin/orders/{order_no}/cancel")
def admin_order_cancel(order_no: str, _=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        cur.execute("UPDATE orders SET order_status='cancelled' WHERE order_no=%s", (order_no,))
        n = cur.rowcount
        conn.commit()
    if n == 0:
        raise HTTPException(404, "注文が見つかりません")
    return {"ok": True}


@router.patch("/api/admin/items/{barcode}/stage")
def admin_item_stage(barcode: str, body: StageFix, _=Depends(require_admin)):
    st = max(0, min(MAX_STAGE, body.stage))
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM order_items WHERE barcode=%s", (barcode,))
        it = cur.fetchone()
        if not it:
            raise HTTPException(404, "製品が見つかりません")
        cur.execute("UPDATE order_items SET current_stage=%s WHERE id=%s", (st, it["id"]))
        et = "complete" if st % 2 == 0 and st > 0 else "start"
        cur.execute("INSERT INTO scan_events (order_item_id, stage_no, event_type, station, note) "
                    "VALUES (%s,%s,%s,'admin','管理者補正')", (it["id"], st, et))
        conn.commit()
    return {"ok": True, "stage": st, "stage_name": STAGE_NAME.get(st, "")}
