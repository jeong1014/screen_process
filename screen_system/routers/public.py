"""
작업자·모니터·대시보드·라벨이 쓰는 공개 API (관리자 인증 없음).
"""

import json
from datetime import datetime

from fastapi import APIRouter, HTTPException

from config import (
    MAX_STAGE, PROC_BY_STAGE, SHEET_SIDE_JA, _PRODUCT_JP, MON_PROC,
    VELCRO_JA, SKIRT_ATTACH_JA,
)
from db import db
from schemas import (
    OrderIn, ScanIn, MonScan, InvScanIn,
)
from print_templates import render_order_label
from services.printing import silent_print_html
from services.formatting import (
    fmt_opt, size_str, qty_str, item_sides, worker_payload,
    board_status, _proc, _proc_fields, _eyelet_diagram_info,
)
from services.stage import (
    next_order_no, _fetch_item, get_item_payload, move_stage, monitor_scan,
)
from services.inventory import inv_scan
from services.labels import (
    printer_key as label_printer_key, resolve as resolve_label,
    listing as label_template_listing,
)

router = APIRouter()


@router.get("/api/shipping-slip/{barcode}")
def api_shipping_slip(barcode: str):
    with db() as conn, conn.cursor() as cur:
        cur.execute("""SELECT o.id, o.order_no, o.customer_name, o.postal_code, o.address,
                              o.phone, o.channel, o.payment_status
                       FROM order_items oi JOIN orders o ON o.id = oi.order_id
                       WHERE oi.barcode = %s""", (barcode,))
        o = cur.fetchone()
        if not o:
            raise HTTPException(404, f"注文が見つかりません: {barcode}")
        cur.execute("""SELECT barcode, fabric_type, width_mm, height_mm
                       FROM order_items WHERE order_id = %s ORDER BY item_no""", (o["id"],))
        items = [{"barcode": r["barcode"], "fabric": r["fabric_type"],
                  "size": size_str(r["width_mm"], r["height_mm"])} for r in cur.fetchall()]
    return {"order_no": o["order_no"], "customer_name": o["customer_name"],
            "postal_code": o["postal_code"], "address": o["address"], "phone": o["phone"],
            "channel": o["channel"], "payment_status": o["payment_status"], "items": items}


@router.get("/api/label-templates")
def api_label_templates():
    """注文入力画面で「この注文だけ別の版」を選ばせるための一覧(認証なし)。
       まだ作られていない版は返さない。"""
    return {"templates": [t for t in label_template_listing() if t["ready"]],
            "current": resolve_label()}


@router.post("/api/orders")
def create_order(order: OrderIn):
    if not order.items:
        raise HTTPException(400, "明細(items)が最低1件必要です。")
    # この注文に使うラベル版(指定が無ければ管理画面の既定)
    label_tpl = resolve_label(order.label_template)
    label_printer = label_printer_key(label_tpl)
    with db() as conn, conn.cursor() as cur:
        order_no = next_order_no(cur)
        cur.execute(
            """INSERT INTO orders (order_no, channel, mall_order_no, customer_name, postal_code,
                 address, phone, payment_status, order_status, raw_data, ordered_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'confirmed',%s,%s) RETURNING id""",
            (order_no, order.channel, order.mall_order_no, order.customer_name, order.postal_code,
             order.address, order.phone, order.payment_status,
             json.dumps(order.model_dump(), ensure_ascii=False),
             order.ordered_at or datetime.now().isoformat()),
        )
        order_id = cur.fetchone()["id"]

        def insert_item(item_no, barcode, it, fabric_type, width_mm, height_mm, sheet_side, pair_item_no):
            cur.execute(
                """INSERT INTO order_items (order_id, item_no, barcode, product_type, fabric_type,
                     width_mm, height_mm, quantity, sheet_side, pair_item_no,
                     process_top, process_top_mm, process_bottom,
                     process_bottom_mm, process_left, process_left_mm, process_right, process_right_mm,
                     velcro_sides, has_skirt,
                     velcro_type, skirt_attachment, skirt_no_seam, eyelet_method,
                     fire_cert_no)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING barcode""",
                (order_id, item_no, barcode, it.product_type, fabric_type, width_mm, height_mm,
                 it.quantity, sheet_side, pair_item_no,
                 it.process_top, it.process_top_mm, it.process_bottom, it.process_bottom_mm,
                 it.process_left, it.process_left_mm, it.process_right, it.process_right_mm,
                 it.velcro_sides, it.has_skirt,
                 it.velcro_type, it.skirt_attachment, it.skirt_no_seam, it.eyelet_method,
                 it.fire_cert_no),
            )
            return cur.fetchone()["barcode"]

        created = []
        seq = 0
        for it in order.items:
            # ハトメのピッチ(mm)を未入力のまま送ってきた場合は既定値300mmを補う
            for side in ("top", "bottom", "left", "right"):
                kind = getattr(it, f"process_{side}")
                if kind == "eyelet" and getattr(it, f"process_{side}_mm") is None:
                    setattr(it, f"process_{side}_mm", 300)
            if it.product_type == "two_sheet_set":
                # 2枚セット: 表面/裏面をそれぞれ独立した行(=独立したバーコード)として作成。
                # 加工オプション(process_*/velcro_type/skirt_*/eyelet_method/fire_cert_no)は
                # 表裏で共有(同じ値をそのまま複製)する。将来、表裏で個別設定したくなった場合は
                # ItemIn に front_process_*/back_process_* のような分離フィールドを追加すればよい。
                seq += 1
                front_no = seq
                seq += 1
                back_no = seq
                front_fabric = it.fabric_type
                back_fabric = it.back_fabric_type or it.fabric_type
                front_barcode = f"{order_no}{front_fabric}{front_no:02d}"   # 例: CDI260715001DP01
                back_barcode  = f"{order_no}{back_fabric}{back_no:02d}"    # 例: CDI260715001DP02
                created.append(insert_item(front_no, front_barcode, it, front_fabric,
                                            it.width_mm, it.height_mm, "front", back_no))
                created.append(insert_item(back_no, back_barcode, it, back_fabric,
                                            it.back_width_mm or it.width_mm,
                                            it.back_height_mm or it.height_mm, "back", front_no))
            else:
                seq += 1
                barcode = f"{order_no}{it.fabric_type}{seq:02d}"   # CDI260713001SDP01
                created.append(insert_item(seq, barcode, it, it.fabric_type,
                                            it.width_mm, it.height_mm, None, None))
        conn.commit()
        # ラベル自動印刷は「副作用」。注文は既に commit 済みなので、印刷や
        # レンダリングで例外が出ても注文全体(APIレスポンス)を落とさないよう
        # 各明細ごとに try/except で囲む。失敗はサーバーログに残す。
        for barcode in created:
            try:
                # DB에서 저장된 항목 데이터를 다시 불러와서 넘김
                cur.execute("SELECT * FROM order_items WHERE barcode=%s", (barcode,))
                item_row = cur.fetchone()
                # worker_payload(기존 함수)를 이용해 템플릿에 들어갈 데이터 포맷팅
                item_data = worker_payload(item_row)
                html_content = render_order_label(item_data)
                silent_print_html(html_content, label_printer)
            except Exception as e:
                import traceback
                print(f"⚠️ ラベル印刷に失敗(注文は登録済み) barcode={barcode}: {e}")
                traceback.print_exc()
    return {"order_no": order_no, "barcodes": created, "label_template": label_tpl}


@router.get("/api/orders/{order_no}")
def get_order(order_no: str):
    """作業者画面: バーコードで製品情報+stage を取得。"""
    return get_item_payload(order_no)


@router.post("/api/scan")
def scan(s: ScanIn):
    return move_stage(s.order_no, +1)


@router.post("/api/scan/undo")
def scan_undo(s: ScanIn):
    return move_stage(s.order_no, -1)


# =============================================================================
# ダッシュボード
# =============================================================================
@router.get("/api/board")
def api_board():
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT oi.*, o.ordered_at
               FROM order_items oi JOIN orders o ON o.id=oi.order_id
               WHERE o.order_status <> 'cancelled'
               ORDER BY o.ordered_at NULLS LAST, oi.id"""
        )
        rows = cur.fetchall()
    out = []
    for r in rows:
        s = item_sides(r)
        out.append({
            "order_no": r["barcode"],
            "fabric": r["fabric_type"],
            "size": size_str(r["width_mm"], r["height_mm"]),
            "qty": qty_str(r["product_type"], r["quantity"], r.get("sheet_side")),
            "sheet_side": SHEET_SIDE_JA.get(r.get("sheet_side")),
            "opts": {side: fmt_opt(kind, mm) for side, (kind, mm) in s.items()},
            "received_at": r["ordered_at"].strftime("%H:%M") if r["ordered_at"] else "--:--",
            "status": board_status(r["current_stage"]),
        })
    return out


@router.get("/api/events")
def api_events(limit: int = 20):
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT se.stage_no, se.event_type, se.scanned_at, oi.barcode
               FROM scan_events se JOIN order_items oi ON oi.id=se.order_item_id
               ORDER BY se.scanned_at DESC LIMIT %s""",
            (limit,),
        )
        rows = cur.fetchall()
    out = []
    for r in rows:
        stage, et = r["stage_no"], r["event_type"]
        proc = PROC_BY_STAGE.get(stage, "受付")
        if et == "undo":
            ev, text = "start", f"{proc} 取消"
        elif stage == MAX_STAGE:
            ev, text = "ship", "ハトメ完了(出荷準備)"
        elif stage % 2 == 0 and stage > 0:
            ev, text = "done", f"{proc} 完了"
        else:
            ev, text = "start", f"{proc} 開始"
        out.append({"t": r["scanned_at"].strftime("%H:%M"), "order_no": r["barcode"], "ev": ev, "text": text})
    return out


@router.get("/api/inventory")
def api_inventory():
    # 原反はダッシュボードでは種別(LN/DP/SDP)ごとに合算して表示
    with db() as conn, conn.cursor() as cur:
        cur.execute("""SELECT fabric_type AS fabric, SUM(remain) AS remain, SUM(capacity) AS cap
                       FROM inv_item
                       WHERE category='fabric' AND active AND fabric_type IS NOT NULL
                       GROUP BY fabric_type ORDER BY fabric_type""")
        rows = cur.fetchall()
    return [{"fabric": r["fabric"], "remain": int(r["remain"] or 0), "cap": int(r["cap"] or 0)} for r in rows]


@router.get("/api/accessories")
def api_accessories():
    with db() as conn, conn.cursor() as cur:
        cur.execute("""SELECT name, remain, capacity, unit FROM inv_item
                       WHERE category='accessory' AND active ORDER BY sort_order, code""")
        rows = cur.fetchall()
    return [{"name": r["name"], "remain": r["remain"], "cap": r["capacity"], "unit": r["unit"]} for r in rows]


@router.get("/api/label/{barcode}")
def api_label(barcode: str):
    """ラベル(v6) の自動記入用データ。barcode/fabric/size/4辺加工 を DB から返す。"""
    with db() as conn, conn.cursor() as cur:
        row = _fetch_item(cur, barcode)
    if not row:
        raise HTTPException(404, f"製品番号が見つかりません: {barcode}")
    s = item_sides(row)
    return {
        "barcodeValue": row["barcode"],           # スキャン対象(=DBのバーコード)
        "barcodeText": row["barcode"],            # バーコード下の表示文字
        "workOrderNo": row["barcode"],
        "orderNo": row["barcode"],
        "fabric": row["fabric_type"],
        "width_mm": row["width_mm"],
        "height_mm": row["height_mm"],
        "product": _PRODUCT_JP.get(row["product_type"], "1枚"),
        "set_quantity": row["quantity"],
        # スカートは下辺のみ。ハトメと同居しうるので _proc に渡して併記させる。
        "processing": {
            "top": _proc(*s["top"]),
            "bottom": _proc(*s["bottom"], skirt=bool(row.get("has_skirt"))),
            "left": _proc(*s["left"]),
            "right": _proc(*s["right"]),
        },
        # ラベルの仕様表に出す実データ(以前はテンプレートに固定値が埋まっていた)
        "velcroSides": row.get("velcro_sides"),
        "velcroType": VELCRO_JA.get(row.get("velcro_type"), ""),
        "hasSkirt": bool(row.get("has_skirt")),
        "skirtAttachment": (SKIRT_ATTACH_JA.get(row.get("skirt_attachment"), "")
                            if row.get("has_skirt") else ""),
        "bohenNumber": row["fire_cert_no"] or "",
        "qrValue": "https://cdigolf.base.ec/",
    }


@router.get("/api/inventory/label/{serial}")
def api_inv_label(serial: str):
    """ラベル記入用データ。シリアル(発行済)またはコード(プレビュー)を受ける。"""
    s = (serial or "").strip().upper()
    with db() as conn, conn.cursor() as cur:
        cur.execute("""SELECT u.serial, u.code, i.name, i.group_name, i.unit
                       FROM inv_unit u JOIN inv_item i ON i.code = u.code WHERE u.serial = %s""", (s,))
        r = cur.fetchone()
        if r:
            return {"serial": r["serial"], "code": r["code"], "qrValue": r["serial"],
                    "title": r["name"], "sub": f'{r["group_name"]} / {r["serial"]}', "unit": r["unit"]}
        # 未発行 → コード指定としてプレビュー
        cur.execute("SELECT code, name, group_name, unit FROM inv_item WHERE code = %s", (s,))
        r2 = cur.fetchone()
    if not r2:
        raise HTTPException(404, f"見つかりません: {serial}")
    return {"serial": r2["code"], "code": r2["code"], "qrValue": r2["code"],
            "title": r2["name"], "sub": f'{r2["group_name"]} / {r2["code"]}', "unit": r2["unit"]}


@router.post("/api/inventory/scan")
def api_inv_scan(body: InvScanIn):
    """QRシリアルをスキャン → 在庫-1・個体を消尽に。二重差引はしない。"""
    return inv_scan(body.code, body.worker)


@router.get("/api/monitor/{proc}")
def api_monitor(proc: str):
    if proc not in MON_PROC:
        raise HTTPException(404, "不明な工程")
    info = MON_PROC[proc]
    with db() as conn, conn.cursor() as cur:
        def lst(stage):
            cur.execute("""SELECT oi.barcode, oi.fabric_type, oi.width_mm, oi.height_mm, oi.updated_at, o.order_no
                           FROM order_items oi JOIN orders o ON o.id=oi.order_id
                           WHERE oi.current_stage=%s AND o.order_status<>'cancelled'
                           ORDER BY oi.updated_at""", (stage,))
            return [{"barcode": r["barcode"], "fabric": r["fabric_type"],
                     "size": size_str(r["width_mm"], r["height_mm"]), "order_no": r["order_no"]}
                    for r in cur.fetchall()]
        queue = lst(info["queue"])
        wip = lst(info["wip"])
        cur.execute("SELECT count(*) AS c FROM scan_events WHERE stage_no=%s AND scanned_at::date=CURRENT_DATE",
                    (info["done"],))
        today_done = cur.fetchone()["c"]
        cur.execute("""SELECT se.scanned_at AS se_at, se.stage_no AS se_stage, oi.*
                       FROM scan_events se JOIN order_items oi ON oi.id=se.order_item_id
                       WHERE se.stage_no IN (%s,%s) ORDER BY se.scanned_at DESC LIMIT 1""",
                    (info["wip"], info["done"]))
        lr = cur.fetchone()
        last = None
        if lr:
            last = {"barcode": lr["barcode"], "fabric": lr["fabric_type"],
                    "size": size_str(lr["width_mm"], lr["height_mm"]),
                    "result": "完了" if lr["se_stage"] == info["done"] else "開始",
                    "at": lr["se_at"].strftime("%H:%M:%S"),
                    "fields": _proc_fields(proc, lr)}
            if proc == "eyelet":
                last.update(_eyelet_diagram_info(lr))
    return {"proc": proc, "name_ja": info["ja"], "name_ko": info["ko"],
            "queue": queue, "wip": wip, "queue_count": len(queue), "wip_count": len(wip),
            "today_done": today_done, "last": last,
            "server_time": datetime.now().strftime("%H:%M:%S")}


@router.post("/api/monitor/{proc}/scan")
def api_monitor_scan(proc: str, body: MonScan):
    return monitor_scan(proc, body.barcode)
