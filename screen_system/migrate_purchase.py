"""
migrate_purchase.py
  発注(仕入れ)機能のテーブルとメール設定を作成する。

  - purchase_order : 発注依頼〜到着予定〜入荷 の1件を管理
      status: 'requested' 依頼(要請) → 'ordered' 発注済(到着予定日あり)
              → 'arrived' 入荷済 / 'cancelled' 取消
  - settings に SMTP / 資材部メール のキー(空の既定値)を追加

実行(UTF-8で安全に投入。psqlは文字化けするので必ずこれで):
    set DATABASE_URL=postgresql://postgres:パスワード@localhost:5432/screen
    python migrate_purchase.py

再実行しても既存データは保持します(IF NOT EXISTS / ON CONFLICT DO NOTHING)。
"""
import os
import psycopg

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:1234@localhost:5432/screen")

DDL = r"""
CREATE TABLE IF NOT EXISTS purchase_order (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code          TEXT NOT NULL,                      -- inv_item.code
    item_name     TEXT NOT NULL,                      -- 依頼時点の品名スナップショット
    unit          TEXT NOT NULL DEFAULT '箱',
    qty           INTEGER NOT NULL,                   -- 必要数(依頼数)
    status        TEXT NOT NULL DEFAULT 'requested',  -- requested|ordered|arrived|cancelled
    requested_by  TEXT,                               -- 依頼者(作業者名 等)
    requested_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    eta           DATE,                               -- 到着予定日(資材部が入力)
    ordered_at    TIMESTAMPTZ,                        -- 発注登録日時
    arrived_at    TIMESTAMPTZ,                        -- 入荷確定日時
    emailed       BOOLEAN NOT NULL DEFAULT FALSE,     -- 資材部へメール送信済か
    req_note      TEXT,                               -- 依頼メモ
    order_note    TEXT                                -- 発注メモ(資材部)
);
CREATE INDEX IF NOT EXISTS idx_po_status ON purchase_order(status);
CREATE INDEX IF NOT EXISTS idx_po_time   ON purchase_order(requested_at);
"""

# メール設定(既定は空 = 未設定。設定するまではメール送信をスキップし、依頼レコードだけ作る)
SETTING_DEFAULTS = [
    ("purchase_email_to", ""),   # 資材部の宛先(カンマ区切りで複数可)
    ("smtp_host", ""),
    ("smtp_port", "587"),
    ("smtp_user", ""),
    ("smtp_pass", ""),
    ("smtp_from", ""),           # 差出人(空なら smtp_user を使用)
    ("smtp_tls", "starttls"),    # starttls | ssl | none
]


def main():
    with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute(DDL)
        for key, val in SETTING_DEFAULTS:
            cur.execute(
                "INSERT INTO settings (key, value) VALUES (%s,%s) ON CONFLICT (key) DO NOTHING",
                (key, val),
            )
        conn.commit()
        cur.execute("SELECT count(*) FROM purchase_order")
        n = cur.fetchone()[0]
    print(f"完了: purchase_order テーブルとメール設定キーを作成しました(既存の発注 {n} 件)。")


if __name__ == "__main__":
    main()
