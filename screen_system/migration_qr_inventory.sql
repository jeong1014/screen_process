-- =============================================================================
-- QR在庫(発行/スキャン消尽) + 付属品単位「箱」統一  マイグレーション
--   既存の screen DB に一度だけ実行:
--     psql -U postgres -d screen -f migration_qr_inventory.sql
--
--  ※ QR在庫は既存テーブル(fabric_inventory / accessories / inventory_transactions)
--    をそのまま使うため、新しいテーブルは不要。
--    QRコード内容:  生地 = INV-F-{LN/DP/SDP}  /  付属品 = INV-A-{accessory_id}
-- =============================================================================
BEGIN;

-- 付属品の単位を全て「箱」に統一
ALTER TABLE accessories ALTER COLUMN unit SET DEFAULT '箱';
UPDATE accessories SET unit = '箱' WHERE unit IS DISTINCT FROM '箱';

COMMIT;
