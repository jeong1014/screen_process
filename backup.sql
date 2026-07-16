--
-- PostgreSQL database dump
--

\restrict Tcxu6L70QLyCdg054kgttFSBMx5NgLH2GrdYo1HWrgwP2cH43IMr2TAxwnxYKdy

-- Dumped from database version 18.4
-- Dumped by pg_dump version 18.4

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: bizlogi_status; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.bizlogi_status AS ENUM (
    'not_requested',
    'requested',
    'issued',
    'failed'
);


ALTER TYPE public.bizlogi_status OWNER TO postgres;

--
-- Name: fabric_type; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.fabric_type AS ENUM (
    'LN',
    'DP',
    'SDP'
);


ALTER TYPE public.fabric_type OWNER TO postgres;

--
-- Name: order_status; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.order_status AS ENUM (
    'imported',
    'confirmed',
    'printed',
    'production',
    'shipped',
    'closed',
    'cancelled'
);


ALTER TYPE public.order_status OWNER TO postgres;

--
-- Name: payment_status; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.payment_status AS ENUM (
    'unpaid',
    'pending',
    'paid',
    'cancelled',
    'refunded'
);


ALTER TYPE public.payment_status OWNER TO postgres;

--
-- Name: print_status; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.print_status AS ENUM (
    'waiting',
    'printing',
    'printed',
    'failed'
);


ALTER TYPE public.print_status OWNER TO postgres;

--
-- Name: print_target_type; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.print_target_type AS ENUM (
    'work_instruction',
    'product_label',
    'shipping_label',
    'control_barcode'
);


ALTER TYPE public.print_target_type OWNER TO postgres;

--
-- Name: printer_type; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.printer_type AS ENUM (
    'brother_td4550',
    'label',
    'sato_cf408t',
    'a4'
);


ALTER TYPE public.printer_type OWNER TO postgres;

--
-- Name: process_kind; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.process_kind AS ENUM (
    'none',
    'eyelet',
    'skirt',
    'velcro'
);


ALTER TYPE public.process_kind OWNER TO postgres;

--
-- Name: product_type; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.product_type AS ENUM (
    'single',
    'two_sheet_set',
    'skirt'
);


ALTER TYPE public.product_type OWNER TO postgres;

--
-- Name: sales_channel; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.sales_channel AS ENUM (
    'rakuten',
    'amazon',
    'yahoo',
    'base_ec'
);


ALTER TYPE public.sales_channel OWNER TO postgres;

--
-- Name: scan_event_type; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.scan_event_type AS ENUM (
    'start',
    'complete',
    'undo'
);


ALTER TYPE public.scan_event_type OWNER TO postgres;

--
-- Name: shipping_status; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.shipping_status AS ENUM (
    'ready',
    'label_printed',
    'handed_to_sagawa',
    'completed'
);


ALTER TYPE public.shipping_status OWNER TO postgres;

--
-- Name: sync_action; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.sync_action AS ENUM (
    'import_order',
    'confirm_payment',
    'issue_label',
    'update_shipping',
    'cancel'
);


ALTER TYPE public.sync_action OWNER TO postgres;

--
-- Name: sync_status; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.sync_status AS ENUM (
    'success',
    'failed'
);


ALTER TYPE public.sync_status OWNER TO postgres;

--
-- Name: sync_system; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.sync_system AS ENUM (
    'rakuten',
    'amazon',
    'yahoo',
    'base_ec',
    'bizlogi',
    'sagawa'
);


ALTER TYPE public.sync_system OWNER TO postgres;

--
-- Name: set_updated_at(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.set_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$;


ALTER FUNCTION public.set_updated_at() OWNER TO postgres;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: accessories; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.accessories (
    id bigint NOT NULL,
    name text NOT NULL,
    remain integer DEFAULT 0 NOT NULL,
    capacity integer DEFAULT 10 NOT NULL,
    unit text DEFAULT '個'::text NOT NULL,
    sort_order smallint DEFAULT 0 NOT NULL,
    reorder_point integer DEFAULT 5 NOT NULL
);


ALTER TABLE public.accessories OWNER TO postgres;

--
-- Name: accessories_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.accessories ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.accessories_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: fabric_inventory; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.fabric_inventory (
    fabric_type public.fabric_type NOT NULL,
    remain_rolls integer DEFAULT 0 NOT NULL,
    capacity_rolls integer DEFAULT 10 NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    reorder_point integer DEFAULT 3 NOT NULL
);


ALTER TABLE public.fabric_inventory OWNER TO postgres;

--
-- Name: fire_safety_report_items; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.fire_safety_report_items (
    id bigint NOT NULL,
    report_id bigint NOT NULL,
    order_no text NOT NULL,
    sold_at date NOT NULL,
    channel public.sales_channel NOT NULL,
    product_type public.product_type NOT NULL,
    fabric_type public.fabric_type NOT NULL,
    width_mm integer,
    height_mm integer,
    quantity integer DEFAULT 1 NOT NULL,
    amount numeric(12,2),
    buyer_name text,
    buyer_address text,
    delivery_name text,
    delivery_address text,
    fire_cert_no text,
    note text
);


ALTER TABLE public.fire_safety_report_items OWNER TO postgres;

--
-- Name: fire_safety_report_items_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.fire_safety_report_items ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.fire_safety_report_items_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: fire_safety_reports; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.fire_safety_reports (
    id bigint NOT NULL,
    report_month date NOT NULL,
    status text DEFAULT 'draft'::text NOT NULL,
    generated_at timestamp with time zone DEFAULT now() NOT NULL,
    exported_at timestamp with time zone,
    file_path text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.fire_safety_reports OWNER TO postgres;

--
-- Name: fire_safety_reports_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.fire_safety_reports ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.fire_safety_reports_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: inventory_transactions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.inventory_transactions (
    id bigint NOT NULL,
    kind text NOT NULL,
    fabric_type public.fabric_type,
    accessory_id bigint,
    delta integer NOT NULL,
    reason text NOT NULL,
    balance_after integer,
    note text,
    worker text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT inventory_transactions_kind_check CHECK ((kind = ANY (ARRAY['fabric'::text, 'accessory'::text]))),
    CONSTRAINT inventory_transactions_reason_check CHECK ((reason = ANY (ARRAY['in'::text, 'out'::text, 'adjust'::text])))
);


ALTER TABLE public.inventory_transactions OWNER TO postgres;

--
-- Name: inventory_transactions_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.inventory_transactions ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.inventory_transactions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: order_items; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.order_items (
    id bigint NOT NULL,
    order_id bigint NOT NULL,
    item_no smallint NOT NULL,
    barcode text NOT NULL,
    product_type public.product_type DEFAULT 'single'::public.product_type NOT NULL,
    fabric_type public.fabric_type NOT NULL,
    width_mm integer NOT NULL,
    height_mm integer NOT NULL,
    quantity integer DEFAULT 1 NOT NULL,
    process_top public.process_kind DEFAULT 'none'::public.process_kind NOT NULL,
    process_top_mm integer,
    process_bottom public.process_kind DEFAULT 'none'::public.process_kind NOT NULL,
    process_bottom_mm integer,
    process_left public.process_kind DEFAULT 'none'::public.process_kind NOT NULL,
    process_left_mm integer,
    process_right public.process_kind DEFAULT 'none'::public.process_kind NOT NULL,
    process_right_mm integer,
    fire_cert_no text,
    current_stage smallint DEFAULT 0 NOT NULL,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT order_items_height_mm_check CHECK ((height_mm > 0)),
    CONSTRAINT order_items_quantity_check CHECK ((quantity > 0)),
    CONSTRAINT order_items_width_mm_check CHECK ((width_mm > 0))
);


ALTER TABLE public.order_items OWNER TO postgres;

--
-- Name: order_items_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.order_items ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.order_items_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: orders; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.orders (
    id bigint NOT NULL,
    order_no text NOT NULL,
    channel public.sales_channel NOT NULL,
    mall_order_no text,
    customer_name text NOT NULL,
    postal_code text,
    address text,
    phone text,
    payment_status public.payment_status DEFAULT 'pending'::public.payment_status NOT NULL,
    order_status public.order_status DEFAULT 'imported'::public.order_status NOT NULL,
    raw_data jsonb,
    ordered_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.orders OWNER TO postgres;

--
-- Name: orders_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.orders ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.orders_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: print_jobs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.print_jobs (
    id bigint NOT NULL,
    order_id bigint,
    target_type public.print_target_type NOT NULL,
    target_id bigint,
    printer_type public.printer_type NOT NULL,
    file_path text,
    status public.print_status DEFAULT 'waiting'::public.print_status NOT NULL,
    error_message text,
    printed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.print_jobs OWNER TO postgres;

--
-- Name: print_jobs_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.print_jobs ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.print_jobs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: production_stages; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.production_stages (
    stage_no smallint NOT NULL,
    code text NOT NULL,
    name_ja text NOT NULL,
    name_ko text NOT NULL,
    proc_key text,
    phase text,
    sort_order smallint NOT NULL,
    CONSTRAINT production_stages_stage_no_check CHECK (((stage_no >= 0) AND (stage_no <= 8)))
);


ALTER TABLE public.production_stages OWNER TO postgres;

--
-- Name: TABLE production_stages; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.production_stages IS '工程マスタ。order_items.current_stage(0〜8)の参照先。奇数=作業中, 偶数=完了';


--
-- Name: scan_events; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.scan_events (
    id bigint NOT NULL,
    order_item_id bigint NOT NULL,
    stage_no smallint NOT NULL,
    event_type public.scan_event_type NOT NULL,
    station text,
    worker text,
    note text,
    scanned_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.scan_events OWNER TO postgres;

--
-- Name: scan_events_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.scan_events ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.scan_events_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: settings; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.settings (
    key text NOT NULL,
    value text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.settings OWNER TO postgres;

--
-- Name: shipments; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.shipments (
    id bigint NOT NULL,
    order_id bigint NOT NULL,
    shipment_no text NOT NULL,
    package_no smallint DEFAULT 1 NOT NULL,
    package_count smallint DEFAULT 1 NOT NULL,
    size_class text,
    weight_kg numeric(6,2),
    carrier text DEFAULT 'sagawa'::text NOT NULL,
    tracking_no text,
    bizlogi_status public.bizlogi_status DEFAULT 'not_requested'::public.bizlogi_status NOT NULL,
    shipping_status public.shipping_status DEFAULT 'ready'::public.shipping_status NOT NULL,
    label_pdf_path text,
    shipped_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.shipments OWNER TO postgres;

--
-- Name: shipments_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.shipments ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.shipments_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: sync_logs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.sync_logs (
    id bigint NOT NULL,
    order_id bigint,
    system public.sync_system NOT NULL,
    action public.sync_action NOT NULL,
    status public.sync_status NOT NULL,
    request_data jsonb,
    response_data jsonb,
    error_message text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.sync_logs OWNER TO postgres;

--
-- Name: sync_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

ALTER TABLE public.sync_logs ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.sync_logs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Data for Name: accessories; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.accessories (id, name, remain, capacity, unit, sort_order, reorder_point) FROM stdin;
1	ハトメ	8	20	箱	1	5
2	ウェビング	3	15	巻	2	5
3	糸	12	30	個	3	5
4	ベルクロ	2	10	巻	4	5
\.


--
-- Data for Name: fabric_inventory; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.fabric_inventory (fabric_type, remain_rolls, capacity_rolls, updated_at, reorder_point) FROM stdin;
LN	6	10	2026-07-13 12:04:44.477113+09	3
SDP	5	10	2026-07-13 12:04:44.477113+09	3
DP	7	10	2026-07-13 13:57:44.829926+09	3
\.


--
-- Data for Name: fire_safety_report_items; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.fire_safety_report_items (id, report_id, order_no, sold_at, channel, product_type, fabric_type, width_mm, height_mm, quantity, amount, buyer_name, buyer_address, delivery_name, delivery_address, fire_cert_no, note) FROM stdin;
\.


--
-- Data for Name: fire_safety_reports; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.fire_safety_reports (id, report_month, status, generated_at, exported_at, file_path, created_at) FROM stdin;
\.


--
-- Data for Name: inventory_transactions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.inventory_transactions (id, kind, fabric_type, accessory_id, delta, reason, balance_after, note, worker, created_at) FROM stdin;
1	fabric	DP	\N	5	in	7	\N	\N	2026-07-13 13:57:44.829926+09
\.


--
-- Data for Name: order_items; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.order_items (id, order_id, item_no, barcode, product_type, fabric_type, width_mm, height_mm, quantity, process_top, process_top_mm, process_bottom, process_bottom_mm, process_left, process_left_mm, process_right, process_right_mm, fire_cert_no, current_stage, started_at, completed_at, created_at, updated_at) FROM stdin;
1	1	1	ORD-20260713-0001-01	two_sheet_set	SDP	4000	3000	1	eyelet	300	eyelet	300	eyelet	200	skirt	\N	TEST-26071301	0	\N	\N	2026-07-13 13:05:57.810248+09	2026-07-13 13:05:57.810248+09
5	5	1	CDI260713001LN01	single	LN	6000	3000	1	eyelet	\N	skirt	\N	eyelet	\N	eyelet	\N	asdasdasd	0	\N	\N	2026-07-13 18:04:10.098183+09	2026-07-13 18:04:10.098183+09
2	2	1	ORD-20260713-0002-01	single	SDP	4000	3000	1	eyelet	200	skirt	\N	eyelet	300	eyelet	300	test-26071302	8	2026-07-13 13:30:32.036493+09	2026-07-13 13:32:32.682746+09	2026-07-13 13:29:41.912176+09	2026-07-13 13:32:32.682746+09
4	4	1	ORD-20260713-0004-01	single	DP	5000	4000	1	velcro	333	eyelet	221	velcro	432	eyelet	122	\N	2	2026-07-13 14:35:53.698661+09	\N	2026-07-13 14:34:51.386257+09	2026-07-13 14:36:07.117047+09
3	3	1	ORD-20260713-0003-01	two_sheet_set	DP	5000	3000	2	eyelet	200	skirt	\N	eyelet	300	eyelet	300	test-26071302	4	2026-07-13 14:00:13.630361+09	\N	2026-07-13 13:59:16.233338+09	2026-07-13 18:00:57.583413+09
\.


--
-- Data for Name: orders; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.orders (id, order_no, channel, mall_order_no, customer_name, postal_code, address, phone, payment_status, order_status, raw_data, ordered_at, created_at, updated_at) FROM stdin;
1	ORD-20260713-0001	rakuten	TEST-26071301	桃太郎	4910031	愛知県一宮市	08061562173	paid	confirmed	{"items": [{"quantity": 1, "width_mm": 4000, "height_mm": 3000, "fabric_type": "SDP", "process_top": "eyelet", "fire_cert_no": "TEST-26071301", "process_left": "eyelet", "product_type": "two_sheet_set", "process_right": "skirt", "process_bottom": "eyelet", "process_top_mm": 300, "process_left_mm": 200, "process_right_mm": null, "process_bottom_mm": 300}], "phone": "08061562173", "address": "愛知県一宮市", "channel": "rakuten", "ordered_at": null, "postal_code": "4910031", "customer_name": "桃太郎", "mall_order_no": "TEST-26071301", "payment_status": "paid"}	2026-07-13 13:05:57.813561+09	2026-07-13 13:05:57.810248+09	2026-07-13 13:05:57.810248+09
2	ORD-20260713-0002	rakuten	test-26071302	ジョンヒョンジュン	4910032	愛知県一宮市	08061562173	paid	confirmed	{"items": [{"quantity": 1, "width_mm": 4000, "height_mm": 3000, "fabric_type": "SDP", "process_top": "eyelet", "fire_cert_no": "test-26071302", "process_left": "eyelet", "product_type": "single", "process_right": "eyelet", "process_bottom": "skirt", "process_top_mm": 200, "process_left_mm": 300, "process_right_mm": 300, "process_bottom_mm": null}], "phone": "08061562173", "address": "愛知県一宮市", "channel": "rakuten", "ordered_at": null, "postal_code": "4910032", "customer_name": "ジョンヒョンジュン", "mall_order_no": "test-26071302", "payment_status": "paid"}	2026-07-13 13:29:41.914115+09	2026-07-13 13:29:41.912176+09	2026-07-13 13:29:41.912176+09
3	ORD-20260713-0003	rakuten	test-26071303	testsan	4910032	愛知県一宮市	08061562111	paid	confirmed	{"items": [{"quantity": 2, "width_mm": 5000, "height_mm": 3000, "fabric_type": "DP", "process_top": "eyelet", "fire_cert_no": "test-26071302", "process_left": "eyelet", "product_type": "two_sheet_set", "process_right": "eyelet", "process_bottom": "skirt", "process_top_mm": 200, "process_left_mm": 300, "process_right_mm": 300, "process_bottom_mm": null}], "phone": "08061562111", "address": "愛知県一宮市", "channel": "rakuten", "ordered_at": null, "postal_code": "4910032", "customer_name": "testsan", "mall_order_no": "test-26071303", "payment_status": "paid"}	2026-07-13 13:59:16.236244+09	2026-07-13 13:59:16.233338+09	2026-07-13 13:59:16.233338+09
4	ORD-20260713-0004	rakuten	test-26071304	テストさん	4910032	愛知県一宮市	１２３１２３１２３１２３	paid	confirmed	{"items": [{"quantity": 1, "width_mm": 5000, "height_mm": 4000, "fabric_type": "DP", "process_top": "velcro", "fire_cert_no": null, "process_left": "velcro", "product_type": "single", "process_right": "eyelet", "process_bottom": "eyelet", "process_top_mm": 333, "process_left_mm": 432, "process_right_mm": 122, "process_bottom_mm": 221}], "phone": "１２３１２３１２３１２３", "address": "愛知県一宮市", "channel": "rakuten", "ordered_at": null, "postal_code": "4910032", "customer_name": "テストさん", "mall_order_no": "test-26071304", "payment_status": "paid"}	2026-07-13 14:34:51.389201+09	2026-07-13 14:34:51.386257+09	2026-07-13 14:34:51.386257+09
5	CDI260713001	rakuten	dd1	テストさん	4910032	仁川広域市 弥鄒忽区 落島中路　32-17 202号	123123123123	paid	confirmed	{"items": [{"quantity": 1, "width_mm": 6000, "height_mm": 3000, "fabric_type": "LN", "process_top": "eyelet", "fire_cert_no": "asdasdasd", "process_left": "eyelet", "product_type": "single", "process_right": "eyelet", "process_bottom": "skirt", "process_top_mm": null, "process_left_mm": null, "process_right_mm": null, "process_bottom_mm": null}], "phone": "123123123123", "address": "仁川広域市 弥鄒忽区 落島中路　32-17 202号", "channel": "rakuten", "ordered_at": null, "postal_code": "4910032", "customer_name": "テストさん", "mall_order_no": "dd1", "payment_status": "paid"}	2026-07-13 18:04:10.101213+09	2026-07-13 18:04:10.098183+09	2026-07-13 18:04:10.098183+09
\.


--
-- Data for Name: print_jobs; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.print_jobs (id, order_id, target_type, target_id, printer_type, file_path, status, error_message, printed_at, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: production_stages; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.production_stages (stage_no, code, name_ja, name_ko, proc_key, phase, sort_order) FROM stdin;
0	received	受付	접수	\N	\N	0
1	cutting_wip	裁断中	재단중	cutting	wip	1
2	cutting_done	裁断完了	재단완료	cutting	done	2
3	sewing_wip	ミシン中	미싱중	sewing	wip	3
4	sewing_done	ミシン完了	미싱완료	sewing	done	4
5	eyelet_wip	ハトメ中	하토메중	eyelet	wip	5
6	eyelet_done	ハトメ完了	하토메완료	eyelet	done	6
7	packing_wip	梱包中	포장중	packing	wip	7
8	packing_done	梱包完了	포장완료	packing	done	8
\.


--
-- Data for Name: scan_events; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.scan_events (id, order_item_id, stage_no, event_type, station, worker, note, scanned_at) FROM stdin;
1	2	1	start	worker_screen	\N	\N	2026-07-13 13:30:32.036493+09
2	2	2	complete	worker_screen	\N	\N	2026-07-13 13:30:34.395316+09
3	2	3	start	worker_screen	\N	\N	2026-07-13 13:30:35.642553+09
4	2	4	complete	worker_screen	\N	\N	2026-07-13 13:30:37.162336+09
5	2	5	start	worker_screen	\N	\N	2026-07-13 13:30:39.689556+09
6	2	6	complete	worker_screen	\N	\N	2026-07-13 13:30:43.078035+09
7	2	7	start	worker_screen	\N	\N	2026-07-13 13:30:45.284666+09
8	2	8	complete	worker_screen	\N	\N	2026-07-13 13:30:46.181915+09
9	2	7	undo	worker_screen	\N	\N	2026-07-13 13:31:44.64517+09
10	2	6	undo	worker_screen	\N	\N	2026-07-13 13:32:07.54636+09
11	2	7	start	worker_screen	\N	\N	2026-07-13 13:32:07.593824+09
12	2	6	undo	worker_screen	\N	\N	2026-07-13 13:32:09.197711+09
13	2	7	start	worker_screen	\N	\N	2026-07-13 13:32:09.246917+09
14	2	6	undo	worker_screen	\N	\N	2026-07-13 13:32:10.076558+09
15	2	7	start	worker_screen	\N	\N	2026-07-13 13:32:10.122543+09
16	2	6	undo	worker_screen	\N	\N	2026-07-13 13:32:11.233722+09
17	2	7	start	worker_screen	\N	\N	2026-07-13 13:32:11.279828+09
18	2	6	undo	worker_screen	\N	\N	2026-07-13 13:32:14.015195+09
19	2	7	start	worker_screen	\N	\N	2026-07-13 13:32:23.517038+09
20	2	8	complete	worker_screen	\N	\N	2026-07-13 13:32:32.682746+09
21	3	1	start	worker_screen	\N	\N	2026-07-13 14:00:13.630361+09
22	3	2	complete	worker_screen	\N	\N	2026-07-13 14:00:40.432653+09
23	3	3	start	worker_screen	\N	\N	2026-07-13 14:00:55.685331+09
24	3	4	complete	worker_screen	\N	\N	2026-07-13 14:06:12.754706+09
25	4	1	start	worker_screen	\N	\N	2026-07-13 14:35:53.698661+09
26	3	5	start	worker_screen	\N	\N	2026-07-13 14:36:00.281093+09
27	4	2	complete	worker_screen	\N	\N	2026-07-13 14:36:07.117047+09
28	3	6	complete	worker_screen	\N	\N	2026-07-13 14:36:12.124593+09
29	3	5	undo	worker_screen	\N	\N	2026-07-13 14:36:18.916411+09
30	3	4	undo	worker_screen	\N	\N	2026-07-13 15:51:41.031709+09
31	3	3	undo	worker_screen	\N	\N	2026-07-13 15:51:41.645158+09
32	3	2	undo	worker_screen	\N	\N	2026-07-13 15:51:41.811232+09
33	3	1	undo	worker_screen	\N	\N	2026-07-13 15:51:41.958522+09
34	3	0	undo	worker_screen	\N	\N	2026-07-13 15:51:42.102849+09
35	3	1	start	worker_screen	\N	\N	2026-07-13 16:13:50.18229+09
36	3	2	complete	worker_screen	\N	\N	2026-07-13 16:14:00.412493+09
37	3	3	start	worker_screen	\N	\N	2026-07-13 16:14:09.707973+09
38	3	4	complete	worker_screen	\N	\N	2026-07-13 16:14:15.083841+09
39	3	5	start	monitor_eyelet	\N	\N	2026-07-13 16:26:00.683039+09
40	3	6	complete	monitor_eyelet	\N	\N	2026-07-13 16:26:06.31375+09
41	3	7	start	worker_screen	\N	\N	2026-07-13 18:00:19.031458+09
42	3	6	undo	worker_screen	\N	\N	2026-07-13 18:00:25.044581+09
43	3	5	undo	worker_screen	\N	\N	2026-07-13 18:00:25.245675+09
44	3	4	undo	worker_screen	\N	\N	2026-07-13 18:00:25.486296+09
45	3	3	undo	worker_screen	\N	\N	2026-07-13 18:00:26.644031+09
46	3	2	undo	worker_screen	\N	\N	2026-07-13 18:00:30.870454+09
47	3	3	start	worker_screen	\N	\N	2026-07-13 18:00:30.96831+09
48	3	2	undo	worker_screen	\N	\N	2026-07-13 18:00:32.170229+09
49	3	3	start	worker_screen	\N	\N	2026-07-13 18:00:32.369534+09
50	3	2	undo	worker_screen	\N	\N	2026-07-13 18:00:37.263853+09
51	3	3	start	worker_screen	\N	\N	2026-07-13 18:00:37.419311+09
52	3	2	undo	worker_screen	\N	\N	2026-07-13 18:00:40.224602+09
53	3	3	start	worker_screen	\N	\N	2026-07-13 18:00:40.31157+09
54	3	2	undo	worker_screen	\N	\N	2026-07-13 18:00:42.641281+09
55	3	3	start	worker_screen	\N	\N	2026-07-13 18:00:42.780216+09
56	3	2	undo	worker_screen	\N	\N	2026-07-13 18:00:45.405925+09
57	3	3	start	worker_screen	\N	\N	2026-07-13 18:00:45.709733+09
58	3	2	undo	worker_screen	\N	\N	2026-07-13 18:00:46.613325+09
59	3	3	start	worker_screen	\N	\N	2026-07-13 18:00:46.714701+09
60	3	2	undo	worker_screen	\N	\N	2026-07-13 18:00:48.793736+09
61	3	3	start	worker_screen	\N	\N	2026-07-13 18:00:48.891517+09
62	3	4	complete	worker_screen	\N	\N	2026-07-13 18:00:57.583413+09
\.


--
-- Data for Name: settings; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.settings (key, value, updated_at) FROM stdin;
admin_password	1234	2026-07-13 13:57:02.301817+09
printer_work	a4	2026-07-13 13:57:02.301817+09
printer_label	label	2026-07-13 13:57:02.301817+09
printer_ship	sato_cf408t	2026-07-13 13:57:02.301817+09
\.


--
-- Data for Name: shipments; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.shipments (id, order_id, shipment_no, package_no, package_count, size_class, weight_kg, carrier, tracking_no, bizlogi_status, shipping_status, label_pdf_path, shipped_at, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: sync_logs; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.sync_logs (id, order_id, system, action, status, request_data, response_data, error_message, created_at) FROM stdin;
\.


--
-- Name: accessories_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.accessories_id_seq', 4, true);


--
-- Name: fire_safety_report_items_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.fire_safety_report_items_id_seq', 1, false);


--
-- Name: fire_safety_reports_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.fire_safety_reports_id_seq', 1, false);


--
-- Name: inventory_transactions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.inventory_transactions_id_seq', 1, true);


--
-- Name: order_items_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.order_items_id_seq', 5, true);


--
-- Name: orders_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.orders_id_seq', 5, true);


--
-- Name: print_jobs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.print_jobs_id_seq', 1, false);


--
-- Name: scan_events_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.scan_events_id_seq', 62, true);


--
-- Name: shipments_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.shipments_id_seq', 1, false);


--
-- Name: sync_logs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.sync_logs_id_seq', 1, false);


--
-- Name: accessories accessories_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.accessories
    ADD CONSTRAINT accessories_pkey PRIMARY KEY (id);


--
-- Name: fabric_inventory fabric_inventory_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.fabric_inventory
    ADD CONSTRAINT fabric_inventory_pkey PRIMARY KEY (fabric_type);


--
-- Name: fire_safety_report_items fire_safety_report_items_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.fire_safety_report_items
    ADD CONSTRAINT fire_safety_report_items_pkey PRIMARY KEY (id);


--
-- Name: fire_safety_reports fire_safety_reports_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.fire_safety_reports
    ADD CONSTRAINT fire_safety_reports_pkey PRIMARY KEY (id);


--
-- Name: inventory_transactions inventory_transactions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.inventory_transactions
    ADD CONSTRAINT inventory_transactions_pkey PRIMARY KEY (id);


--
-- Name: order_items order_items_barcode_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.order_items
    ADD CONSTRAINT order_items_barcode_key UNIQUE (barcode);


--
-- Name: order_items order_items_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.order_items
    ADD CONSTRAINT order_items_pkey PRIMARY KEY (id);


--
-- Name: orders orders_order_no_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_order_no_key UNIQUE (order_no);


--
-- Name: orders orders_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_pkey PRIMARY KEY (id);


--
-- Name: print_jobs print_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.print_jobs
    ADD CONSTRAINT print_jobs_pkey PRIMARY KEY (id);


--
-- Name: production_stages production_stages_code_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.production_stages
    ADD CONSTRAINT production_stages_code_key UNIQUE (code);


--
-- Name: production_stages production_stages_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.production_stages
    ADD CONSTRAINT production_stages_pkey PRIMARY KEY (stage_no);


--
-- Name: scan_events scan_events_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.scan_events
    ADD CONSTRAINT scan_events_pkey PRIMARY KEY (id);


--
-- Name: settings settings_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.settings
    ADD CONSTRAINT settings_pkey PRIMARY KEY (key);


--
-- Name: shipments shipments_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.shipments
    ADD CONSTRAINT shipments_pkey PRIMARY KEY (id);


--
-- Name: shipments shipments_shipment_no_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.shipments
    ADD CONSTRAINT shipments_shipment_no_key UNIQUE (shipment_no);


--
-- Name: sync_logs sync_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sync_logs
    ADD CONSTRAINT sync_logs_pkey PRIMARY KEY (id);


--
-- Name: fire_safety_reports uq_fire_reports_month; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.fire_safety_reports
    ADD CONSTRAINT uq_fire_reports_month UNIQUE (report_month);


--
-- Name: order_items uq_order_items_order_itemno; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.order_items
    ADD CONSTRAINT uq_order_items_order_itemno UNIQUE (order_id, item_no);


--
-- Name: orders uq_orders_channel_mall_no; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT uq_orders_channel_mall_no UNIQUE (channel, mall_order_no);


--
-- Name: shipments uq_shipments_order_pkg; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.shipments
    ADD CONSTRAINT uq_shipments_order_pkg UNIQUE (order_id, package_no);


--
-- Name: idx_fire_items_report_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_fire_items_report_id ON public.fire_safety_report_items USING btree (report_id);


--
-- Name: idx_inv_tx_ref; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_inv_tx_ref ON public.inventory_transactions USING btree (kind, fabric_type, accessory_id);


--
-- Name: idx_inv_tx_time; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_inv_tx_time ON public.inventory_transactions USING btree (created_at);


--
-- Name: idx_order_items_barcode; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_order_items_barcode ON public.order_items USING btree (barcode);


--
-- Name: idx_order_items_order_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_order_items_order_id ON public.order_items USING btree (order_id);


--
-- Name: idx_order_items_stage; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_order_items_stage ON public.order_items USING btree (current_stage);


--
-- Name: idx_orders_ordered_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_orders_ordered_at ON public.orders USING btree (ordered_at);


--
-- Name: idx_orders_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_orders_status ON public.orders USING btree (order_status);


--
-- Name: idx_print_jobs_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_print_jobs_status ON public.print_jobs USING btree (status);


--
-- Name: idx_scan_events_item_time; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_scan_events_item_time ON public.scan_events USING btree (order_item_id, scanned_at);


--
-- Name: idx_scan_events_time; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_scan_events_time ON public.scan_events USING btree (scanned_at);


--
-- Name: idx_shipments_order_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_shipments_order_id ON public.shipments USING btree (order_id);


--
-- Name: idx_sync_logs_created; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_sync_logs_created ON public.sync_logs USING btree (created_at);


--
-- Name: order_items trg_order_items_updated_at; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_order_items_updated_at BEFORE UPDATE ON public.order_items FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: orders trg_orders_updated_at; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_orders_updated_at BEFORE UPDATE ON public.orders FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: print_jobs trg_print_jobs_updated_at; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_print_jobs_updated_at BEFORE UPDATE ON public.print_jobs FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: shipments trg_shipments_updated_at; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trg_shipments_updated_at BEFORE UPDATE ON public.shipments FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: fire_safety_report_items fire_safety_report_items_report_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.fire_safety_report_items
    ADD CONSTRAINT fire_safety_report_items_report_id_fkey FOREIGN KEY (report_id) REFERENCES public.fire_safety_reports(id) ON DELETE CASCADE;


--
-- Name: inventory_transactions inventory_transactions_accessory_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.inventory_transactions
    ADD CONSTRAINT inventory_transactions_accessory_id_fkey FOREIGN KEY (accessory_id) REFERENCES public.accessories(id) ON DELETE CASCADE;


--
-- Name: order_items order_items_current_stage_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.order_items
    ADD CONSTRAINT order_items_current_stage_fkey FOREIGN KEY (current_stage) REFERENCES public.production_stages(stage_no);


--
-- Name: order_items order_items_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.order_items
    ADD CONSTRAINT order_items_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id) ON DELETE CASCADE;


--
-- Name: print_jobs print_jobs_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.print_jobs
    ADD CONSTRAINT print_jobs_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id) ON DELETE CASCADE;


--
-- Name: scan_events scan_events_order_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.scan_events
    ADD CONSTRAINT scan_events_order_item_id_fkey FOREIGN KEY (order_item_id) REFERENCES public.order_items(id) ON DELETE CASCADE;


--
-- Name: scan_events scan_events_stage_no_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.scan_events
    ADD CONSTRAINT scan_events_stage_no_fkey FOREIGN KEY (stage_no) REFERENCES public.production_stages(stage_no);


--
-- Name: shipments shipments_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.shipments
    ADD CONSTRAINT shipments_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id) ON DELETE CASCADE;


--
-- Name: sync_logs sync_logs_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sync_logs
    ADD CONSTRAINT sync_logs_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id) ON DELETE SET NULL;


--
-- PostgreSQL database dump complete
--

\unrestrict Tcxu6L70QLyCdg054kgttFSBMx5NgLH2GrdYo1HWrgwP2cH43IMr2TAxwnxYKdy

