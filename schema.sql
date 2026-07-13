-- =============================================================================
-- スクリーン原団 工場工程管理システム  —  PostgreSQL スキーマ
-- screen fabric factory process-management system  —  schema
--
-- 対象: 注文受信(4チャネル) → 作業指示/ラベル出力 → 4工程生産
--       → 検品/梱包 → BizLogi/佐川 出荷 → 月次 消防法報告
--
-- 設計方針:
--   * 進行状態は order_items.current_stage (0〜8) を single source of truth とする
--   * すべてのスキャン(開始/完了/取消)は scan_events に1行ずつ記録する
--   * 工程は production_stages マスタで定義 → 工程追加はスキーマ変更不要
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 0. 共通関数
-- ---------------------------------------------------------------------------

-- updated_at を自動更新する共通トリガ関数
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ---------------------------------------------------------------------------
-- 1. ENUM 型 (安定した固定集合)
-- ---------------------------------------------------------------------------

-- 販売チャネル
CREATE TYPE sales_channel AS ENUM ('rakuten', 'amazon', 'yahoo', 'base_ec');

-- 決済状態
CREATE TYPE payment_status AS ENUM ('unpaid', 'pending', 'paid', 'cancelled', 'refunded');

-- 注文全体の状態
CREATE TYPE order_status AS ENUM (
    'imported',    -- 取込済
    'confirmed',   -- 仕様確認済
    'printed',     -- 作業指示/ラベル出力済
    'production',  -- 生産中
    'shipped',     -- 出荷済
    'closed',      -- 完了
    'cancelled'    -- キャンセル
);

-- 原団種別
CREATE TYPE fabric_type AS ENUM ('LN', 'DP', 'SDP');

-- 商品種別
CREATE TYPE product_type AS ENUM ('single', 'two_sheet_set', 'skirt');

-- 各辺の加工内容
CREATE TYPE process_kind AS ENUM ('none', 'eyelet', 'skirt', 'hatome');

-- スキャンイベント種別 (各工程 開始/完了 の2回スキャン + 取消)
CREATE TYPE scan_event_type AS ENUM ('start', 'complete', 'undo');

-- 出力ジョブ対象
CREATE TYPE print_target_type AS ENUM ('work_instruction', 'product_label', 'shipping_label', 'control_barcode');

-- プリンタ種別
CREATE TYPE printer_type AS ENUM ('brother_td4550', 'label', 'sato_cf408t', 'a4');

-- 出力ジョブ状態
CREATE TYPE print_status AS ENUM ('waiting', 'printing', 'printed', 'failed');

-- 出荷/送り状状態
CREATE TYPE shipping_status AS ENUM ('ready', 'label_printed', 'handed_to_sagawa', 'completed');

-- BizLogi 連携状態
CREATE TYPE bizlogi_status AS ENUM ('not_requested', 'requested', 'issued', 'failed');

-- 外部システム連携ログ
CREATE TYPE sync_system AS ENUM ('rakuten', 'amazon', 'yahoo', 'base_ec', 'bizlogi', 'sagawa');
CREATE TYPE sync_action AS ENUM ('import_order', 'confirm_payment', 'issue_label', 'update_shipping', 'cancel');
CREATE TYPE sync_status AS ENUM ('success', 'failed');


-- ---------------------------------------------------------------------------
-- 2. production_stages — 工程マスタ (進行状態 0〜8 の定義)
--    工程を追加/変更する場合はここに行を足すだけ (スキーマ変更不要)
-- ---------------------------------------------------------------------------

CREATE TABLE production_stages (
    stage_no     SMALLINT PRIMARY KEY CHECK (stage_no BETWEEN 0 AND 99),
    code         TEXT NOT NULL UNIQUE,          -- 内部コード (英字)
    name_ja      TEXT NOT NULL,                 -- 日本語表示名
    name_ko      TEXT NOT NULL,                 -- 韓国語表示名
    is_scannable BOOLEAN NOT NULL DEFAULT TRUE, -- 作業者バーコードスキャン対象か
    sort_order   SMALLINT NOT NULL              -- 表示順
);

COMMENT ON TABLE production_stages IS '工程マスタ。order_items.current_stage の参照先。0=未着手 〜 8=完了';

INSERT INTO production_stages (stage_no, code, name_ja, name_ko, is_scannable, sort_order) VALUES
    (0, 'waiting',      '未着手',           '대기',          FALSE, 0),
    (1, 'fabric_check', '生地確認',         '원단확인',      TRUE,  1),
    (2, 'cutting',      '裁断',             '재단',          TRUE,  2),
    (3, 'sewing',       'ミシン',           '미싱',          TRUE,  3),
    (4, 'eyelet_skirt', 'ハトメ・スカート', '하토메·스커트', TRUE,  4),
    (5, 'inspection',   '検品',             '검품',          TRUE,  5),
    (6, 'packing',      '梱包',             '포장',          TRUE,  6),
    (7, 'shipped',      '集荷完了',         '집하완료',      FALSE, 7),
    (8, 'closed',       '完了',             '완료',          FALSE, 8);


-- ---------------------------------------------------------------------------
-- 3. orders — 注文ヘッダ (ショップから受信した注文単位)
-- ---------------------------------------------------------------------------

CREATE TABLE orders (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_no       TEXT NOT NULL UNIQUE,          -- 社内注文番号 ORD-YYYYMMDD-0001
    channel        sales_channel NOT NULL,
    mall_order_no  TEXT,                          -- ショップ側の注文番号
    customer_name  TEXT NOT NULL,
    postal_code    TEXT,
    address        TEXT,
    phone          TEXT,
    payment_status payment_status NOT NULL DEFAULT 'pending',
    order_status   order_status   NOT NULL DEFAULT 'imported',
    raw_data       JSONB,                         -- ショップ受信の生データ(JSON/XML)
    ordered_at     TIMESTAMPTZ,                   -- 注文日時
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- 同一チャネル内でショップ注文番号は一意
    CONSTRAINT uq_orders_channel_mall_no UNIQUE (channel, mall_order_no)
);

CREATE INDEX idx_orders_status      ON orders (order_status);
CREATE INDEX idx_orders_channel     ON orders (channel);
CREATE INDEX idx_orders_ordered_at  ON orders (ordered_at);

CREATE TRIGGER trg_orders_updated_at
    BEFORE UPDATE ON orders
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ---------------------------------------------------------------------------
-- 4. order_items — 注文明細 (作業指示書/ラベル1枚 = 1行)
--    current_stage が進行状態の single source of truth
-- ---------------------------------------------------------------------------

CREATE TABLE order_items (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id       BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    item_no        SMALLINT NOT NULL,             -- 注文内の明細番号 1,2,3...
    barcode        TEXT NOT NULL UNIQUE,          -- ラベル印字バーコード(Code128) スキャンキー

    product_type   product_type NOT NULL,
    fabric_type    fabric_type  NOT NULL,
    width_mm       INTEGER NOT NULL CHECK (width_mm  > 0),
    height_mm      INTEGER NOT NULL CHECK (height_mm > 0),
    quantity       INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),

    -- 4辺の加工 (種別 + 寸法mm)
    process_top       process_kind NOT NULL DEFAULT 'none',
    process_top_mm    INTEGER,
    process_bottom    process_kind NOT NULL DEFAULT 'none',
    process_bottom_mm INTEGER,
    process_left      process_kind NOT NULL DEFAULT 'none',
    process_left_mm   INTEGER,
    process_right     process_kind NOT NULL DEFAULT 'none',
    process_right_mm  INTEGER,

    fire_cert_no   TEXT,                          -- 防炎認証番号(消防法報告用)

    -- 進行状態: production_stages(0〜8) を参照
    current_stage     SMALLINT NOT NULL DEFAULT 0 REFERENCES production_stages(stage_no),
    -- 現在の工程が「開始済み・未完了」か (開始スキャン済 → TRUE)
    stage_in_progress BOOLEAN NOT NULL DEFAULT FALSE,

    label_printed_at TIMESTAMPTZ,                 -- 製品ラベル出力時刻(NULL=未出力)
    started_at     TIMESTAMPTZ,                   -- 最初の工程開始時刻
    completed_at   TIMESTAMPTZ,                   -- 梱包完了時刻

    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_order_items_order_itemno UNIQUE (order_id, item_no)
);

CREATE INDEX idx_order_items_order_id ON order_items (order_id);
CREATE INDEX idx_order_items_stage    ON order_items (current_stage);
CREATE INDEX idx_order_items_barcode  ON order_items (barcode);

CREATE TRIGGER trg_order_items_updated_at
    BEFORE UPDATE ON order_items
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ---------------------------------------------------------------------------
-- 5. scan_events — バーコードスキャン履歴 (全イベントを追記)
--    各工程 開始(start)/完了(complete)、誤操作の取消(undo) を1行ずつ記録
--    current_stage はこのイベントを基に更新する(アプリ層 or トリガ)
-- ---------------------------------------------------------------------------

CREATE TABLE scan_events (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_item_id BIGINT NOT NULL REFERENCES order_items(id) ON DELETE CASCADE,
    stage_no      SMALLINT NOT NULL REFERENCES production_stages(stage_no),
    event_type    scan_event_type NOT NULL,      -- start / complete / undo
    station       TEXT,                          -- スキャン場所/端末(例: cutting_tablet)
    worker        TEXT,                          -- 作業者(任意)
    note          TEXT,
    scanned_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 明細ごとの時系列参照が主用途
CREATE INDEX idx_scan_events_item_time ON scan_events (order_item_id, scanned_at);
CREATE INDEX idx_scan_events_stage     ON scan_events (stage_no);
CREATE INDEX idx_scan_events_type      ON scan_events (event_type);


-- ---------------------------------------------------------------------------
-- 6. shipments — 梱包/送り状情報 (佐川/BizLogi)
-- ---------------------------------------------------------------------------

CREATE TABLE shipments (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id        BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    shipment_no     TEXT NOT NULL UNIQUE,         -- SHIP-YYYYMMDD-0001
    package_no      SMALLINT NOT NULL DEFAULT 1,  -- 何個口中の何番目
    package_count   SMALLINT NOT NULL DEFAULT 1,  -- 総個口数
    size_class      TEXT,                         -- 佐川サイズ区分(例: 200)
    weight_kg       NUMERIC(6,2),
    carrier         TEXT NOT NULL DEFAULT 'sagawa',
    tracking_no     TEXT,                         -- 送り状番号
    bizlogi_status  bizlogi_status  NOT NULL DEFAULT 'not_requested',
    shipping_status shipping_status NOT NULL DEFAULT 'ready',
    label_pdf_path  TEXT,                         -- 送り状PDFパス
    shipped_at      TIMESTAMPTZ,                  -- 集荷完了時刻
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_shipments_order_pkg UNIQUE (order_id, package_no)
);

CREATE INDEX idx_shipments_order_id        ON shipments (order_id);
CREATE INDEX idx_shipments_shipping_status ON shipments (shipping_status);
CREATE INDEX idx_shipments_tracking_no     ON shipments (tracking_no);

CREATE TRIGGER trg_shipments_updated_at
    BEFORE UPDATE ON shipments
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ---------------------------------------------------------------------------
-- 7. print_jobs — 出力ジョブ管理 (どのプリンタで何を出すか)
-- ---------------------------------------------------------------------------

CREATE TABLE print_jobs (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id      BIGINT REFERENCES orders(id) ON DELETE CASCADE,
    target_type   print_target_type NOT NULL,
    target_id     BIGINT,                         -- order_items.id / shipments.id 等
    printer_type  printer_type NOT NULL,
    file_path     TEXT,                           -- 生成PDF/ラベルファイル
    status        print_status NOT NULL DEFAULT 'waiting',
    error_message TEXT,
    printed_at    TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_print_jobs_order_id ON print_jobs (order_id);
CREATE INDEX idx_print_jobs_status   ON print_jobs (status);
CREATE INDEX idx_print_jobs_target   ON print_jobs (target_type, target_id);

CREATE TRIGGER trg_print_jobs_updated_at
    BEFORE UPDATE ON print_jobs
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ---------------------------------------------------------------------------
-- 8. sync_logs — 外部API連携ログ (取込/出荷反映/送り状発行 の成否記録)
-- ---------------------------------------------------------------------------

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

CREATE INDEX idx_sync_logs_order_id ON sync_logs (order_id);
CREATE INDEX idx_sync_logs_system   ON sync_logs (system, action);
CREATE INDEX idx_sync_logs_created  ON sync_logs (created_at);


-- ---------------------------------------------------------------------------
-- 9. 消防法 月次報告  (防炎物品 販売記録の提出用)
--    fire_safety_reports(ヘッダ) 1 --- N fire_safety_report_items(明細)
-- ---------------------------------------------------------------------------

CREATE TABLE fire_safety_reports (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    report_month DATE NOT NULL,                   -- 対象月(月初日 例:2026-06-01)
    status       TEXT NOT NULL DEFAULT 'draft',   -- draft / confirmed / exported
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    exported_at  TIMESTAMPTZ,
    file_path    TEXT,                            -- 出力Excel/PDFパス
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_fire_reports_month UNIQUE (report_month)
);

CREATE TABLE fire_safety_report_items (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    report_id        BIGINT NOT NULL REFERENCES fire_safety_reports(id) ON DELETE CASCADE,
    order_no         TEXT NOT NULL,
    sold_at          DATE NOT NULL,               -- 販売/集荷日
    channel          sales_channel NOT NULL,
    product_type     product_type NOT NULL,
    fabric_type      fabric_type NOT NULL,
    width_mm         INTEGER,
    height_mm        INTEGER,
    quantity         INTEGER NOT NULL DEFAULT 1,
    amount           NUMERIC(12,2),               -- 金額(円)
    buyer_name       TEXT,
    buyer_address    TEXT,                        -- 購入者住所(全体)
    delivery_name    TEXT,
    delivery_address TEXT,                        -- 配送先住所(全体)
    fire_cert_no     TEXT,                        -- 防炎認証番号
    note             TEXT
);

CREATE INDEX idx_fire_items_report_id ON fire_safety_report_items (report_id);
CREATE INDEX idx_fire_items_sold_at   ON fire_safety_report_items (sold_at);

COMMIT;
