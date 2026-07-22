"""
スクリーン原団 工場工程管理システム — FastAPI バックエンド (v2)
worker_v5.html / dashboard_v2_2.html の API契約に整合。

役割: ブラウザHTML(入力/作業者/ダッシュボード)と PostgreSQL の仲介。
  進行状態 stage(0〜6) を order_items.current_stage で一元管理。
  「注文番号(製品番号)」= order_items.barcode。

実行:  uvicorn app:app --reload --host 0.0.0.0 --port 8000
必要:  pip install fastapi uvicorn "psycopg[binary]"
DB  :  環境変数 DATABASE_URL
"""

import os
import json

from datetime import date, datetime

from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from print_templates import render_inventory_label, render_order_label, render_shipping_slip
from db import db, _set_setting
from security import require_admin, _check_pw_query, _admin_password
from services.printing import silent_print_html
from services.mailer import _smtp_config, _send_purchase_email

from config import (
    FRONTEND_DIR, MAX_STAGE,
    SIDE_JA, PROC_BY_STAGE, VELCRO_JA, SKIRT_ATTACH_JA, EYELET_METHOD_JA,
    SHEET_SIDE_JA, STAGE_NAME, _PRODUCT_JP, MON_PROC, INV_GROUPS, DB_TABLES,
)
from schemas import (
    OrderIn, ScanIn, MonScan, InvScanIn, LoginIn,
    AdjustIn, ReorderIn, AccIn,
    InvIssueIn, InvAdjustIn, InvReorderIn, InvItemIn,
    PurchaseReqIn, PurchaseOrderIn, PurchaseSettingsIn,
    OrderPatch, StageFix, ShipIn, SettingsIn, DbEdit,
)

app = FastAPI(title="スクリーン原団 工程管理 v2")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# =============================================================================
# 表示用フォーマット (DBの構造データ → 各画面が期待する文字列)
# =============================================================================

# 販売サイトのオプション体系(2026-07 統合)に合わせた表示用ラベル
# 2枚セット(two_sheet_set)の表面/裏面区分(裁断/ミシン/ハトメを2回スキャンするため2行に分けて管理)


def fmt_opt(kind: str, mm) -> str:
    """ダッシュボード opts 用: 上/下/左/右 それぞれの加工文字列。"""
    if kind == "eyelet":
        return f"ハトメP{mm}" if mm else "ハトメ"
    if kind == "skirt":
        return "スカート"
    if kind == "velcro":
        return "ベルクロ"
    return "なし"


def eyelet_val(kind: str, mm) -> str:
    """作業者画面ハトメ工程 用: その辺のハトメ間隔。ハトメ以外は なし。"""
    if kind == "eyelet":
        return f"P{mm}" if mm else "P"
    return "なし"


def size_str(w, h) -> str:
    return f"W{w}×H{h}"


def qty_str(product_type: str, q: int, sheet_side=None) -> str:
    # 2枚セットは表面/裏面が別行(別バーコード)になったため、行自体はどちらも「1枚」の数量。
    # sheet_side が付いている行(=分離済みの新方式)では「セット」表記をしない。
    if product_type == "two_sheet_set" and not sheet_side:
        return f"{q}セット / 合計{q*2}枚"
    return f"{q}枚"


def item_sides(row):
    """4辺の (kind, mm) を返す。"""
    return {
        "top":    (row["process_top"],    row["process_top_mm"]),
        "bottom": (row["process_bottom"], row["process_bottom_mm"]),
        "left":   (row["process_left"],   row["process_left_mm"]),
        "right":  (row["process_right"],  row["process_right_mm"]),
    }


def worker_payload(row, pair_barcode=None):
    """作業者画面 GET /api/orders/{no} の応答形。
       2枚セット(two_sheet_set)は表面/裏面が別行(別バーコード)なので、
       この行がどちら側か(sheet_side)と、対になるもう片方のバーコード(pair_barcode)を含める。"""
    s = item_sides(row)
    velcro_sides = [SIDE_JA[k] for k, (kind, _) in s.items() if kind == "velcro"]
    skirt_any = any(kind == "skirt" for kind, _ in s.values())
    eyelet_pitch_mm = next((mm for kind, mm in s.values() if kind == "eyelet" and mm), None)
    return {
        "order_no": row["barcode"],
        "fabric": row["fabric_type"],
        "size": size_str(row["width_mm"], row["height_mm"]),
        "sheet_side": SHEET_SIDE_JA.get(row.get("sheet_side")),
        "pair_barcode": pair_barcode,
        # ベルクロは全製品に必ず付くため(辺ごとの選択は廃止)、常に「有り」+ 雌雄を表示。
        # 旧データで辺に'velcro'が個別設定されていれば、その面も参考として表示する。
        "magictape": "有り" + ("(" + "・".join(velcro_sides) + ")" if velcro_sides else ""),
        "velcro_type": VELCRO_JA.get(row.get("velcro_type"), "-"),
        "skirt": "有り" if skirt_any else "無し",
        "skirt_attachment": SKIRT_ATTACH_JA.get(row.get("skirt_attachment"), "なし") if skirt_any else "なし",
        "skirt_no_seam": "シームレス" if (skirt_any and row.get("skirt_no_seam")) else ("通常" if skirt_any else "なし"),
        "e_top":    eyelet_val(*s["top"]),
        "e_bottom": eyelet_val(*s["bottom"]),
        "e_left":   eyelet_val(*s["left"]),
        "e_right":  eyelet_val(*s["right"]),
        "eyelet_method": EYELET_METHOD_JA.get(row.get("eyelet_method"), "なし"),
        "eyelet_method_code": row.get("eyelet_method"),   # "A"/"B"/"C"/None(作業者画面の配置図の切替用)
        "eyelet_pitch_mm": eyelet_pitch_mm,
        "stage": row["current_stage"],
    }


def board_status(stage: int):
    """stage(0〜6) → 各工程の working/wait/done。"""
    def st(done_at, wip_at):
        return "done" if stage >= done_at else ("working" if stage == wip_at else "wait")
    return {
        "cutting": st(2, 1),
        "sewing":  st(4, 3),
        "eyelet":  st(6, 5),
    }

# 프린터 설정 로드


# =============================================================================
# 入力モデル
# =============================================================================


# =============================================================================
# ページ
# =============================================================================
@app.get("/")
def root():
    return RedirectResponse("/input")

@app.get("/input")
def page_input():
    return FileResponse(os.path.join(FRONTEND_DIR, "input.html"))

@app.get("/worker")
def page_worker():
    return FileResponse(os.path.join(FRONTEND_DIR, "worker.html"))

@app.get("/dashboard")
def page_dashboard():
    return FileResponse(os.path.join(FRONTEND_DIR, "dashboard.html"))

@app.get("/shop")
def page_shop():
    # 販売サイトの商品ページ(detail_sizeGuide_v26.html)を同一オリジンで配信。
    # ここから「注文を確定」すると POST /api/orders でDBに登録される。
    base = os.path.dirname(os.path.abspath(__file__))
    return FileResponse(os.path.join(base, "detail_sizeGuide_v26.html"))

@app.get("/shipping-slip/{barcode}")
def page_shipping_slip(barcode: str):
    # ハトメ完了時などに開く送_り状(印刷)ページ。barcode から注文を引いて表示する。
    return FileResponse(os.path.join(FRONTEND_DIR, "shipping_slip.html"))


@app.get("/api/shipping-slip/{barcode}")
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


# =============================================================================
# 入力: 注文全体(顧客+明細)  POST /api/orders
# =============================================================================
def next_order_no(cur) -> str:
    ymd = date.today().strftime("%y%m%d")   # 例: 260713
    cur.execute("SELECT count(*) AS c FROM orders WHERE order_no LIKE %s", (f"CDI{ymd}%",))
    return f"CDI{ymd}{cur.fetchone()['c']+1:03d}"   # CDI260713001


@app.post("/api/orders")
def create_order(order: OrderIn):
    if not order.items:
        raise HTTPException(400, "明細(items)が最低1件必要です。")
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
                     velcro_type, skirt_attachment, skirt_no_seam, eyelet_method,
                     fire_cert_no)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING barcode""",
                (order_id, item_no, barcode, it.product_type, fabric_type, width_mm, height_mm,
                 it.quantity, sheet_side, pair_item_no,
                 it.process_top, it.process_top_mm, it.process_bottom, it.process_bottom_mm,
                 it.process_left, it.process_left_mm, it.process_right, it.process_right_mm,
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
                silent_print_html(html_content, "order_printer")
            except Exception as e:
                import traceback
                print(f"⚠️ ラベル印刷に失敗(注文は登録済み) barcode={barcode}: {e}")
                traceback.print_exc()
    return {"order_no": order_no, "barcodes": created}


# =============================================================================
# 作業者画面
# =============================================================================
def _fetch_item(cur, barcode):
    cur.execute("SELECT * FROM order_items WHERE barcode=%s", (barcode,))
    return cur.fetchone()


def _pair_barcode(cur, row):
    """2枚セット(表面/裏面)で、対になるもう片方のバーコードを引く。単品なら None。"""
    if not row or not row.get("pair_item_no"):
        return None
    cur.execute("SELECT barcode FROM order_items WHERE order_id=%s AND item_no=%s",
                (row["order_id"], row["pair_item_no"]))
    r = cur.fetchone()
    return r["barcode"] if r else None


@app.get("/api/orders/{order_no}")
def get_order(order_no: str):
    """作業者画面: バーコードで製品情報+stage を取得。"""
    with db() as conn, conn.cursor() as cur:
        row = _fetch_item(cur, order_no)
        if not row:
            raise HTTPException(404, f"製品番号が見つかりません: {order_no}")
        pair_bc = _pair_barcode(cur, row)
    return worker_payload(row, pair_bc)


def _move(order_no: str, delta: int):
    with db() as conn, conn.cursor() as cur:
        row = _fetch_item(cur, order_no)
        if not row:
            raise HTTPException(404, f"製品番号が見つかりません: {order_no}")
        new_stage = min(MAX_STAGE, max(0, row["current_stage"] + delta))
        et = "undo" if delta < 0 else ("complete" if new_stage % 2 == 0 else "start")
        cur.execute(
            """UPDATE order_items
               SET current_stage=%s,
                   started_at = COALESCE(started_at, CASE WHEN %s>0 THEN now() END),
                   completed_at = CASE WHEN %s=%s THEN now() ELSE completed_at END
               WHERE id=%s""",
            (new_stage, delta, new_stage, MAX_STAGE, row["id"]),
        )
        cur.execute(
            "INSERT INTO scan_events (order_item_id, stage_no, event_type, station) VALUES (%s,%s,%s,%s)",
            (row["id"], new_stage, et, "worker_screen"),
        )
        cur.execute("SELECT * FROM order_items WHERE id=%s", (row["id"],))
        row = cur.fetchone()
        pair_bc = _pair_barcode(cur, row)
        conn.commit()
    ###################
        if new_stage == MAX_STAGE and delta > 0:
            print(f"📦 제품 {order_no} ハトメ完了(최종) -> 송장 자동 출력 개시")
            
            # 1. 주문(고객) 정보 가져오기 (이 부분이 추가되었습니다!)
            cur.execute("SELECT * FROM orders WHERE order_no=%s", (order_no,))
            order_info = cur.fetchone() or {}
            
            # 2. 해당 주문에 포함된 전체 제품 목록 가져오기
            cur.execute("SELECT barcode, fabric_type as fabric, width_mm, height_mm FROM order_items WHERE order_id=%s", (row["order_id"],))
            items_db = cur.fetchall()
            items_list = [{"barcode": i["barcode"], "fabric": i["fabric"], "size": f"W{i['width_mm']}xH{i['height_mm']}"} for i in items_db]
            
            # 3. 위에서 만든 템플릿에 데이터(order_info)를 넣어 HTML 생성
            html_content = render_shipping_slip(order_no=order_no, order_info=order_info, items=items_list)
            
            # 4. 송장 프린터로 전송
            silent_print_html(html_content, "invoice_printer")
    return worker_payload(row, pair_bc)


@app.post("/api/scan")
def scan(s: ScanIn):
    return _move(s.order_no, +1)


@app.post("/api/scan/undo")
def scan_undo(s: ScanIn):
    return _move(s.order_no, -1)


# =============================================================================
# ダッシュボード
# =============================================================================
@app.get("/api/board")
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


@app.get("/api/events")
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


@app.get("/api/inventory")
def api_inventory():
    # 原反はダッシュボードでは種別(LN/DP/SDP)ごとに合算して表示
    with db() as conn, conn.cursor() as cur:
        cur.execute("""SELECT fabric_type AS fabric, SUM(remain) AS remain, SUM(capacity) AS cap
                       FROM inv_item
                       WHERE category='fabric' AND active AND fabric_type IS NOT NULL
                       GROUP BY fabric_type ORDER BY fabric_type""")
        rows = cur.fetchall()
    return [{"fabric": r["fabric"], "remain": int(r["remain"] or 0), "cap": int(r["cap"] or 0)} for r in rows]


@app.get("/api/accessories")
def api_accessories():
    with db() as conn, conn.cursor() as cur:
        cur.execute("""SELECT name, remain, capacity, unit FROM inv_item
                       WHERE category='accessory' AND active ORDER BY sort_order, code""")
        rows = cur.fetchall()
    return [{"name": r["name"], "remain": r["remain"], "cap": r["capacity"], "unit": r["unit"]} for r in rows]


if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


# =============================================================================
# ラベル自動化: /label/{barcode} でラベルを開くと DB から自動で埋まる
#   複数枚まとめて出す時は /label?serials=バーコード1,バーコード2&print=1 も使える
#   (2枚セットの表面/裏面を同時に印刷する時など。在庫QRラベルと同じ方式)
# =============================================================================
@app.get("/label")
def page_label_multi():
    # 本番ラベル = label_gorilla.html(ゴリラインパクトデザイン)。
    # 旧 label.html は使わずバックアップとして残置。
    return FileResponse(os.path.join(FRONTEND_DIR, "label_gorilla.html"))


@app.get("/label/{barcode}")
def page_label(barcode: str):
    return FileResponse(os.path.join(FRONTEND_DIR, "label_gorilla.html"))


# 加工種別(DB) → ラベル v6 の processing 形式


def _proc(kind, mm):
    if kind == "eyelet":
        return {"type": "eyelet", "spacing": mm}
    if kind in ("skirt", "velcro"):
        return {"type": kind}
    return {"type": "none"}


@app.get("/api/label/{barcode}")
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
        "processing": {
            "top": _proc(*s["top"]),
            "bottom": _proc(*s["bottom"]),
            "left": _proc(*s["left"]),
            "right": _proc(*s["right"]),
        },
        "bohenNumber": row["fire_cert_no"] or "",
        "qrValue": "https://cdigolf.base.ec/",
    }


# =============================================================================
# 管理者ページ /admin  (簡易パスワード + 各種管理API)
# =============================================================================
from fastapi import Query
from fastapi.responses import Response
import csv, io


@app.get("/admin")
def page_admin():
    return FileResponse(os.path.join(FRONTEND_DIR, "admin.html"))


@app.post("/api/admin/login")
def admin_login(body: LoginIn):
    with db() as conn, conn.cursor() as cur:
        ok = body.password == _admin_password(cur)
    if not ok:
        raise HTTPException(401, "パスワードが違います")
    return {"ok": True}


# ---- 在庫 ----------------------------------------------------------------
@app.get("/api/admin/inventory")
def admin_inventory(_=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT fabric_type, remain_rolls, capacity_rolls, reorder_point FROM fabric_inventory ORDER BY fabric_type")
        fabric = [{"kind": "fabric", "id": r["fabric_type"], "name": r["fabric_type"],
                   "remain": r["remain_rolls"], "cap": r["capacity_rolls"],
                   "reorder": r["reorder_point"], "unit": "ロール",
                   "low": r["remain_rolls"] <= r["reorder_point"]} for r in cur.fetchall()]
        cur.execute("SELECT id, name, remain, capacity, unit, reorder_point FROM accessories ORDER BY sort_order, id")
        acc = [{"kind": "accessory", "id": r["id"], "name": r["name"], "remain": r["remain"],
                "cap": r["capacity"], "reorder": r["reorder_point"], "unit": r["unit"],
                "low": r["remain"] <= r["reorder_point"]} for r in cur.fetchall()]
    return {"fabric": fabric, "accessories": acc}


@app.post("/api/admin/inventory/adjust")
def admin_inventory_adjust(body: AdjustIn, _=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        if body.kind == "fabric":
            cur.execute("UPDATE fabric_inventory SET remain_rolls = remain_rolls + %s, updated_at=now() "
                        "WHERE fabric_type=%s RETURNING remain_rolls", (body.delta, body.id))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "生地が見つかりません")
            bal = row["remain_rolls"]
            cur.execute("""INSERT INTO inventory_transactions (kind, fabric_type, delta, reason, balance_after, note, worker)
                           VALUES ('fabric',%s,%s,%s,%s,%s,%s)""",
                        (body.id, body.delta, body.reason, bal, body.note, body.worker))
        elif body.kind == "accessory":
            cur.execute("UPDATE accessories SET remain = remain + %s WHERE id=%s RETURNING remain",
                        (body.delta, int(body.id)))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "付属品が見つかりません")
            bal = row["remain"]
            cur.execute("""INSERT INTO inventory_transactions (kind, accessory_id, delta, reason, balance_after, note, worker)
                           VALUES ('accessory',%s,%s,%s,%s,%s,%s)""",
                        (int(body.id), body.delta, body.reason, bal, body.note, body.worker))
        else:
            raise HTTPException(400, "kind は fabric / accessory")
        conn.commit()
    return {"ok": True, "balance": bal}


@app.post("/api/admin/inventory/reorder")
def admin_inventory_reorder(body: ReorderIn, _=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        if body.kind == "fabric":
            cur.execute("UPDATE fabric_inventory SET reorder_point=%s WHERE fabric_type=%s", (body.reorder_point, body.id))
        else:
            cur.execute("UPDATE accessories SET reorder_point=%s WHERE id=%s", (body.reorder_point, int(body.id)))
        conn.commit()
    return {"ok": True}


def _inv_hist_rows(cur, kind="", reason="", date_from="", date_to="", limit=500):
    where, params = ["1=1"], []
    if kind:      where.append("t.kind=%s");   params.append(kind)
    if reason:    where.append("t.reason=%s"); params.append(reason)
    if date_from: where.append("t.created_at >= %s"); params.append(date_from)
    if date_to:   where.append("t.created_at < (%s::date + 1)"); params.append(date_to)
    cur.execute(f"""SELECT t.created_at, t.kind, t.delta, t.reason, t.balance_after, t.note, t.worker,
                           COALESCE(t.fabric_type::text, a.name) AS target
                    FROM inventory_transactions t LEFT JOIN accessories a ON a.id = t.accessory_id
                    WHERE {' AND '.join(where)} ORDER BY t.created_at DESC LIMIT %s""", params + [limit])
    return cur.fetchall()


@app.get("/api/admin/inventory/history")
def admin_inventory_history(kind: str = "", reason: str = "", date_from: str = "",
                            date_to: str = "", limit: int = 300, _=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        rows = _inv_hist_rows(cur, kind, reason, date_from, date_to, limit)
    return [{"t": r["created_at"].strftime("%Y-%m-%d %H:%M"), "target": r["target"], "kind": r["kind"],
             "delta": r["delta"], "reason": r["reason"], "balance": r["balance_after"],
             "note": r["note"], "worker": r["worker"]} for r in rows]


@app.get("/api/admin/inventory/history.csv")
def admin_inventory_history_csv(kind: str = "", reason: str = "", date_from: str = "",
                                date_to: str = "", pw: str = ""):
    _check_pw_query(pw)
    with db() as conn, conn.cursor() as cur:
        rows = _inv_hist_rows(cur, kind, reason, date_from, date_to, 100000)
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["日時", "対象", "種別", "区分", "増減", "残", "メモ", "担当"])
    rmap = {"in": "入庫", "out": "消尽", "adjust": "調整"}
    for r in rows:
        w.writerow([r["created_at"].strftime("%Y-%m-%d %H:%M"), r["target"], r["kind"],
                    rmap.get(r["reason"], r["reason"]), r["delta"], r["balance_after"], r["note"], r["worker"]])
    return Response(content="\ufeff" + buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="inventory_history.csv"'})


def _scan_rows(cur, q="", stage="", date_from="", date_to="", limit=500):
    where, params = ["1=1"], []
    if q:
        where.append("(oi.barcode ILIKE %s OR o.order_no ILIKE %s)"); params += [f"%{q}%", f"%{q}%"]
    if stage != "" and stage is not None:
        where.append("se.stage_no=%s"); params.append(int(stage))
    if date_from: where.append("se.scanned_at >= %s"); params.append(date_from)
    if date_to:   where.append("se.scanned_at < (%s::date + 1)"); params.append(date_to)
    cur.execute(f"""SELECT se.scanned_at, se.stage_no, se.event_type, se.station, se.worker,
                           oi.barcode, o.order_no
                    FROM scan_events se JOIN order_items oi ON oi.id = se.order_item_id
                    JOIN orders o ON o.id = oi.order_id
                    WHERE {' AND '.join(where)} ORDER BY se.scanned_at DESC LIMIT %s""", params + [limit])
    return cur.fetchall()


@app.get("/api/admin/scans")
def admin_scans(q: str = "", stage: str = "", date_from: str = "", date_to: str = "",
                limit: int = 300, _=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        rows = _scan_rows(cur, q, stage, date_from, date_to, limit)
    return [{"t": r["scanned_at"].strftime("%Y-%m-%d %H:%M"), "barcode": r["barcode"], "order_no": r["order_no"],
             "stage": r["stage_no"], "stage_name": STAGE_NAME.get(r["stage_no"], ""),
             "event": r["event_type"], "station": r["station"], "worker": r["worker"]} for r in rows]


@app.get("/api/admin/scans.csv")
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


@app.post("/api/admin/accessories")
def admin_accessory_create(body: AccIn, _=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT COALESCE(max(sort_order),0)+1 AS s FROM accessories")
        so = cur.fetchone()["s"]
        cur.execute("""INSERT INTO accessories (name, remain, capacity, unit, reorder_point, sort_order)
                       VALUES (%s,0,%s,%s,%s,%s) RETURNING id""",
                    (body.name, body.capacity, body.unit, body.reorder_point, so))
        nid = cur.fetchone()["id"]; conn.commit()
    return {"ok": True, "id": nid}


@app.delete("/api/admin/accessories/{acc_id}")
def admin_accessory_delete(acc_id: int, _=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM accessories WHERE id=%s", (acc_id,))
        n = cur.rowcount; conn.commit()
    if n == 0:
        raise HTTPException(404, "付属品が見つかりません")
    return {"ok": True}


# ---- QR在庫 v2: 品目コード + シリアル個体 --------------------------------
#   ・品目はエクセル準拠のコード(11〜61)で管理。原反=ロール / 付属品=箱。
#   ・QR発行 = 入庫(+1)。発行のたびに「コード-連番」= 最終製品番号 を採番。
#       例)11-00001, 11-00002 …  QR内容はこのシリアル。
#   ・その同じQRをスキャン = 消尽(-1)。個体は in_stock→consumed。
#       消尽済みQVを再スキャンしても二重差引はしない。
#   テーブル: inv_item / inv_unit / inv_tx  (migrate_inventory_v2.py で作成)
# --------------------------------------------------------------------------


@app.get("/invscan")
def page_invscan():
    """QRシリアルを読み取って在庫を消尽する現場用スキャン画面。"""
    return FileResponse(os.path.join(FRONTEND_DIR, "invscan.html"))


@app.get("/invlabel/{serial}")
def page_invlabel(serial: str):
    """29×90mm QR在庫ラベル(QR=シリアル + 品名)。?print=1 で自動印刷。"""
    return FileResponse(os.path.join(FRONTEND_DIR, "invlabel.html"))


@app.get("/api/inventory/label/{serial}")
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


@app.post("/api/inventory/scan")
def api_inv_scan(body: InvScanIn):
    """QRシリアルをスキャン → 在庫-1・個体を消尽に。二重差引はしない。"""
    serial = (body.code or "").strip().upper()
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
                    (body.worker, serial))
        row = cur.fetchone()
        if row:
            cur.execute("INSERT INTO inv_tx (code, serial, delta, reason, balance_after, worker) "
                        "VALUES (%s,%s,-1,'consume',%s,%s)", (row["code"], serial, row["remain"], body.worker))
            conn.commit()
            return {"ok": True, "serial": serial, "name": row["name"], "unit": row["unit"],
                    "balance": row["remain"], "low": row["remain"] <= row["reorder_point"]}
        cur.execute("SELECT status FROM inv_unit WHERE serial=%s", (serial,))
        u = cur.fetchone()
        conn.rollback()
    if u and u["status"] == "consumed":
        return {"ok": False, "reason": "既に消尽済みのQR(二重差引なし)", "serial": serial}
    return {"ok": False, "reason": "未登録のQR", "serial": serial}


# ---- 管理: 品目一覧 / QR発行(入庫) / 調整 / 発注点 / 履歴 / 品目CRUD ----
@app.get("/api/admin/inv")
def admin_inv_list(_=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM inv_item WHERE active ORDER BY group_no, sort_order, code")
        rows = cur.fetchall()
    items = [{"code": r["code"], "category": r["category"], "group_no": r["group_no"],
              "group_name": r["group_name"], "name": r["name"], "fabric_type": r["fabric_type"],
              "flame": r["flame"], "unit": r["unit"], "remain": r["remain"], "cap": r["capacity"],
              "reorder": r["reorder_point"], "low": r["remain"] <= r["reorder_point"]} for r in rows]
    return {"groups": [{"no": g[0], "name": g[1]} for g in INV_GROUPS], "items": items}


@app.post("/api/admin/inv/{code}/issue")
def admin_inv_issue(code: str, body: InvIssueIn, _=Depends(require_admin)):
    """QR発行 = 入庫(+count)。シリアル(コード-連番)を採番して返す。"""
    n = max(1, min(200, int(body.count or 1)))
    serials = []
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT code, name, unit FROM inv_item WHERE code=%s AND active FOR UPDATE", (code,))
        it = cur.fetchone()
        if not it:
            raise HTTPException(404, f"品目が見つかりません: {code}")
        for _i in range(n):
            cur.execute("""WITH nx AS (SELECT COALESCE(MAX(seq),0)+1 AS s FROM inv_unit WHERE code=%s)
                           INSERT INTO inv_unit (code, seq, serial)
                           SELECT %s, nx.s, %s || LPAD(nx.s::text, 5, '0') FROM nx
                           RETURNING serial""", (code, code, code + "-"))
            serials.append(cur.fetchone()["serial"])
        cur.execute("UPDATE inv_item SET remain = remain + %s WHERE code=%s RETURNING remain", (n, code))
        bal = cur.fetchone()["remain"]
        for s in serials:
            cur.execute("INSERT INTO inv_tx (code, serial, delta, reason, balance_after, worker) "
                        "VALUES (%s,%s,1,'issue',%s,%s)", (code, s, bal, body.worker))
        conn.commit()
    for s in serials:
        html_content = render_inventory_label(code=code, name=it["name"], serial=s, unit=it["unit"])
        silent_print_html(html_content, "inventory_printer")
    return {"ok": True, "code": code, "name": it["name"], "unit": it["unit"],
            "serials": serials, "balance": bal}


@app.post("/api/admin/inv/{code}/adjust")
def admin_inv_adjust(code: str, body: InvAdjustIn, _=Depends(require_admin)):
    """手動補正(棚卸差異など)。シリアルは発行しない。"""
    if not body.delta:
        return {"ok": True}
    with db() as conn, conn.cursor() as cur:
        cur.execute("UPDATE inv_item SET remain = GREATEST(0, remain + %s) WHERE code=%s AND active RETURNING remain",
                    (body.delta, code))
        r = cur.fetchone()
        if not r:
            raise HTTPException(404, "品目が見つかりません")
        cur.execute("INSERT INTO inv_tx (code, delta, reason, balance_after, note, worker) "
                    "VALUES (%s,%s,'adjust',%s,%s,%s)", (code, body.delta, r["remain"], body.note, body.worker))
        conn.commit()
    return {"ok": True, "balance": r["remain"]}


@app.post("/api/admin/inv/{code}/reorder")
def admin_inv_reorder(code: str, body: InvReorderIn, _=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        cur.execute("UPDATE inv_item SET reorder_point=%s WHERE code=%s", (max(0, body.reorder_point), code))
        conn.commit()
    return {"ok": True}


@app.get("/api/admin/inv/history")
def admin_inv_history(limit: int = 300, _=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        cur.execute("""SELECT t.created_at, t.code, i.name, t.serial, t.delta, t.reason,
                              t.balance_after, t.note, t.worker
                       FROM inv_tx t LEFT JOIN inv_item i ON i.code = t.code
                       ORDER BY t.created_at DESC LIMIT %s""", (limit,))
        rows = cur.fetchall()
    RJA = {"issue": "発行(入庫)", "consume": "消尽", "adjust": "調整"}
    return [{"t": r["created_at"].strftime("%Y-%m-%d %H:%M"), "code": r["code"], "name": r["name"],
             "serial": r["serial"], "delta": r["delta"], "reason": RJA.get(r["reason"], r["reason"]),
             "balance": r["balance_after"], "note": r["note"], "worker": r["worker"]} for r in rows]


@app.post("/api/admin/inv/item")
def admin_inv_item_create(body: InvItemIn, _=Depends(require_admin)):
    unit = body.unit or ("ロール" if body.category == "fabric" else "箱")
    so = int(body.code) if body.code.isdigit() else 999
    with db() as conn, conn.cursor() as cur:
        try:
            cur.execute("""INSERT INTO inv_item (code, category, group_no, group_name, name,
                             fabric_type, flame, unit, sort_order)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (body.code, body.category, body.group_no, body.group_name, body.name,
                         body.fabric_type, body.flame, unit, so))
            conn.commit()
        except Exception as e:
            raise HTTPException(400, f"追加エラー: {str(e).splitlines()[0]}")
    return {"ok": True}


@app.delete("/api/admin/inv/item/{code}")
def admin_inv_item_delete(code: str, _=Depends(require_admin)):
    """在庫履歴を保つため論理削除(active=false)。"""
    with db() as conn, conn.cursor() as cur:
        cur.execute("UPDATE inv_item SET active=FALSE WHERE code=%s", (code,))
        n = cur.rowcount
        conn.commit()
    if not n:
        raise HTTPException(404, "品目が見つかりません")
    return {"ok": True}


# =============================================================================
# 発注(仕入れ): 依頼 → 資材部へメール → 発注登録(到着予定日) → 入荷
# =============================================================================


@app.post("/api/admin/purchase")
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


@app.get("/api/admin/purchase")
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


@app.post("/api/admin/purchase/{po_id}/order")
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


@app.post("/api/admin/purchase/{po_id}/arrive")
def admin_purchase_arrive(po_id: int, _=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        cur.execute("""UPDATE purchase_order SET status='arrived', arrived_at=now()
                       WHERE id=%s AND status='ordered' RETURNING id""", (po_id,))
        r = cur.fetchone()
        if not r:
            raise HTTPException(404, "発注済の対象が見つかりません")
        conn.commit()
    return {"ok": True}


@app.post("/api/admin/purchase/{po_id}/cancel")
def admin_purchase_cancel(po_id: int, _=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        cur.execute("""UPDATE purchase_order SET status='cancelled'
                       WHERE id=%s AND status IN ('requested','ordered') RETURNING id""", (po_id,))
        r = cur.fetchone()
        if not r:
            raise HTTPException(404, "取消できる対象が見つかりません")
        conn.commit()
    return {"ok": True}


@app.get("/api/admin/purchase/settings")
def admin_purchase_settings_get(_=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        cfg = _smtp_config(cur)
    cfg["pass_set"] = bool(cfg.pop("pass"))   # パスワードは返さず設定有無だけ
    return cfg


@app.post("/api/admin/purchase/settings")
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


# ---- 注文 ----------------------------------------------------------------
@app.get("/api/admin/orders")
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


@app.get("/api/admin/orders/{order_no}")
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


@app.patch("/api/admin/orders/{order_no}")
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


@app.post("/api/admin/orders/{order_no}/cancel")
def admin_order_cancel(order_no: str, _=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        cur.execute("UPDATE orders SET order_status='cancelled' WHERE order_no=%s", (order_no,))
        n = cur.rowcount
        conn.commit()
    if n == 0:
        raise HTTPException(404, "注文が見つかりません")
    return {"ok": True}


@app.patch("/api/admin/items/{barcode}/stage")
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


# ---- 出荷 ----------------------------------------------------------------
@app.get("/api/admin/shipments")
def admin_shipments(_=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        cur.execute("""SELECT s.*, o.order_no, o.customer_name FROM shipments s
                       JOIN orders o ON o.id=s.order_id ORDER BY s.created_at DESC LIMIT 200""")
        rows = cur.fetchall()
    return [{"order_no": r["order_no"], "customer_name": r["customer_name"], "shipment_no": r["shipment_no"],
             "tracking_no": r["tracking_no"], "shipping_status": r["shipping_status"],
             "bizlogi_status": r["bizlogi_status"], "package_count": r["package_count"]} for r in rows]


@app.post("/api/admin/shipments")
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
@app.get("/api/admin/prints")
def admin_prints(_=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        cur.execute("""SELECT p.*, o.order_no FROM print_jobs p LEFT JOIN orders o ON o.id=p.order_id
                       ORDER BY p.id DESC LIMIT 200""")
        rows = cur.fetchall()
    return [{"id": r["id"], "order_no": r["order_no"], "target": r["target_type"], "printer": r["printer_type"],
             "status": r["status"], "error": r["error_message"],
             "printed_at": r["printed_at"].strftime("%m/%d %H:%M") if r["printed_at"] else ""} for r in rows]


@app.get("/api/admin/sync-logs")
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


@app.get("/api/admin/fire-report")
def admin_fire_report(month: str = Query(...), _=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        rows = _fire_rows(cur, month)
    return [{"order_no": r["order_no"], "sold_at": str(r["sold_at"]), "channel": r["channel"],
             "product_type": r["product_type"], "fabric": r["fabric_type"],
             "size": size_str(r["width_mm"], r["height_mm"]), "quantity": r["quantity"],
             "fire_cert_no": r["fire_cert_no"], "buyer": r["customer_name"], "address": r["address"]} for r in rows]


@app.get("/api/admin/fire-report.csv")
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
@app.get("/api/admin/stats")
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
@app.get("/api/admin/export/orders.csv")
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


@app.get("/api/admin/export/inventory.csv")
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


# ---- 設定 ----------------------------------------------------------------
@app.get("/api/admin/settings")
def admin_settings_get(_=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT key, value FROM settings ORDER BY key")
        rows = {r["key"]: r["value"] for r in cur.fetchall()}
    rows.pop("admin_password", None)   # パスワードは返さない
    return rows


@app.post("/api/admin/settings")
def admin_settings_set(body: SettingsIn, _=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        for k, v in body.values.items():
            cur.execute("""INSERT INTO settings (key, value, updated_at) VALUES (%s,%s,now())
                           ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=now()""", (k, str(v)))
        conn.commit()
    return {"ok": True}


# =============================================================================
# DB ビューア (管理者) — 任意テーブルを閲覧 + セル編集
# =============================================================================
from psycopg import sql as _sql


def _col_types(cur, table):
    cur.execute("""SELECT column_name, udt_name FROM information_schema.columns
                   WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position""", (table,))
    return {r["column_name"]: r["udt_name"] for r in cur.fetchall()}


@app.get("/api/admin/db/tables")
def db_tables(_=Depends(require_admin)):
    out = []
    with db() as conn, conn.cursor() as cur:
        for t, pk in DB_TABLES.items():
            cur.execute(_sql.SQL("SELECT count(*) AS c FROM {}").format(_sql.Identifier(t)))
            out.append({"table": t, "pk": pk, "count": cur.fetchone()["c"]})
    return out


@app.get("/api/admin/db/{table}")
def db_view(table: str, limit: int = 300, _=Depends(require_admin)):
    if table not in DB_TABLES:
        raise HTTPException(404, "不明なテーブル")
    with db() as conn, conn.cursor() as cur:
        columns = list(_col_types(cur, table).keys())
        cur.execute(_sql.SQL("SELECT * FROM {} ORDER BY 1 DESC LIMIT %s").format(_sql.Identifier(table)), (limit,))
        rows = cur.fetchall()
    return {"table": table, "pk": DB_TABLES[table], "columns": columns, "rows": rows}


@app.patch("/api/admin/db/{table}")
def db_edit(table: str, body: DbEdit, _=Depends(require_admin)):
    if table not in DB_TABLES:
        raise HTTPException(404, "不明なテーブル")
    pk = DB_TABLES[table]
    with db() as conn, conn.cursor() as cur:
        ct = _col_types(cur, table)
        sets, vals = [], []
        for col, v in body.changes.items():
            if col not in ct or col == pk:
                continue
            if v is None or v == "":
                sets.append(_sql.SQL("{}=NULL").format(_sql.Identifier(col)))
            else:
                sets.append(_sql.SQL("{}=%s::{}").format(_sql.Identifier(col), _sql.SQL(ct[col])))
                vals.append(v)
        if not sets:
            return {"ok": True, "updated": 0}
        q = _sql.SQL("UPDATE {} SET {} WHERE {}=%s::{}").format(
            _sql.Identifier(table), _sql.SQL(", ").join(sets),
            _sql.Identifier(pk), _sql.SQL(ct[pk]))
        try:
            cur.execute(q, vals + [body.pk_value])
            n = cur.rowcount
            conn.commit()
        except Exception as e:
            raise HTTPException(400, f"更新エラー: {str(e).splitlines()[0]}")
    return {"ok": True, "updated": n}


# =============================================================================
# 工程別モニター (裁断/ミシン/ハトメ) — 各工程にモニター+スキャナ
#   スキャン=進行(その工程の対象のみ)。モニターは待機/作業中/実績を表示。
#   工程ごとの stage: queue(待機) → wip(作業中) → done(完了=次工程の待機)
# =============================================================================


def stage_to_proc(stage: int):
    """現在のstage番号から、それがどの工程のqueue/wipに該当するかを自動判定する。
       1台のPCで複数のモニター画面(cutting/sewing/eyelet)を同時に開いている場合、
       スキャナーの入力はフォーカスが当たっている画面にしか届かない。
       URLのprocだけで判定すると「違う画面が選択されている」だけでエラーになるため、
       実際のDB上のstageから工程を逆引きして、どの画面がアクティブでも正しく処理できるようにする。"""
    for key, info in MON_PROC.items():
        if stage in (info["queue"], info["wip"]):
            return key, info
    return None, None


def _proc_fields(proc, row):
    """モニター画面(cutting/sewing/eyelet)に必要な情報を [ラベル, 値] で返す。
       作業者画面(worker_payload)の内容と揃えてある。"""
    s = item_sides(row)
    skirt_any = any(kind == "skirt" for kind, _ in s.values())
    if proc == "cutting":
        return [["サイズ", size_str(row["width_mm"], row["height_mm"])],
                ["生地", row["fabric_type"]],
                ["スカート", "有り" if skirt_any else "無し"]]
    if proc == "sewing":
        velcro = [SIDE_JA[k] for k, (kind, _) in s.items() if kind == "velcro"]
        return [["マジックテープ", "有り" + ("(" + "・".join(velcro) + ")" if velcro else "")],
                ["ベルクロ種別", VELCRO_JA.get(row.get("velcro_type"), "-")],
                ["スカート", "有り" if skirt_any else "無し"],
                ["スカート取付", SKIRT_ATTACH_JA.get(row.get("skirt_attachment"), "なし") if skirt_any else "なし"],
                ["スカート継ぎ目", ("シームレス" if row.get("skirt_no_seam") else "通常") if skirt_any else "なし"]]
    if proc == "eyelet":
        return [["上辺", eyelet_val(*s["top"])], ["下辺", eyelet_val(*s["bottom"])],
                ["左辺", eyelet_val(*s["left"])], ["右辺", eyelet_val(*s["right"])],
                ["配置方式", EYELET_METHOD_JA.get(row.get("eyelet_method"), "なし")]]
    return []


def _eyelet_diagram_info(row):
    """ハトメモニター画面の配置図に必要な生データ(方式コード/ピッチ)。"""
    s = item_sides(row)
    pitch = next((mm for kind, mm in s.values() if kind == "eyelet" and mm), None)
    return {"eyelet_method_code": row.get("eyelet_method"), "eyelet_pitch_mm": pitch}


@app.get("/monitor/{proc}")
def page_monitor(proc: str):
    if proc not in MON_PROC:
        raise HTTPException(404, "不明な工程 (cutting/sewing/eyelet)")
    return FileResponse(os.path.join(FRONTEND_DIR, "monitor.html"))


@app.get("/api/monitor/{proc}")
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


@app.post("/api/monitor/{proc}/scan")
def api_monitor_scan(proc: str, body: MonScan):
    if proc not in MON_PROC:
        raise HTTPException(404, "不明な工程")
    bc = body.barcode.strip()
    with db() as conn, conn.cursor() as cur:
        cur.execute("""SELECT oi.*, o.order_status FROM order_items oi JOIN orders o ON o.id=oi.order_id
                       WHERE oi.barcode=%s""", (bc,))
        it = cur.fetchone()
        if not it:
            return {"ok": False, "reason": "未登録バーコード", "barcode": bc}
        if it["order_status"] == "cancelled":
            return {"ok": False, "reason": "キャンセル済みの注文", "barcode": bc}
        cur_stage = it["current_stage"]
        # URLのproc(=どのモニター画面がスキャンを受けたか)ではなく、実際のstageから
        # 工程を自動判定する。これで複数モニターを1台のPCで開いていて、スキャン時に
        # 別の画面がフォーカスされていても正しい工程として処理される。
        actual_proc, info = stage_to_proc(cur_stage)
        if not info:
            return {"ok": False, "reason": f"対象外(現在: {STAGE_NAME.get(cur_stage, cur_stage)})",
                    "barcode": bc, "fabric": it["fabric_type"],
                    "size": size_str(it["width_mm"], it["height_mm"]),
                    "fields": _proc_fields(proc, it)}
        if cur_stage == info["queue"]:
            new, result, et = info["wip"], "開始", "start"
        else:  # cur_stage == info["wip"]
            new, result, et = info["done"], "完了", "complete"
        cur.execute("""UPDATE order_items SET current_stage=%s,
                         started_at=COALESCE(started_at, now()) WHERE id=%s""", (new, it["id"]))
        cur.execute("INSERT INTO scan_events (order_item_id, stage_no, event_type, station) VALUES (%s,%s,%s,%s)",
                    (it["id"], new, et, "monitor_" + actual_proc))
        conn.commit()
    out = {"ok": True, "result": result, "barcode": bc, "fabric": it["fabric_type"],
           "size": size_str(it["width_mm"], it["height_mm"]), "stage_name": STAGE_NAME.get(new, ""),
           "fields": _proc_fields(actual_proc, it)}
    if actual_proc == "eyelet":
        out.update(_eyelet_diagram_info(it))
    return out
    
# =============================================================================
# [통합] 내장 시리얼 바코드 스캐너 백그라운드 스레드 제어 (JSON 설정 기반)
# =============================================================================
import threading
import time
import re

import serial

# JSON 설정 파일을 읽어오는 함수
def load_scanner_config():
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scanner_config.json")
    if not os.path.exists(config_path):
        print(f"⚠️ 설정 파일({config_path})이 없습니다. 스캐너 연동 없이 시작합니다.")
        return []
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            print(f"📄 스캐너 설정 파일 로드 완료! (총 {len(config)}대 스캐너 연결 예정)")
            return config
    except Exception as e:
        print(f"❌ 설정 파일 읽기 오류: {e}")
        return []

def _serial_reader_worker(config):
    port = config.get("port")
    baudrate = config.get("baudrate", 9600)
    scan_type = config.get("type")
    proc = config.get("proc")
    
    while True:
        try:
            print(f"🔌 [{port}] 시리얼 포트 연결 시도 중...")
            with serial.Serial(port, baudrate, timeout=1) as ser:
                print(f"🟢 [{port}] 연결 성공! 바코드 대기 중... (매핑: {scan_type} / {proc or '없음'})")
                
                while ser.is_open:
                    if ser.in_waiting > 0:
                        barcode_data = ser.readline().decode('utf-8').strip()
                        if barcode_data:
                            print(f"📥 [{port}] 바코드 스캔 감지: {barcode_data}")
                            
                            try:
                                # 🌟 1. 재고 바코드인지 먼저 검사 (형식: 숫자2~4자리 - 숫자3~6자리)
                                if re.match(r"^\d{2,4}-\d{3,6}$", barcode_data):
                                    body = InvScanIn(code=barcode_data)
                                    result = api_inv_scan(body)  # 재고 차감 함수 직접 호출
                                    print(f"📦 [{port}] 재고 스캔 처리 완료: {result}")
                                    continue  # 재고 처리를 완료했으므로 아래의 공정 진행 로직은 건너뜀 (중요)
                                
                                # 🌟 2. 일반 생산/공정 바코드인 경우 기존 로직 수행
                                if scan_type == "monitor":
                                    body = MonScan(barcode=barcode_data)
                                    result = api_monitor_scan(proc, body)
                                    print(f"✅ [{port}] 모니터 스캔 처리 완료: {result}")
                                    if result.get("ok") and result.get("stage_name") == "ハトメ完了":
                                        print(f"📦 [{port}] 제품 {barcode_data} 최종 공정 완료 -> 송장 자동 출력 개시")
                                        
                                        with db() as conn, conn.cursor() as cur:
                                            # 1. order_items에서는 order_id만 조회합니다. (order_no는 이 테이블에 없음)
                                            cur.execute("SELECT order_id FROM order_items WHERE barcode=%s", (barcode_data,))
                                            item_info = cur.fetchone()
                                            
                                            if item_info:
                                                order_id = item_info["order_id"]
                                                
                                                # 2. orders 테이블에서 고유 id로 전체 주문 정보와 order_no를 가져옵니다.
                                                cur.execute("SELECT * FROM orders WHERE id=%s", (order_id,))
                                                order_info = cur.fetchone() or {}
                                                order_no = order_info.get("order_no", "UNKNOWN")
                                                
                                                # 3. 해당 주문의 전체 제품 목록 가져오기
                                                cur.execute("SELECT barcode, fabric_type as fabric, width_mm, height_mm FROM order_items WHERE order_id=%s", (order_id,))
                                                items_db = cur.fetchall()
                                                items_list = [{"barcode": i["barcode"], "fabric": i["fabric"], "size": f"W{i['width_mm']}xH{i['height_mm']}"} for i in items_db]
                                                
                                                # 4. HTML 생성 및 출력
                                                html_content = render_shipping_slip(order_no=order_no, order_info=order_info, items=items_list)
                                                silent_print_html(html_content, "invoice_printer")
                                elif scan_type == "worker":
                                    result = _move(barcode_data, +1)
                                    print(f"✅ [{port}] 작업자 스캔 처리 완료: {result['order_no']} (Stage: {result['stage']})")
                                    
                            except HTTPException as he:
                                print(f"⚠️ [{port}] 거부됨 ({he.status_code}): {he.detail}")
                            except Exception as e:
                                print(f"❌ [{port}] DB 처리 오류: {e}")
                                
                    time.sleep(0.05)
                    
        except serial.SerialException as e:
            print(f"❌ [{port}] 연결 실패 또는 유실 (5초 후 재시도)...")
            time.sleep(5)
        except Exception as e:
            time.sleep(5)

@app.on_event("startup")
def start_serial_scanners():
    """서버 시작 시 JSON 파일을 읽고 백그라운드 스레드를 구동합니다."""
    # 하드코딩 대신 함수를 호출해 JSON 데이터를 가져옵니다.
    ports_config = load_scanner_config()
    
    if ports_config:
        print("🚀 [System] 통합 시리얼 포트 백그라운드 리스너 구동을 시작합니다.")
        for config in ports_config:
            t = threading.Thread(target=_serial_reader_worker, args=(config,), daemon=True)
            t.start()