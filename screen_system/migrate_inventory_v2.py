"""
migrate_inventory_v2.py
  在庫を「品目コード + シリアルQR」方式へ移行する。
  - inv_item : 品目マスター(エクセル準拠, コード 11〜61 + 消耗品 71〜74)
  - inv_unit : シリアル個体(QR1枚 = 実物1本/1箱, in_stock/consumed)
  - inv_tx   : 入出庫履歴(発行=+1 / 消尽=-1)
  付属品の単位は全て「箱」、原反は「ロール」。

実行(UTF-8で安全に投入されます。psqlのファイル読込は文字化けするので必ずこれで):
    set DATABASE_URL=postgresql://postgres:パスワード@localhost:5432/screen
    python migrate_inventory_v2.py

再実行しても在庫数(remain/capacity/reorder_point)は保持し、名称等のマスター情報だけ更新します。
"""
import os
import psycopg

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:1234@localhost:5432/screen")

DDL = r"""
CREATE TABLE IF NOT EXISTS inv_item (
    code          TEXT PRIMARY KEY,                 -- '11'〜'61'
    category      TEXT NOT NULL,                     -- 'fabric' | 'accessory' | 'supply'
    group_no      SMALLINT NOT NULL,                 -- 1〜7
    group_name    TEXT NOT NULL,                     -- 原反 / マジックテープ ...
    name          TEXT NOT NULL,                     -- 品名
    fabric_type   TEXT,                              -- 'LN'|'DP'|'SDP' (原反のみ)
    flame         BOOLEAN,                           -- 防炎あり(true)/なし(false) 原反のみ
    unit          TEXT NOT NULL,                     -- 'ロール' | '箱'
    remain        INTEGER NOT NULL DEFAULT 0,
    capacity      INTEGER NOT NULL DEFAULT 10,
    reorder_point INTEGER NOT NULL DEFAULT 3,
    sort_order    INTEGER NOT NULL DEFAULT 0,
    active        BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS inv_unit (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code        TEXT NOT NULL REFERENCES inv_item(code),
    seq         INTEGER NOT NULL,                    -- コードごとの連番
    serial      TEXT NOT NULL UNIQUE,                -- '11-00001' = 最終製品番号
    status      TEXT NOT NULL DEFAULT 'in_stock',    -- in_stock | consumed
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    consumed_at TIMESTAMPTZ,
    worker      TEXT
);
CREATE INDEX IF NOT EXISTS idx_inv_unit_code   ON inv_unit(code);
CREATE INDEX IF NOT EXISTS idx_inv_unit_status ON inv_unit(status);

CREATE TABLE IF NOT EXISTS inv_tx (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code          TEXT NOT NULL,
    serial        TEXT,
    delta         INTEGER NOT NULL,                  -- +1 発行/入庫 / -1 消尽
    reason        TEXT NOT NULL,                     -- 'issue' | 'consume' | 'adjust'
    balance_after INTEGER,
    worker        TEXT,
    note          TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_inv_tx_time ON inv_tx(created_at);
CREATE INDEX IF NOT EXISTS idx_inv_tx_code ON inv_tx(code);
"""

# (code, category, group_no, group_name, name, fabric_type, flame, unit, sort_order)
ITEMS = [
    # 1. 原反 (ロール)
    ("11", "fabric", 1, "原反", "ダブルレイヤーポリエステル生地",        "DP",  True,  "ロール", 11),
    ("12", "fabric", 1, "原反", "ダブルレイヤーポリエステル生地(防炎なし)", "DP",  False, "ロール", 12),
    ("13", "fabric", 1, "原反", "特殊ダブルレイヤーポリエステル生地",      "SDP", True,  "ロール", 13),
    ("14", "fabric", 1, "原反", "特殊ダブルレイヤーポリエステル生地(防炎なし)", "SDP", False, "ロール", 14),
    ("15", "fabric", 1, "原反", "低騒音生地",                          "LN",  True,  "ロール", 15),
    ("16", "fabric", 1, "原反", "低騒音生地(防炎なし)",                 "LN",  False, "ロール", 16),
    # 2. マジックテープ (箱)
    ("21", "accessory", 2, "マジックテープ", "マジックテープ、HOOK", None, None, "箱", 21),
    ("22", "accessory", 2, "マジックテープ", "マジックテープ、LOOP", None, None, "箱", 22),
    # 3. ウェビング (箱)
    ("31", "accessory", 3, "ウェビング", "黒色ウェビング", None, None, "箱", 31),
    # 4. アイレット (箱)
    ("41", "accessory", 4, "アイレット", "アイレット(24号)", None, None, "箱", 41),
    ("42", "accessory", 4, "アイレット", "アイレット(28号)", None, None, "箱", 42),
    # 5. 糸 (箱)
    ("51", "accessory", 5, "糸", "糸", None, None, "箱", 51),
    # 6. カバー (箱)
    ("61", "accessory", 6, "カバー", "白色ウェビング", None, None, "箱", 61),
    # 7. 消耗品 — 工場備品(プリンタ用の資材)。生産材料ではないので category='supply'。
    ("71", "supply", 7, "消耗品", "ラベル紙(注文ラベル用 110mm)",        None, None, "ロール", 71),
    ("72", "supply", 7, "消耗品", "熱転写リボン(110mm)",                 None, None, "本",     72),
    ("73", "supply", 7, "消耗品", "ラベルシール(在庫QR用 29×90mm)",      None, None, "ロール", 73),
    ("74", "supply", 7, "消耗品", "A4用紙(送り状プリンタ用)",            None, None, "箱",     74),
]

UPSERT = """
INSERT INTO inv_item (code, category, group_no, group_name, name, fabric_type, flame, unit,
                      capacity, reorder_point, sort_order)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
ON CONFLICT (code) DO UPDATE SET
    category   = EXCLUDED.category,
    group_no   = EXCLUDED.group_no,
    group_name = EXCLUDED.group_name,
    name       = EXCLUDED.name,
    fabric_type= EXCLUDED.fabric_type,
    flame      = EXCLUDED.flame,
    unit       = EXCLUDED.unit,
    sort_order = EXCLUDED.sort_order,
    active     = TRUE;
"""


def main():
    with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute(DDL)
        for it in ITEMS:
            code, cat, gno, gname, name, ft, flame, unit, so = it
            cap = {"fabric": 10, "supply": 10}.get(cat, 20)
            reorder = {"fabric": 3, "supply": 2}.get(cat, 5)
            cur.execute(UPSERT, (code, cat, gno, gname, name, ft, flame, unit, cap, reorder, so))
        conn.commit()
        cur.execute("SELECT count(*) FROM inv_item")
        n = cur.fetchone()[0]
    print(f"完了: inv_item / inv_unit / inv_tx を作成し、品目 {len(ITEMS)} 件を投入しました(現在 {n} 件)。")


if __name__ == "__main__":
    main()
