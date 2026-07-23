"""
設定と定数 — 環境依存の値と、ロジックを持たない定数テーブルだけを置く。

ここには関数・DB接続・FastAPI 依存を入れないこと。
このモジュールは他のどのモジュールも import してよい最下層に位置する。
"""

import os

# ===== 環境 =====
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:1234@localhost:5432/screen"
)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
PRINTER_CONFIG_PATH = os.path.join(BASE_DIR, "printer_config.json")
SCANNER_CONFIG_PATH = os.path.join(BASE_DIR, "scanner_config.json")
SUMATRA_PATH = os.path.join(BASE_DIR, "SumatraPDF.exe")

# ===== ラベル自動印刷のエンジン =====
#   "chrome"    … label_gorilla.html を Chrome(ヘッドレス)で PDF 化して印刷。
#                 画面(手動印刷)と全く同じ見た目になる。Chrome が無ければ自動で
#                 weasyprint にフォールバックするので、ラベルが出ないことはない。
#   "weasyprint"… 従来どおり print_templates.py を WeasyPrint で PDF 化。
#   問題が出たら下を "weasyprint" にすれば即座に元の挙動へ戻せる。
LABEL_PRINT_ENGINE = os.environ.get("LABEL_PRINT_ENGINE", "chrome")

# 自動印刷はサーバー自身の /label ページを Chrome で開いて刷る。そのための自分宛URL。
# uvicorn を別ポートで動かす場合は環境変数 SERVER_BASE_URL で上書きする。
SERVER_BASE_URL = os.environ.get("SERVER_BASE_URL", "http://127.0.0.1:8000")

# Chrome / Edge の実行ファイル候補(Windows)。最初に見つかったものを使う。
CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

# 進行状態 stage の最大値 (0=受付 … 6=ハトメ完了)
MAX_STAGE = 6


# ===== 表示用ラベル =====
SIDE_JA = {"top": "上", "bottom": "下", "left": "左", "right": "右"}
PROC_BY_STAGE = {1: "裁断", 2: "裁断", 3: "ミシン", 4: "ミシン",
                 5: "ハトメ", 6: "ハトメ"}

# 販売サイトのオプション体系(2026-07 統合)に合わせた表示用ラベル
VELCRO_JA = {"male": "オス", "female": "メス"}
SKIRT_ATTACH_JA = {"sew": "縫い付け", "velcro": "マジックテープ"}
EYELET_METHOD_JA = {"A": "方式A(コーナー基準)", "B": "方式B(間隔均等)", "C": "方式C(未定)"}
# 2枚セット(two_sheet_set)の表面/裏面区分(裁断/ミシン/ハトメを2回スキャンするため2行に分けて管理)
SHEET_SIDE_JA = {"front": "表面", "back": "裏面"}

STAGE_NAME = {0: "受付", 1: "裁断中", 2: "裁断完了", 3: "ミシン中", 4: "ミシン完了",
              5: "ハトメ中", 6: "ハトメ完了"}

# 加工種別(DB) → ラベル v6 の processing 形式
_PRODUCT_JP = {"single": "1枚", "two_sheet_set": "2枚セット", "skirt": "スカート"}


# ===== 工程別モニター =====
#   工程ごとの stage: queue(待機) → wip(作業中) → done(完了=次工程の待機)
MON_PROC = {
    "cutting": {"ja": "裁断",   "ko": "재단",   "queue": 0, "wip": 1, "done": 2},
    "sewing":  {"ja": "ミシン", "ko": "미싱",   "queue": 2, "wip": 3, "done": 4},
    "eyelet":  {"ja": "ハトメ", "ko": "하토메", "queue": 4, "wip": 5, "done": 6},
}


# ===== QR在庫 v2 =====
#   品目はエクセル準拠のコード(11〜61)で管理。原反=ロール / 付属品=箱。
#   7 = 消耗品(工場備品): プリンタのラベル紙・リボン・A4用紙など。
#       生産材料ではないので、ダッシュボードの原反/付属品パネルには出さない
#       (category='supply' で区別している)。発注依頼の仕組みはそのまま使える。
INV_GROUPS = [(1, "原反"), (2, "マジックテープ"), (3, "ウェビング"),
              (4, "アイレット"), (5, "糸"), (6, "カバー"), (7, "消耗品")]


# ===== ラベルの版(テンプレート) =====
#
#   新しいラベルを足す手順:
#     1. frontend/ に HTML を1枚置く(データの受け取り方は既存の label_gorilla.html と同じ)
#     2. 下の LABEL_TEMPLATES に1行足す
#     3. printer_config.json に printer で指定したキーを足す(別の用紙設定で印刷する場合)
#   ファイルが無い版は管理画面に「未作成」と出て選べないだけで、他に影響しない。
#
#   printer  : printer_config.json のキー。無ければ order_printer にフォールバック。
#   page     : 用紙サイズ(管理画面での案内表示用)
LABEL_TEMPLATES = {
    "standard": {
        "name": "標準(二つ折り)",
        "file": "label_gorilla.html",
        "printer": "order_printer",
        "page": "110 × 412mm(二つ折り)",
    },
    "small": {
        "name": "小型(縮小版)",
        "file": "label_small.html",
        "printer": "order_printer_small",
        "page": "未定(作成者に確認)",
    },
}
DEFAULT_LABEL_TEMPLATE = "standard"
LABEL_TEMPLATE_KEY = "label_template"      # settings テーブルのキー


# ===== DB ビューア対象テーブル → 主キー列 =====
DB_TABLES = {
    "orders": "id", "order_items": "id", "scan_events": "id", "shipments": "id",
    "print_jobs": "id", "sync_logs": "id", "fabric_inventory": "fabric_type",
    "accessories": "id", "inventory_transactions": "id", "settings": "key",
    "production_stages": "stage_no", "fire_safety_reports": "id", "fire_safety_report_items": "id",
    "inv_item": "code", "inv_unit": "id", "inv_tx": "id",
}
