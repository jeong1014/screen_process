"""
スクリーン原団 工場工程管理システム — FastAPI バックエンド (v2)
worker_v5.html / dashboard_v2_2.html の API契約に整合。

役割: ブラウザHTML(入力/作業者/ダッシュボード)と PostgreSQL の仲介。
  進行状態 stage(0〜8) を order_items.current_stage で一元管理。
  「注文番号(製品番号)」= order_items.barcode。

実行:  uvicorn app:app --reload --host 0.0.0.0 --port 8000
必要:  pip install fastapi uvicorn "psycopg[binary]"
DB  :  環境変数 DATABASE_URL
"""

import os
import json
from datetime import date, datetime
from typing import Optional, List

import psycopg
from psycopg.rows import dict_row
from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ===== 設定 =====
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/screen")
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
MAX_STAGE = 8

app = FastAPI(title="スクリーン原団 工程管理 v2")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def db():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


# =============================================================================
# 表示用フォーマット (DBの構造データ → 各画面が期待する文字列)
# =============================================================================
SIDE_JA = {"top": "上", "bottom": "下", "left": "左", "right": "右"}
PROC_BY_STAGE = {1: "裁断", 2: "裁断", 3: "ミシン", 4: "ミシン",
                 5: "ハトメ", 6: "ハトメ", 7: "梱包", 8: "梱包"}


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


def qty_str(product_type: str, q: int) -> str:
    if product_type == "two_sheet_set":
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


def worker_payload(row):
    """作業者画面 GET /api/orders/{no} の応答形。"""
    s = item_sides(row)
    velcro_sides = [SIDE_JA[k] for k, (kind, _) in s.items() if kind == "velcro"]
    skirt_any = any(kind == "skirt" for kind, _ in s.values())
    return {
        "order_no": row["barcode"],
        "fabric": row["fabric_type"],
        "size": size_str(row["width_mm"], row["height_mm"]),
        "magictape": "・".join(velcro_sides) if velcro_sides else "なし",
        "skirt": "有り" if skirt_any else "無し",
        "e_top":    eyelet_val(*s["top"]),
        "e_bottom": eyelet_val(*s["bottom"]),
        "e_left":   eyelet_val(*s["left"]),
        "e_right":  eyelet_val(*s["right"]),
        "stage": row["current_stage"],
    }


def board_status(stage: int):
    """stage(0〜8) → 各工程の working/wait/done。"""
    def st(done_at, wip_at):
        return "done" if stage >= done_at else ("working" if stage == wip_at else "wait")
    return {
        "cutting": st(2, 1),
        "sewing":  st(4, 3),
        "eyelet":  st(6, 5),
        "packing": st(8, 7),
    }


# =============================================================================
# 入力モデル
# =============================================================================
class ItemIn(BaseModel):
    product_type: str = "single"
    fabric_type: str = "LN"
    width_mm: int
    height_mm: int
    quantity: int = 1
    process_top: str = "none"
    process_top_mm: Optional[int] = None
    process_bottom: str = "none"
    process_bottom_mm: Optional[int] = None
    process_left: str = "none"
    process_left_mm: Optional[int] = None
    process_right: str = "none"
    process_right_mm: Optional[int] = None
    fire_cert_no: Optional[str] = None


class OrderIn(BaseModel):
    channel: str
    customer_name: str
    postal_code: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    payment_status: str = "paid"
    mall_order_no: Optional[str] = None
    ordered_at: Optional[str] = None
    items: List[ItemIn] = Field(default_factory=list)


class ScanIn(BaseModel):
    order_no: str            # = barcode


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
        created = []
        for i, it in enumerate(order.items, start=1):
            barcode = f"{order_no}{it.fabric_type}{i:02d}"   # CDI260713001SDP01
            cur.execute(
                """INSERT INTO order_items (order_id, item_no, barcode, product_type, fabric_type,
                     width_mm, height_mm, quantity, process_top, process_top_mm, process_bottom,
                     process_bottom_mm, process_left, process_left_mm, process_right, process_right_mm,
                     fire_cert_no)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING barcode""",
                (order_id, i, barcode, it.product_type, it.fabric_type, it.width_mm, it.height_mm,
                 it.quantity, it.process_top, it.process_top_mm, it.process_bottom, it.process_bottom_mm,
                 it.process_left, it.process_left_mm, it.process_right, it.process_right_mm, it.fire_cert_no),
            )
            created.append(cur.fetchone()["barcode"])
        conn.commit()
    return {"order_no": order_no, "barcodes": created}


# =============================================================================
# 作業者画面
# =============================================================================
def _fetch_item(cur, barcode):
    cur.execute("SELECT * FROM order_items WHERE barcode=%s", (barcode,))
    return cur.fetchone()


@app.get("/api/orders/{order_no}")
def get_order(order_no: str):
    """作業者画面: バーコードで製品情報+stage を取得。"""
    with db() as conn, conn.cursor() as cur:
        row = _fetch_item(cur, order_no)
    if not row:
        raise HTTPException(404, f"製品番号が見つかりません: {order_no}")
    return worker_payload(row)


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
        conn.commit()
    return worker_payload(row)


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
            "qty": qty_str(r["product_type"], r["quantity"]),
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
            ev, text = "ship", "梱包 完了(出荷準備)"
        elif stage % 2 == 0 and stage > 0:
            ev, text = "done", f"{proc} 完了"
        else:
            ev, text = "start", f"{proc} 開始"
        out.append({"t": r["scanned_at"].strftime("%H:%M"), "order_no": r["barcode"], "ev": ev, "text": text})
    return out


@app.get("/api/inventory")
def api_inventory():
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT fabric_type, remain_rolls, capacity_rolls FROM fabric_inventory ORDER BY fabric_type")
        rows = cur.fetchall()
    return [{"fabric": r["fabric_type"], "remain": r["remain_rolls"], "cap": r["capacity_rolls"]} for r in rows]


@app.get("/api/accessories")
def api_accessories():
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT name, remain, capacity, unit FROM accessories ORDER BY sort_order, id")
        rows = cur.fetchall()
    return [{"name": r["name"], "remain": r["remain"], "cap": r["capacity"], "unit": r["unit"]} for r in rows]


if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


# =============================================================================
# ラベル自動化: /label/{barcode} でラベルを開くと DB から自動で埋まる
# =============================================================================
@app.get("/label/{barcode}")
def page_label(barcode: str):
    return FileResponse(os.path.join(FRONTEND_DIR, "label.html"))


# 加工種別(DB) → ラベル v6 の processing 形式
_PRODUCT_JP = {"single": "1枚", "two_sheet_set": "2枚セット", "skirt": "スカート"}


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
from fastapi import Header, Query
from fastapi.responses import Response
import csv, io

STAGE_NAME = {0: "受付", 1: "裁断中", 2: "裁断完了", 3: "ミシン中", 4: "ミシン完了",
              5: "ハトメ中", 6: "ハトメ完了", 7: "梱包中", 8: "梱包完了"}


def _get_setting(cur, key, default=None):
    cur.execute("SELECT value FROM settings WHERE key=%s", (key,))
    r = cur.fetchone()
    return r["value"] if r else default


def _admin_password(cur):
    return _get_setting(cur, "admin_password", "1234")


def require_admin(x_admin_pass: str = Header(default="")):
    with db() as conn, conn.cursor() as cur:
        if x_admin_pass != _admin_password(cur):
            raise HTTPException(401, "認証が必要です(パスワード)")
    return True


def _check_pw_query(pw: str):
    """ダウンロードリンク用: クエリ ?pw= で認証。"""
    with db() as conn, conn.cursor() as cur:
        if pw != _admin_password(cur):
            raise HTTPException(401, "認証が必要です(パスワード)")


@app.get("/admin")
def page_admin():
    return FileResponse(os.path.join(FRONTEND_DIR, "admin.html"))


class LoginIn(BaseModel):
    password: str


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


class AdjustIn(BaseModel):
    kind: str                      # fabric / accessory
    id: str                        # fabric_type(LN..) or accessory_id
    delta: int                     # +入庫 / −消尽
    reason: str = "adjust"         # in / out / adjust
    note: Optional[str] = None
    worker: Optional[str] = None


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


class ReorderIn(BaseModel):
    kind: str
    id: str
    reorder_point: int


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


class AccIn(BaseModel):
    name: str
    unit: str = "個"
    capacity: int = 10
    reorder_point: int = 5


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


class OrderPatch(BaseModel):
    order_no: Optional[str] = None          # 新しい注文番号(変更時)
    customer_name: Optional[str] = None
    postal_code: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    payment_status: Optional[str] = None


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


class StageFix(BaseModel):
    stage: int


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


class ShipIn(BaseModel):
    order_no: str
    tracking_no: Optional[str] = None
    shipping_status: Optional[str] = None
    bizlogi_status: Optional[str] = None
    package_count: Optional[int] = None


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


class SettingsIn(BaseModel):
    values: dict


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

DB_TABLES = {
    "orders": "id", "order_items": "id", "scan_events": "id", "shipments": "id",
    "print_jobs": "id", "sync_logs": "id", "fabric_inventory": "fabric_type",
    "accessories": "id", "inventory_transactions": "id", "settings": "key",
    "production_stages": "stage_no", "fire_safety_reports": "id", "fire_safety_report_items": "id",
}


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


class DbEdit(BaseModel):
    pk_value: str
    changes: dict


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
MON_PROC = {
    "cutting": {"ja": "裁断",   "ko": "재단",   "queue": 0, "wip": 1, "done": 2},
    "sewing":  {"ja": "ミシン", "ko": "미싱",   "queue": 2, "wip": 3, "done": 4},
    "eyelet":  {"ja": "ハトメ", "ko": "하토메", "queue": 4, "wip": 5, "done": 6},
}


def _proc_fields(proc, row):
    """作業者画面と同じ、その工程に必要な情報を [ラベル, 値] で返す。"""
    s = item_sides(row)
    if proc == "cutting":
        return [["サイズ", size_str(row["width_mm"], row["height_mm"])],
                ["生地", row["fabric_type"]]]
    if proc == "sewing":
        velcro = [SIDE_JA[k] for k, (kind, _) in s.items() if kind == "velcro"]
        skirt = any(kind == "skirt" for kind, _ in s.values())
        return [["マジックテープ", "・".join(velcro) if velcro else "なし"],
                ["スカート", "有り" if skirt else "無し"]]
    if proc == "eyelet":
        return [["上面", eyelet_val(*s["top"])], ["下面", eyelet_val(*s["bottom"])],
                ["左面", eyelet_val(*s["left"])], ["右面", eyelet_val(*s["right"])]]
    return []


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
    return {"proc": proc, "name_ja": info["ja"], "name_ko": info["ko"],
            "queue": queue, "wip": wip, "queue_count": len(queue), "wip_count": len(wip),
            "today_done": today_done, "last": last,
            "server_time": datetime.now().strftime("%H:%M:%S")}


class MonScan(BaseModel):
    barcode: str


@app.post("/api/monitor/{proc}/scan")
def api_monitor_scan(proc: str, body: MonScan):
    if proc not in MON_PROC:
        raise HTTPException(404, "不明な工程")
    info = MON_PROC[proc]
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
        if cur_stage == info["queue"]:
            new, result, et = info["wip"], "開始", "start"
        elif cur_stage == info["wip"]:
            new, result, et = info["done"], "完了", "complete"
        else:
            return {"ok": False, "reason": f"この工程の対象外(現在: {STAGE_NAME.get(cur_stage, cur_stage)})",
                    "barcode": bc, "fabric": it["fabric_type"],
                    "size": size_str(it["width_mm"], it["height_mm"]),
                    "fields": _proc_fields(proc, it)}
        cur.execute("""UPDATE order_items SET current_stage=%s,
                         started_at=COALESCE(started_at, now()) WHERE id=%s""", (new, it["id"]))
        cur.execute("INSERT INTO scan_events (order_item_id, stage_no, event_type, station) VALUES (%s,%s,%s,%s)",
                    (it["id"], new, et, "monitor_" + proc))
        conn.commit()
    return {"ok": True, "result": result, "barcode": bc, "fabric": it["fabric_type"],
            "size": size_str(it["width_mm"], it["height_mm"]), "stage_name": STAGE_NAME.get(new, ""),
            "fields": _proc_fields(proc, it)}
