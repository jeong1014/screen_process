-- =============================================================================
-- migration_remove_packing.sql
-- 梱包(packing, 旧 stage 7=梱包中 / 8=梱包完了)工程を廃止する。
-- ハトメ完了(stage 6)を最終段階(=出荷準備完了)とする。
--
-- 実行方法(例):
--   psql -U <user> -d <db> -f migration_remove_packing.sql
--
-- 冪等(idempotent)に近い形で書いてあり、複数回流しても壊れないようにしている。
-- =============================================================================

BEGIN;

-- 1) 既存データを移送: stage 7/8 の在庫を 6(ハトメ完了)へ寄せる
UPDATE order_items  SET current_stage = 6 WHERE current_stage IN (7, 8);

-- 2) スキャン履歴の stage_no も 6 に付け替える(production_stages への FK があるため先に実施)
UPDATE scan_events  SET stage_no = 6 WHERE stage_no IN (7, 8);

-- 3) 工程マスタから梱包(7,8)を削除
DELETE FROM production_stages WHERE stage_no IN (7, 8);

-- 4) stage_no の CHECK 制約を 0〜6 に締め直す
--    (制約名は PostgreSQL 既定の "production_stages_stage_no_check"。
--     環境で名前が異なる場合は \d production_stages で確認して置き換えること)
ALTER TABLE production_stages DROP CONSTRAINT IF EXISTS production_stages_stage_no_check;
ALTER TABLE production_stages
    ADD CONSTRAINT production_stages_stage_no_check CHECK (stage_no BETWEEN 0 AND 6);

-- 5) テーブルコメント更新
COMMENT ON TABLE production_stages IS
    '工程マスタ。order_items.current_stage(0〜6)の参照先。奇数=作業中, 偶数=完了。ハトメ完了(6)が最終段階';

COMMIT;

-- 確認用(任意):
--   SELECT stage_no, code, name_ja FROM production_stages ORDER BY stage_no;
--   SELECT current_stage, count(*) FROM order_items GROUP BY current_stage ORDER BY current_stage;
