-- =============================================================================
-- 管理者ページ用 マイグレーション (既存の screen DB に一度だけ実行)
--   実行: psql -U postgres -d screen -f migration_admin.sql
--   ※ 新規インストールは schema.sql に同内容が入っているので不要
-- =============================================================================
BEGIN;

-- 在庫の発注点(これ以下で「不足」警告)
ALTER TABLE fabric_inventory ADD COLUMN IF NOT EXISTS reorder_point INTEGER NOT NULL DEFAULT 3;
ALTER TABLE accessories      ADD COLUMN IF NOT EXISTS reorder_point INTEGER NOT NULL DEFAULT 5;

-- 入出庫履歴
CREATE TABLE IF NOT EXISTS inventory_transactions (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind          TEXT NOT NULL CHECK (kind IN ('fabric', 'accessory')),
    fabric_type   fabric_type,                       -- kind='fabric' のとき
    accessory_id  BIGINT REFERENCES accessories(id) ON DELETE CASCADE,  -- kind='accessory'
    delta         INTEGER NOT NULL,                  -- +入庫 / −消尽
    reason        TEXT NOT NULL CHECK (reason IN ('in', 'out', 'adjust')),
    balance_after INTEGER,                           -- 反映後の残数
    note          TEXT,
    worker        TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_inv_tx_time ON inventory_transactions (created_at);
CREATE INDEX IF NOT EXISTS idx_inv_tx_ref  ON inventory_transactions (kind, fabric_type, accessory_id);

-- 設定(key/value)
CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO settings (key, value) VALUES
    ('admin_password', '1234'),          -- ★ 初期パスワード(設定タブで変更してください)
    ('printer_work',   'a4'),            -- 作業指示書プリンタ
    ('printer_label',  'label'),         -- 製品ラベルプリンタ
    ('printer_ship',   'sato_cf408t')    -- 送り状プリンタ
ON CONFLICT (key) DO NOTHING;

COMMIT;
