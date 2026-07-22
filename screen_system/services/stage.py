"""
공정 진행(stage) 핵심 로직 — 이 시스템의 심장부.

order_items.current_stage (0〜6) 를 단일 진실 공급원으로 삼아 진행/되돌리기를 처리한다.
호출 지점이 세 곳이라 라우트 핸들러가 아니라 서비스 함수로 둔다:
  1. POST /api/scan, /api/scan/undo   (작업자 화면)
  2. POST /api/monitor/{proc}/scan    (공정별 모니터)
  3. services/scanner.py              (시리얼 바코드 스캐너 백그라운드 스레드)

이 모듈은 routers 를 절대 import 하지 않는다. (순환 import 방지)
"""

from datetime import date

from fastapi import HTTPException

from config import MAX_STAGE, MON_PROC, STAGE_NAME
from db import db
from services.formatting import (
    worker_payload, size_str, stage_to_proc, _proc_fields, _eyelet_diagram_info,
)
from services.shipping import auto_print_shipping_slip, fetch_order_by_no


# =============================================================================
# 조회 헬퍼
# =============================================================================
def next_order_no(cur) -> str:
    ymd = date.today().strftime("%y%m%d")   # 例: 260713
    cur.execute("SELECT count(*) AS c FROM orders WHERE order_no LIKE %s", (f"CDI{ymd}%",))
    return f"CDI{ymd}{cur.fetchone()['c']+1:03d}"   # CDI260713001


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


def get_item_payload(order_no: str):
    """作業者画面: バーコードで製品情報+stage を取得。"""
    with db() as conn, conn.cursor() as cur:
        row = _fetch_item(cur, order_no)
        if not row:
            raise HTTPException(404, f"製品番号が見つかりません: {order_no}")
        pair_bc = _pair_barcode(cur, row)
    return worker_payload(row, pair_bc)


# =============================================================================
# 진행 / 되돌리기
# =============================================================================
def move_stage(order_no: str, delta: int):
    """stage 를 delta 만큼 이동. 최종 공정 완료 시 송장을 자동 출력한다."""
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

        if new_stage == MAX_STAGE and delta > 0:
            print(f"📦 제품 {order_no} ハトメ完了(최종) -> 송장 자동 출력 개시")
            # NOTE: 여기서 order_no 는 실제로는 order_items.barcode 다.
            #       orders.order_no 로 조회하므로 대부분 빈 dict 가 되어
            #       고객 정보 없이 인쇄된다. (기존 동작 유지 — 별건으로 수정 필요)
            order_info = fetch_order_by_no(cur, order_no)
            auto_print_shipping_slip(cur, order_no, row["order_id"], order_info)

    return worker_payload(row, pair_bc)


# =============================================================================
# 공정별 모니터 스캔
# =============================================================================
def monitor_scan(proc: str, barcode: str):
    if proc not in MON_PROC:
        raise HTTPException(404, "不明な工程")
    bc = barcode.strip()
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
