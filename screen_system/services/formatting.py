"""
표시용 포맷 함수 모음 — DB 행(dict) → 각 화면이 기대하는 문자열/구조로 변환.

전부 순수 함수다. DB 접속도 FastAPI 의존도 없으므로 단위 테스트가 그대로 가능하다.
"""

from config import (
    SIDE_JA, VELCRO_JA, SKIRT_ATTACH_JA, EYELET_METHOD_JA, SHEET_SIDE_JA, MON_PROC,
)


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


def _proc(kind, mm):
    if kind == "eyelet":
        return {"type": "eyelet", "spacing": mm}
    if kind in ("skirt", "velcro"):
        return {"type": kind}
    return {"type": "none"}


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
