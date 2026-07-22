"""
관리자 리포트 — スキャン履歴 / 消防法 月次報告 / 統計 / CSV書き出し.
"""

import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from config import (
    STAGE_NAME,
)
from db import db
from security import require_admin, _check_pw_query
from services.formatting import (
    size_str,
)

router = APIRouter()


def _scan_rows(cur, q="", stage="", date_from="", date_to="", limit=500):
    where, params = ["1=1"], []
    if q:
        where.append("(oi.barcode ILIKE %s OR o.order_no ILIKE %s)"); params += [f"%{q}%", f"%{q}%"]
    if stage != "" and stage is not None:
        where.append("se.stage_no=%s"); params.append(int(stage))
    if date_from: where.append("se.scanned_at >= %s"); params.append(date_from)
    if date_to:   where.append("se.scanned_at < (%s::date + 1)"); params.append(date_to)
    cur.execute(f"""SELECT se.id, se.scanned_at, se.stage_no, se.event_type, se.station, se.worker,
                           oi.barcode, o.order_no
                    FROM scan_events se JOIN order_items oi ON oi.id = se.order_item_id
                    JOIN orders o ON o.id = oi.order_id
                    WHERE {' AND '.join(where)} ORDER BY se.scanned_at DESC LIMIT %s""", params + [limit])
    return cur.fetchall()


@router.get("/api/admin/scans")
def admin_scans(q: str = "", stage: str = "", date_from: str = "", date_to: str = "",
                limit: int = 300, _=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        rows = _scan_rows(cur, q, stage, date_from, date_to, limit)
    return [{"id": r["id"],
             "t": r["scanned_at"].strftime("%Y-%m-%d %H:%M"), "barcode": r["barcode"], "order_no": r["order_no"],
             "stage": r["stage_no"], "stage_name": STAGE_NAME.get(r["stage_no"], ""),
             "event": r["event_type"], "station": r["station"], "worker": r["worker"]} for r in rows]


@router.delete("/api/admin/scans/{scan_id}")
def admin_scan_delete(scan_id: int, _=Depends(require_admin)):
    """スキャン履歴を1件削除する(誤スキャン・テスト記録の掃除用)。

    注意: 履歴を消しても order_items.current_stage は動かない。
    工程を戻したい場合は注文詳細の「工程で補正」を使うこと。
    """
    with db() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM scan_events WHERE id=%s", (scan_id,))
        deleted = cur.rowcount
        conn.commit()
    if not deleted:
        raise HTTPException(404, "該当する履歴がありません")
    return {"ok": True, "deleted": deleted}


@router.get("/api/admin/scans.csv")
def admin_scans_csv(q: str = "", stage: str = "", date_from: str = "", date_to: str = "", pw: str = ""):
    _check_pw_query(pw)
    with db() as conn, conn.cursor() as cur:
        rows = _scan_rows(cur, q, stage, date_from, date_to, 100000)
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["日時", "バーコード", "注文番号", "工程", "種別", "端末", "担当"])
    for r in rows:
        w.writerow([r["scanned_at"].strftime("%Y-%m-%d %H:%M"), r["barcode"], r["order_no"],
                    STAGE_NAME.get(r["stage_no"], r["stage_no"]), r["event_type"], r["station"], r["worker"]])
    return Response(content="\ufeff" + buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="scan_history.csv"'})


# ---- 消防法 月次報告 -------------------------------------------------------
def _fire_rows(cur, month: str):
    # month = 'YYYY-MM'
    cur.execute("""SELECT o.order_no, o.ordered_at::date AS sold_at, o.channel,
                          oi.product_type, oi.fabric_type, oi.width_mm, oi.height_mm, oi.quantity,
                          oi.fire_cert_no, o.customer_name, o.address
                   FROM orders o JOIN order_items oi ON oi.order_id=o.id
                   WHERE to_char(o.ordered_at,'YYYY-MM')=%s AND o.order_status <> 'cancelled'
                   ORDER BY o.ordered_at""", (month,))
    return cur.fetchall()


@router.get("/api/admin/fire-report")
def admin_fire_report(month: str = Query(...), _=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        rows = _fire_rows(cur, month)
    return [{"order_no": r["order_no"], "sold_at": str(r["sold_at"]), "channel": r["channel"],
             "product_type": r["product_type"], "fabric": r["fabric_type"],
             "size": size_str(r["width_mm"], r["height_mm"]), "quantity": r["quantity"],
             "fire_cert_no": r["fire_cert_no"], "buyer": r["customer_name"], "address": r["address"]} for r in rows]


@router.get("/api/admin/fire-report.csv")
def admin_fire_report_csv(month: str, pw: str = ""):
    _check_pw_query(pw)
    with db() as conn, conn.cursor() as cur:
        rows = _fire_rows(cur, month)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["注文番号", "販売日", "チャネル", "商品", "生地", "サイズ", "数量", "防炎番号", "購入者", "住所"])
    for r in rows:
        w.writerow([r["order_no"], r["sold_at"], r["channel"], r["product_type"], r["fabric_type"],
                    size_str(r["width_mm"], r["height_mm"]), r["quantity"], r["fire_cert_no"],
                    r["customer_name"], r["address"]])
    data = "﻿" + buf.getvalue()   # BOM付きでExcel文字化け防止
    return Response(content=data, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="fire_report_{month}.csv"'})


# ---- 統計 ----------------------------------------------------------------
@router.get("/api/admin/stats")
def admin_stats(_=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        cur.execute("""SELECT to_char(ordered_at,'MM-DD') AS d, count(*) AS c FROM orders
                       WHERE ordered_at >= now() - interval '14 days' GROUP BY d ORDER BY d""")
        daily = [{"d": r["d"], "count": r["c"]} for r in cur.fetchall()]
        cur.execute("SELECT channel, count(*) AS c FROM orders GROUP BY channel ORDER BY c DESC")
        by_channel = [{"channel": r["channel"], "count": r["c"]} for r in cur.fetchall()]
        cur.execute("SELECT fabric_type, count(*) AS c, sum(quantity) AS q FROM order_items GROUP BY fabric_type ORDER BY c DESC")
        by_fabric = [{"fabric": r["fabric_type"], "count": r["c"], "qty": r["q"]} for r in cur.fetchall()]
        cur.execute("SELECT count(*) AS c FROM orders")
        total_orders = cur.fetchone()["c"]
        cur.execute("SELECT count(*) AS c FROM order_items")
        total_items = cur.fetchone()["c"]
    return {"daily": daily, "by_channel": by_channel, "by_fabric": by_fabric,
            "total_orders": total_orders, "total_items": total_items}


# ---- データ書き出し(CSV) --------------------------------------------------
@router.get("/api/admin/export/orders.csv")
def admin_export_orders(pw: str = ""):
    _check_pw_query(pw)
    with db() as conn, conn.cursor() as cur:
        cur.execute("""SELECT o.order_no, o.ordered_at, o.channel, o.customer_name, o.payment_status,
                              o.order_status, oi.barcode, oi.product_type, oi.fabric_type,
                              oi.width_mm, oi.height_mm, oi.quantity, oi.current_stage
                       FROM orders o JOIN order_items oi ON oi.order_id=o.id
                       ORDER BY o.ordered_at DESC""")
        rows = cur.fetchall()
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["注文番号", "受注日時", "チャネル", "顧客", "決済", "状態", "バーコード", "商品",
                "生地", "幅", "高さ", "数量", "工程"])
    for r in rows:
        w.writerow([r["order_no"], r["ordered_at"], r["channel"], r["customer_name"], r["payment_status"],
                    r["order_status"], r["barcode"], r["product_type"], r["fabric_type"], r["width_mm"],
                    r["height_mm"], r["quantity"], STAGE_NAME.get(r["current_stage"], r["current_stage"])])
    return Response(content="﻿" + buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="orders.csv"'})


@router.get("/api/admin/export/inventory.csv")
def admin_export_inventory(pw: str = ""):
    _check_pw_query(pw)
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT fabric_type, remain_rolls, capacity_rolls, reorder_point FROM fabric_inventory ORDER BY fabric_type")
        fab = cur.fetchall()
        cur.execute("SELECT name, remain, capacity, unit, reorder_point FROM accessories ORDER BY sort_order")
        acc = cur.fetchall()
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["種別", "名称", "残", "容量", "単位", "発注点"])
    for r in fab:
        w.writerow(["生地", r["fabric_type"], r["remain_rolls"], r["capacity_rolls"], "ロール", r["reorder_point"]])
    for r in acc:
        w.writerow(["付属品", r["name"], r["remain"], r["capacity"], r["unit"], r["reorder_point"]])
    return Response(content="﻿" + buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="inventory.csv"'})
