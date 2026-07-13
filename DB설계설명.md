# 스크린원단 공장 시스템 — DB 설계 설명서

FastAPI + PostgreSQL 기준. `schema.sql`을 그대로 실행하면 아래 9개 테이블이 생성됩니다.
실제 PostgreSQL에서 스키마 적용 및 시나리오 테스트(주문→스캔→출하→소방법 보고)까지 검증 완료했습니다.

---

## 1. 전체 구조 한눈에 보기

```
orders ──1:N──> order_items ──1:N──> scan_events
  │                  │  (current_stage 0~8 = 진행상태의 기준)
  │                  └──> production_stages (공정 마스터, 참조)
  ├──1:N──> shipments        (포장/송장)
  ├──1:N──> print_jobs       (출력 잡)
  └──1:N──> sync_logs        (API 연동 로그)

fire_safety_reports ──1:N──> fire_safety_report_items   (월간 소방법 보고, 별도 계열)
```

핵심 원칙 세 가지:

- **진행상태는 `order_items.current_stage`(0~8) 하나로만 판단한다** — single source of truth.
- **모든 바코드 스캔은 `scan_events`에 한 줄씩 쌓는다** — 시작/완료/취소(UNDO) 전부 이력으로 남음.
- **공정 정의는 `production_stages` 마스터 테이블에 둔다** — 공정을 추가/변경해도 테이블 구조는 안 건드림, 행만 추가.

---

## 2. 테이블별 설명

### production_stages — 공정 마스터 (진행상태 0~8 정의)
공정 목록을 코드가 아니라 데이터로 관리합니다. 지금 값은 이렇게 들어가 있습니다.

| stage_no | code | 日本語 | 한국어 | 스캔대상 |
|---|---|---|---|---|
| 0 | waiting | 未着手 | 대기 | ✗ |
| 1 | fabric_check | 生地確認 | 원단확인 | ✓ |
| 2 | cutting | 裁断 | 재단 | ✓ |
| 3 | sewing | ミシン | 미싱 | ✓ |
| 4 | eyelet_skirt | ハトメ・スカート | 하토메·스커트 | ✓ |
| 5 | inspection | 検品 | 검품 | ✓ |
| 6 | packing | 梱包 | 포장 | ✓ |
| 7 | shipped | 集荷完了 | 집하완료 | ✗ |
| 8 | closed | 完了 | 완료 | ✗ |

나중에 예를 들어 "재단"과 "미싱" 사이에 공정을 하나 넣고 싶으면 이 표에 행을 추가하고 `sort_order`만 조정하면 됩니다. `order_items`나 코드는 안 바꿔도 됩니다. (`stage_no`는 0~99까지 허용해 뒀습니다.)

### orders — 주문 헤더
쇼핑몰(라쿠텐/아마존/야후/BASE)에서 받은 주문 1건 = 1행. 원본 수신 데이터는 `raw_data`(JSONB)에 통째로 보관해서 나중에 재파싱·감사가 가능합니다. `(channel, mall_order_no)` 조합에 UNIQUE를 걸어 같은 주문을 두 번 취임하는 것을 막았습니다. `order_no`는 사내 번호(ORD-YYYYMMDD-0001)로 별도 UNIQUE.

### order_items — 주문 명세 (작업지시서/라벨 1장 = 1행)
작업의 실제 단위입니다. 원단 종류(LN/DP/SDP), 사이즈, 4변 가공(상/하/좌/우 각각 종류 + 치수mm)을 담습니다.

- `barcode`: 라벨에 인쇄되고 작업자가 스캔하는 키. UNIQUE.
- `current_stage`: 지금 어느 공정까지 왔는지(0~8). `production_stages`를 참조(FK).
- `stage_in_progress`: 현재 공정이 "시작 스캔은 됐는데 완료는 안 된" 상태인지. 시작 스캔 시 TRUE, 완료 스캔 시 FALSE.
- `fire_cert_no`: 방염 인증번호(소방법 보고에 쓰임).

### scan_events — 바코드 스캔 이력 (핵심)
작업자가 바코드를 찍을 때마다 한 줄씩 쌓입니다. memory의 "각 공정 2회 스캔(시작+완료) + UNDO" 설계를 그대로 구현한 테이블입니다.

- `event_type`: `start`(시작) / `complete`(완료) / `undo`(오스캔 취소).
- `stage_no`: 어느 공정을 찍었는지.
- `station`, `worker`: 어느 단말/누가 (선택).

**진행상태 갱신 규칙 (애플리케이션 로직):**

1. `start` 스캔 → `scan_events`에 insert + `order_items.stage_in_progress = TRUE`.
2. `complete` 스캔 → insert + `current_stage = 해당 stage_no`, `stage_in_progress = FALSE`.
3. `undo` 스캔 → insert(취소 기록) + 직전 상태로 되돌림(예: `stage_in_progress = FALSE`, 필요 시 `current_stage`를 이전 공정으로).

즉 `current_stage`는 "지금 상태를 빠르게 읽는 캐시", `scan_events`는 "누가 언제 뭘 했는지 전부 남는 원장"입니다. 둘을 분리해서 조회 성능과 추적성을 동시에 얻습니다.

> 참고: 이 갱신을 FastAPI 코드에서 하는 대신 DB 트리거로 자동화할 수도 있습니다. 지금 스키마는 애플리케이션 층 갱신을 전제로 했습니다(제어가 명확하고 UNDO 규칙을 유연하게 짜기 쉬움). 원하시면 트리거 버전도 추가로 만들 수 있습니다.

### shipments — 포장/송장
주문당 개수(package_count/package_no)로 여러 박스 분할 발송을 지원합니다. `bizlogi_status`(발행 요청/발행됨)와 `shipping_status`(준비/라벨출력/사가와인계/완료)를 나눠, "송장은 발행됐지만 아직 집하 전" 같은 상태를 정확히 표현합니다.

### print_jobs — 출력 잡
작업지시서/제품라벨/송장/제어바코드를 어느 프린터(Brother TD-4550 / 라벨 / SATO CF408T / A4)로 뽑을지 관리. `target_type` + `target_id`로 어떤 대상(order_items 또는 shipments)을 출력하는지 가리킵니다. 재출력은 같은 대상으로 새 잡을 하나 더 넣으면 됩니다. 실패 시 `error_message` 기록.

### sync_logs — API 연동 로그
쇼핑몰 주문 취임, 출하완료 반영, BizLogi 송장 발행 등 외부 시스템과 주고받은 요청/응답을 남깁니다. API 오류 화면은 `WHERE status='failed'`로 바로 뽑을 수 있습니다.

### fire_safety_reports / _items — 월간 소방법 보고
방염물품 판매기록 제출용. 월별 헤더(1행) 아래 그 달 판매 명세를 담습니다. 확정→Excel/PDF 출력 상태를 `status`로 관리하고 출력 파일 경로를 `file_path`에 남깁니다.

---

## 3. 화면별 주요 쿼리 (참고)

**담당자 화면** (주문번호·결제·출력·작업·출하 상태 목록):
```sql
SELECT o.order_no, o.channel, o.payment_status,
       oi.barcode, ps.name_ko AS 작업상태, oi.stage_in_progress,
       oi.label_printed_at IS NOT NULL AS 라벨출력됨,
       s.shipping_status
FROM order_items oi
JOIN orders o            ON o.id = oi.order_id
JOIN production_stages ps ON ps.stage_no = oi.current_stage
LEFT JOIN shipments s     ON s.order_id = o.id
ORDER BY o.ordered_at DESC;
```

**작업자 화면** (한 건의 전체 정보): `orders`(고객·주소·전화·채널·결제) + `order_items`(상품·사이즈·가공) + `shipments`(포장수·송장번호)를 order_id로 조인.

**API 오류 화면**: `SELECT * FROM sync_logs WHERE status='failed' ORDER BY created_at DESC;`

**특정 명세 진행 이력** (UNDO 포함 추적):
```sql
SELECT ps.name_ko, se.event_type, se.station, se.scanned_at
FROM scan_events se
JOIN production_stages ps ON ps.stage_no = se.stage_no
WHERE se.order_item_id = :id
ORDER BY se.scanned_at;
```

---

## 4. 기술 메모

- PK는 `BIGINT GENERATED ALWAYS AS IDENTITY`(PostgreSQL 표준 자동증가).
- 상태값은 대부분 PostgreSQL **ENUM 타입**으로 고정 — 오타/잘못된 값을 DB가 거부. (검증에서 `'tiktok'` 채널 삽입이 거부됨을 확인)
- 시각 컬럼은 `TIMESTAMPTZ`(타임존 포함). `updated_at`은 트리거로 자동 갱신.
- 원본/요청/응답 데이터는 `JSONB`로 저장(인덱싱·쿼리 가능).
- 조회 패턴에 맞춰 인덱스 배치(주문 상태, 공정, 바코드, 스캔 시계열, 출하 상태 등).
- 삭제 정책: 주문 삭제 시 하위 명세·스캔·출하·출력잡은 CASCADE 삭제, `sync_logs`는 SET NULL로 로그 보존.

## 5. 향후 확장 여지 (미결정 항목)

- **재고 관리(LN/DP/SDP)**: 별도 `fabric_inventory` 테이블 추가 예정. 현재 스키마엔 미포함.
- **스캔→진행상태 갱신을 DB 트리거로 자동화**할지 여부(현재는 앱 층 처리 전제).
- **출력 자동화 트리거**(webhook vs DB entry) 결정 후 print_jobs 생성 방식 확정.
