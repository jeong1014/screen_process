-- =============================================================================
-- 販売サイトのオプション体系への統合 マイグレーション (既存の screen DB に一度だけ実行)
--   実行: psql -U postgres -d screen -f migration_options_v1.sql
--   ※ 新規インストールは schema.sql に同内容が入っているので不要
--
--   追加内容:
--     order_items.back_fabric_type / back_width_mm / back_height_mm
--       → 2枚セット(two_sheet_set)の裏面の生地/サイズを表面と別に管理
--     order_items.velcro_type   (male/female)
--     order_items.skirt_attachment (sew/velcro)
--     order_items.skirt_no_seam (boolean)
--     order_items.eyelet_method (A/B/C)
--   ※ 防炎(fire_cert_no)は現状どおりテキスト欄のみで管理(新規カラムは追加しない)
-- =============================================================================
BEGIN;

-- ENUM型は CREATE TYPE IF NOT EXISTS が無いため、存在チェックしてから作成
DO $$ BEGIN
    CREATE TYPE velcro_kind AS ENUM ('male', 'female');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE skirt_attach_kind AS ENUM ('sew', 'velcro');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE eyelet_method_kind AS ENUM ('A', 'B', 'C');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

ALTER TABLE order_items ADD COLUMN IF NOT EXISTS back_fabric_type fabric_type;
ALTER TABLE order_items ADD COLUMN IF NOT EXISTS back_width_mm    INTEGER;
ALTER TABLE order_items ADD COLUMN IF NOT EXISTS back_height_mm   INTEGER;
ALTER TABLE order_items ADD COLUMN IF NOT EXISTS velcro_type      velcro_kind;
ALTER TABLE order_items ADD COLUMN IF NOT EXISTS skirt_attachment skirt_attach_kind;
ALTER TABLE order_items ADD COLUMN IF NOT EXISTS skirt_no_seam    BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE order_items ADD COLUMN IF NOT EXISTS eyelet_method    eyelet_method_kind;

-- back_width_mm / back_height_mm の正数チェック(既存データがあっても安全に追加できるよう NOT VALID)
DO $$ BEGIN
    ALTER TABLE order_items ADD CONSTRAINT chk_order_items_back_width_mm
        CHECK (back_width_mm IS NULL OR back_width_mm > 0) NOT VALID;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
    ALTER TABLE order_items ADD CONSTRAINT chk_order_items_back_height_mm
        CHECK (back_height_mm IS NULL OR back_height_mm > 0) NOT VALID;
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

COMMIT;
