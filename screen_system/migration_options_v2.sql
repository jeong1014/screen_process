-- =============================================================================
-- 2枚セット(two_sheet_set) 表面/裏面 分離 マイグレーション (既存の screen DB に一度だけ実行)
--   実行: psql -U postgres -d screen -f migration_options_v2.sql
--   ※ 新規インストールは schema.sql に同内容が入っているので不要
--
--   背景: 2枚セットは裁断/ミシン/ハトメ/梱包を表面用・裏面用で2回作業する必要があるため、
--         1行(1バーコード)で裏面情報を付随管理する方式(migration_options_v1.sql)をやめ、
--         表面/裏面をそれぞれ独立した order_items 行(=独立したバーコード)として管理する。
--         例: 表面 = CDI260715001DP01 / 裏面 = CDI260715001DP02
--
--   追加: order_items.sheet_side ('front'/'back', 2枚セットのみ)
--         order_items.pair_item_no (対になるもう片方の item_no)
--   削除: order_items.back_fabric_type / back_width_mm / back_height_mm
--         (migration_options_v1.sql で追加したが、表裏を1行にまとめる旧方式のため不要に)
-- =============================================================================
BEGIN;

DO $$ BEGIN
    CREATE TYPE sheet_side_kind AS ENUM ('front', 'back');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

ALTER TABLE order_items ADD COLUMN IF NOT EXISTS sheet_side   sheet_side_kind;
ALTER TABLE order_items ADD COLUMN IF NOT EXISTS pair_item_no SMALLINT;

-- 旧方式(1行に裏面情報を付随)のカラムを削除。CHECK制約もカラムと一緒に自動削除される。
ALTER TABLE order_items DROP COLUMN IF EXISTS back_fabric_type;
ALTER TABLE order_items DROP COLUMN IF EXISTS back_width_mm;
ALTER TABLE order_items DROP COLUMN IF EXISTS back_height_mm;

COMMIT;
