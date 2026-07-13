-- =============================================================================
-- スクリーン原団 工場工程管理システム  —  PostgreSQL スキーマ (v2)
-- 既存の作業者画面(worker_v5) / ダッシュボード(dashboard_v2_2) の実モデルに整合
--
-- 進行状態 stage (0〜8) を single source of truth とする:
--   0=受付
--   1=裁断中  2=裁断完了
--   3=ミシン中 4=ミシン完了
--   5=ハトメ中 6=ハトメ完了
--   7=梱包中  8=梱包完了(=出荷準備完了)
--   → 奇数=作業中, 偶数=完了。スキャン1回で +1、戻る(UNDO)で -1。
--
-- 「注文番号(製品番号)」= ラベルのバーコード = order_items.barcode (スキャン単位)
-- =============================================================================

BEGIN;

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------------
-- ENUM
-- ---------------------------------------------------------------------------
CREATE TYPE sales_channel  AS ENUM ('rakuten', 'amazon', 'yahoo', 'base_ec');
CREATE TYPE payment_status AS ENUM ('unpaid', 'pending', 'paid', 'cancelled', 'refunded');
CREATE TYPE order_status   AS ENUM ('imported','confirmed','printed','production','shipped','closed','cancelled');
CREATE TYPE fabric_type    AS ENUM ('LN', 'DP', 'SDP');
CREATE TYPE product_type   AS ENUM ('single', 'two_sheet_set', 'skirt');
-- 各辺の加工: なし / ハトメ(eyelet) / スカート(skirt) / ベルクロ(velcro)
CREATE TYPE process_kind   AS ENUM ('none', 'eyelet', 'skirt', 'velcro');
CREATE TYPE scan_event_type AS ENUM ('start', 'complete', 'undo');
CREATE TYPE print_target_type AS ENUM ('work_instruction', 'product_label', 'shipping_label', 'control_barcode');
CREATE TYPE printer_type   AS ENUM ('brother_td4550', 'label', 'sato_cf408t', 'a4');
CREATE TYPE print_status   AS ENUM ('waiting', 'printing', 'printed', 'failed');
CREATE TYPE shipping_status AS ENUM ('ready', 'label_printed', 'handed_to_sagawa', 'completed');
CREATE TYPE bizlogi_status AS ENUM ('not_requested', 'requested', 'issued', 'failed');
CREATE TYPE sync_system    AS ENUM ('rakuten', 'amazon', 'yahoo', 'base_ec', 'bizlogi', 'sagawa');
CREATE TYPE sync_action    AS ENUM ('import_order', 'confirm_payment', 'issue_label', 'update_shipping', 'cancel');
CREATE TYPE sync_status    AS ENUM ('success', 'failed');

-- ---------------------------------------------------------------------------
-- production_stages — 工程マスタ (0〜8)
-- ---------------------------------------------------------------------------
CREATE TABLE production_stages (
    stage_no   SMALLINT PRIMARY KEY CHECK (stage_no BETWEEN 0 AND 8),
    code       TEXT NOT NULL UNIQUE,
    name_ja    TEXT NOT NULL,
    name_ko    TEXT NOT NULL,
    proc_key   TEXT,                    -- cutting/sewing/eyelet/packing (受付は NULL)
    phase      TEXT,                    -- wip(作業中) / done(完了) / (受付は NULL)
    sort_order SMALLINT NOT NULL
);
COMMENT ON TABLE production_stages IS '工程マスタ。order_items.current_stage(0〜8)の参照先。奇数=作業中, 偶数=完了';

INSERT INTO production_stages (stage_no, code, name_ja, name_ko, proc_key, phase, sort_order) VALUES
    (0, 'received',     '受付',     '접수',     NULL,      NULL,  0),
    (1, 'cutting_wip',  '裁断中',   '재단중',   'cutting', 'wip', 1),
    (2, 'cutting_done', '裁断完了', '재단완료', 'cutting', 'done',2),
    (3, 'sewing_wip',   'ミシン中', '미싱중',   'sewing',  'wip', 3),
    (4, 'sewing_done',  'ミシン完了','미싱완료','sewing',  'done',4),
    (5, 'eyelet_wip',   'ハトメ中', '하토메중', 'eyelet',  'wip', 5),
    (6, 'eyelet_done',  'ハトメ完了','하토메완료','eyelet', 'done',6),
    (7, 'packing_wip',  '梱包中',   '포장중',   'packing', 'wip', 7),
    (8, 'packing_done', '梱包完了', '포장완료', 'packing', 'done',8);

-- ---------------------------------------------------------------------------
-- orders — 注文ヘッダ
-- ---------------------------------------------------------------------------
CREATE TABLE orders (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_no       TEXT NOT NULL UNIQUE,
    channel        sales_channel NOT NULL,
    mall_order_no  TEXT,
    customer_name  TEXT NOT NULL,
    postal_code    TEXT,
    address        TEXT,
    phone          TEXT,
    payment_status payment_status NOT NULL DEFAULT 'pending',
    order_status   order_status   NOT NULL DEFAULT 'imported',
    raw_data       JSONB,
    ordered_at     TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_orders_channel_mall_no UNIQUE (channel, mall_order_no)
);
CREATE INDEX idx_orders_status     ON orders (order_status);
CREATE INDEX idx_orders_ordered_at ON orders (ordered_at);
CREATE TRIGGER trg_orders_updated_at BEFORE UPDATE ON orders
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------
-- order_items — 注文明細 (= ラベル1枚 = 製品1点 = スキャン単位)
--   current_stage(0〜8) が進行状態の single source of truth
-- ---------------------------------------------------------------------------
CREATE TABLE order_items (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id     BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    item_no      SMALLINT NOT NULL,
    barcode      TEXT NOT NULL UNIQUE,          -- ラベル印字/スキャンキー(=画面の製品番号)

    product_type product_type NOT NULL DEFAULT 'single',
    fabric_type  fabric_type  NOT NULL,
    width_mm     INTEGER NOT NULL CHECK (width_mm  > 0),
    height_mm    INTEGER NOT NULL CHECK (height_mm > 0),
    quantity     INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),

    -- 4辺の加工: 種別 + ハトメ間隔(mm)。ミシン/ハトメ工程の表示に使う
    process_top       process_kind NOT NULL DEFAULT 'none',
    process_top_mm    INTEGER,
    process_bottom    process_kind NOT NULL DEFAULT 'none',
    process_bottom_mm INTEGER,
    process_left      process_kind NOT NULL DEFAULT 'none',
    process_left_mm   INTEGER,
    process_right     process_kind NOT NULL DEFAULT 'none',
    process_right_mm  INTEGER,

    fire_cert_no  TEXT,

    current_stage SMALLINT NOT NULL DEFAULT 0 REFERENCES production_stages(stage_no),
    started_at    TIMESTAMPTZ,
    completed_at  TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_order_items_order_itemno UNIQUE (order_id, item_no)
);
CREATE INDEX idx_order_items_order_id ON order_items (order_id);
CREATE INDEX idx_order_items_stage    ON order_items (current_stage);
CREATE INDEX idx_order_items_barcode  ON order_items (barcode);
CREATE TRIGGER trg_order_items_updated_at BEFORE UPDATE ON order_items
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------
-- scan_events — スキャン履歴 (1回 = 1行, 履歴/現況板イベントの元)
-- ---------------------------------------------------------------------------
CREATE TABLE scan_events (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_item_id BIGINT NOT NULL REFERENCES order_items(id) ON DELETE CASCADE,
    stage_no      SMALLINT NOT NULL REFERENCES production_stages(stage_no),  -- スキャン後の段階
    event_type    scan_event_type NOT NULL,
    station       TEXT,
    worker        TEXT,
    note          TEXT,
    scanned_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_scan_events_item_time ON scan_events (order_item_id, scanned_at);
CREATE INDEX idx_scan_events_time      ON scan_events (scanned_at);

-- ---------------------------------------------------------------------------
-- 在庫: 生地(ロール単位) / 付属品
-- ---------------------------------------------------------------------------
CREATE TABLE fabric_inventory (
    fabric_type    fabric_type PRIMARY KEY,
    remain_rolls   INTEGER NOT NULL DEFAULT 0,
    capacity_rolls INTEGER NOT NULL DEFAULT 10,
    reorder_point  INTEGER NOT NULL DEFAULT 3,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO fabric_inventory (fabric_type, remain_rolls, capacity_rolls) VALUES
    ('LN', 6, 10), ('DP', 2, 10), ('SDP', 5, 10);

CREATE TABLE accessories (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name       TEXT NOT NULL,
    remain     INTEGER NOT NULL DEFAULT 0,
    capacity   INTEGER NOT NULL DEFAULT 10,
    unit       TEXT NOT NULL DEFAULT '個',
    reorder_point INTEGER NOT NULL DEFAULT 5,
    sort_order SMALLINT NOT NULL DEFAULT 0
);
INSERT INTO accessories (name, remain, capacity, unit, sort_order) VALUES
    ('ハトメ',     8,  20, '箱', 1),
    ('ウェビング', 3,  15, '巻', 2),
    ('糸',         12, 30, '個', 3),
    ('ベルクロ',   2,  10, '巻', 4);

-- 入出庫履歴 / 設定 (管理者ページ)
CREATE TABLE inventory_transactions (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind          TEXT NOT NULL CHECK (kind IN ('fabric', 'accessory')),
    fabric_type   fabric_type,
    accessory_id  BIGINT REFERENCES accessories(id) ON DELETE CASCADE,
    delta         INTEGER NOT NULL,
    reason        TEXT NOT NULL CHECK (reason IN ('in', 'out', 'adjust')),
    balance_after INTEGER,
    note          TEXT,
    worker        TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_inv_tx_time ON inventory_transactions (created_at);
CREATE INDEX idx_inv_tx_ref  ON inventory_transactions (kind, fabric_type, accessory_id);

CREATE TABLE settings (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO settings (key, value) VALUES
    ('admin_password', '1234'),
    ('printer_work',   'a4'),
    ('printer_label',  'label'),
    ('printer_ship',   'sato_cf408t');

-- ---------------------------------------------------------------------------
-- shipments / print_jobs / sync_logs
-- ---------------------------------------------------------------------------
CREATE TABLE shipments (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id        BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    shipment_no     TEXT NOT NULL UNIQUE,
    package_no      SMALLINT NOT NULL DEFAULT 1,
    package_count   SMALLINT NOT NULL DEFAULT 1,
    size_class      TEXT,
    weight_kg       NUMERIC(6,2),
    carrier         TEXT NOT NULL DEFAULT 'sagawa',
    tracking_no     TEXT,
    bizlogi_status  bizlogi_status  NOT NULL DEFAULT 'not_requested',
    shipping_status shipping_status NOT NULL DEFAULT 'ready',
    label_pdf_path  TEXT,
    shipped_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_shipments_order_pkg UNIQUE (order_id, package_no)
);
CREATE INDEX idx_shipments_order_id ON shipments (order_id);
CREATE TRIGGER trg_shipments_updated_at BEFORE UPDATE ON shipments
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE print_jobs (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id      BIGINT REFERENCES orders(id) ON DELETE CASCADE,
    target_type   print_target_type NOT NULL,
    target_id     BIGINT,
    printer_type  printer_type NOT NULL,
    file_path     TEXT,
    status        print_status NOT NULL DEFAULT 'waiting',
    error_message TEXT,
    printed_at    TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_print_jobs_status ON print_jobs (status);
CREATE TRIGGER trg_print_jobs_updated_at BEFORE UPDATE ON print_jobs
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE sync_logs (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id      BIGINT REFERENCES orders(id) ON DELETE SET NULL,
    system        sync_system NOT NULL,
    action        sync_action NOT NULL,
    status        sync_status NOT NULL,
    request_data  JSONB,
    response_data JSONB,
    error_message TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_sync_logs_created ON sync_logs (created_at);

-- ---------------------------------------------------------------------------
-- 消防法 月次報告
-- ---------------------------------------------------------------------------
CREATE TABLE fire_safety_reports (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    report_month DATE NOT NULL,
    status       TEXT NOT NULL DEFAULT 'draft',
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    exported_at  TIMESTAMPTZ,
    file_path    TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_fire_reports_month UNIQUE (report_month)
);
CREATE TABLE fire_safety_report_items (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    report_id        BIGINT NOT NULL REFERENCES fire_safety_reports(id) ON DELETE CASCADE,
    order_no         TEXT NOT NULL,
    sold_at          DATE NOT NULL,
    channel          sales_channel NOT NULL,
    product_type     product_type NOT NULL,
    fabric_type      fabric_type NOT NULL,
    width_mm         INTEGER,
    height_mm        INTEGER,
    quantity         INTEGER NOT NULL DEFAULT 1,
    amount           NUMERIC(12,2),
    buyer_name       TEXT,
    buyer_address    TEXT,
    delivery_name    TEXT,
    delivery_address TEXT,
    fire_cert_no     TEXT,
    note             TEXT
);
CREATE INDEX idx_fire_items_report_id ON fire_safety_report_items (report_id);

COMMIT;
