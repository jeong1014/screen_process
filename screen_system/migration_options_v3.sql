-- =============================================================================
-- migration_options_v3.sql
-- ベルクロ・ハトメ・スカートは同じ辺に同時に付く。
-- 従来の process_top/bottom/left/right は「1辺につき1種類」しか持てず、
-- 実態(上辺 = ハトメ + ベルクロ、下辺 = スカート + ハトメ + ベルクロ)を表せなかった。
--
--   ・process_*      → ハトメ専用に意味を絞る ('none' か 'eyelet' のみ)
--   ・velcro_sides   → ベルクロ面数 (NULL=なし / 3=上左右 / 4=四辺)
--   ・has_skirt      → スカートの有無 (下辺のみ。取付方法は既存 skirt_attachment)
--
-- 実行方法(screen_system フォルダで):
--   python run_migration.py migration_options_v3.sql
--   もしくは  psql -U <user> -d <db> -f migration_options_v3.sql
--
-- 冪等(idempotent)。複数回流しても壊れない。
-- =============================================================================

BEGIN;

-- 1) 列を追加
ALTER TABLE order_items ADD COLUMN IF NOT EXISTS velcro_sides SMALLINT;
ALTER TABLE order_items ADD COLUMN IF NOT EXISTS has_skirt    BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE order_items DROP CONSTRAINT IF EXISTS ck_order_items_velcro_sides;
ALTER TABLE order_items ADD  CONSTRAINT ck_order_items_velcro_sides
      CHECK (velcro_sides IS NULL OR velcro_sides IN (3, 4));

COMMENT ON COLUMN order_items.velcro_sides IS 'ベルクロ面数: NULL=なし / 3=上左右 / 4=四辺';
COMMENT ON COLUMN order_items.has_skirt    IS 'スカート有無(下辺)。取付方法は skirt_attachment';

-- 2) 既存データの移送: 辺に 'skirt' が入っていれば has_skirt=true
UPDATE order_items
   SET has_skirt = true
 WHERE has_skirt = false
   AND 'skirt' IN (process_top, process_bottom, process_left, process_right);

-- 3) 既存データの移送: 辺に 'velcro' が入っていた枚数を面数として記録
--    (3辺なら3、4辺なら4。1〜2辺だけの旧データは3面に寄せる)
UPDATE order_items
   SET velcro_sides = CASE WHEN v >= 4 THEN 4 ELSE 3 END
  FROM (
        SELECT id AS oid,
               (process_top    = 'velcro')::int
             + (process_bottom = 'velcro')::int
             + (process_left   = 'velcro')::int
             + (process_right  = 'velcro')::int AS v
          FROM order_items
       ) t
 WHERE order_items.id = t.oid
   AND order_items.velcro_sides IS NULL
   AND t.v > 0;

-- 4) process_* を ハトメ専用に正規化 ('skirt'/'velcro' は 'none' へ)
--    ハトメ以外になった辺のピッチ(mm)も消す
UPDATE order_items SET process_top    = 'none', process_top_mm    = NULL WHERE process_top    IN ('skirt', 'velcro');
UPDATE order_items SET process_bottom = 'none', process_bottom_mm = NULL WHERE process_bottom IN ('skirt', 'velcro');
UPDATE order_items SET process_left   = 'none', process_left_mm   = NULL WHERE process_left   IN ('skirt', 'velcro');
UPDATE order_items SET process_right  = 'none', process_right_mm  = NULL WHERE process_right  IN ('skirt', 'velcro');

COMMIT;

-- 確認用:
--   SELECT barcode, process_top, process_bottom, velcro_sides, has_skirt FROM order_items ORDER BY id DESC LIMIT 10;
