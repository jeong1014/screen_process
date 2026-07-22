# app.py 모듈 분리 — ✅ 작업 완료 (브랜치 `refactor/split-app`)

**코드 분리와 자동 검증은 전부 끝났습니다. 남은 건 실기 스모크 테스트 하나뿐입니다.**

| | 누가 | 상태 |
|---|---|---|
| 1~3장 (설계) | Claude | ✅ |
| 4장 (0~6단계 실행) | Claude | ✅ 커밋 6개 |
| 5장 자동 검사 | Claude | ✅ 통과 |
| **5장 실기 스모크** | **정현준** | 🔴 **남음** |
| 6장 부수 정리 | Claude | ✅ |

실행: `uvicorn main:app --host 0.0.0.0 --port 8000` (기존 `app:app` 도 그대로 동작)


- 대상: `screen_system/app.py` (1938줄, 라우트 약 70개)
- 범위: 백엔드만. 프론트엔드(`frontend/*.html`)는 이번에 손대지 않음
- 원칙: **동작 변경 0**. 파일만 옮기고, 엔드포인트 경로·응답 스키마는 그대로 유지

---

## 1. 현재 구조 분석

app.py 안에 섞여 있는 관심사:

| 영역 | 현재 위치(줄) | 규모 |
|---|---|---|
| 설정 상수 | 36~39, 52~61 | 소 |
| 표시용 포맷 함수 | 64~144 | 중 |
| 프린터 제어 | 146~193 | 중 |
| Pydantic 모델 | 198~238 (+ 곳곳에 산재) | 중 |
| 페이지 서빙(HTML) | 243~289, 554~565, 642~645, 851~861, 1742~1747 | 중 |
| 주문 입력 | 294~384 | 중 |
| 작업자 스캔 | 389~467 | 중 |
| 대시보드 | 472~547 | 중 |
| 라벨 | 567~605 | 소 |
| 관리자 인증 | 610~658 | 소 |
| 관리자 재고(구) | 661~837 | 대 |
| QR 재고 v2 | 847~1054 | 대 |
| 발주/메일 | 1059~1259 | 대 |
| 관리자 주문 | 1262~1411 | 대 |
| 출하/인쇄/로그 | 1414~1488 | 중 |
| 소방법/통계/CSV | 1491~1586 | 중 |
| 설정 | 1589~1610 | 소 |
| DB 뷰어 | 1615~1686 | 중 |
| 공정별 모니터 | 1693~1829 | 대 |
| 시리얼 스캐너 스레드 | 1834~1938 | 대 |

### 구조적 문제

1. **import가 파일 중간에 흩어져 있음** — 610행(`Header`, `Query`, `Response`, `csv`, `io`), 1615행(`psycopg.sql`), 1834행(`threading`, `serial` 등). 파일을 자를 때 이게 어디에 필요한지 추적이 필요함
2. **`import code`(14행)는 미사용** — 삭제 대상
3. **시리얼 스캐너가 라우트 핸들러를 직접 호출** — `api_inv_scan()`, `api_monitor_scan()`, `_move()`를 함수로 직접 부름. **이게 이번 분리의 핵심 난점.** 그냥 나누면 `scanner → routers → services → scanner` 순환 import가 남
4. **`@app.on_event("startup")`은 deprecated** — 옮기는 김에 `lifespan`으로 교체

---

## 2. 목표 구조 (13개 파일)

```
screen_system/
├── main.py                 앱 생성 · 미들웨어 · 라우터 등록 · lifespan   (~60줄)
├── config.py               DATABASE_URL, FRONTEND_DIR, MAX_STAGE,
│                           SIDE_JA / PROC_BY_STAGE / STAGE_NAME /
│                           MON_PROC / INV_GROUPS / DB_TABLES        (~90줄)
├── db.py                   db() 커넥션, _get_setting, _set_setting   (~40줄)
├── security.py             require_admin, _check_pw_query,
│                           _admin_password                          (~40줄)
├── schemas.py              Pydantic 모델 전부 (ItemIn, OrderIn,
│                           ScanIn, AdjustIn, InvIssueIn …)          (~180줄)
├── services/
│   ├── formatting.py       fmt_opt, eyelet_val, size_str, qty_str,
│   │                       item_sides, worker_payload, board_status,
│   │                       _proc, stage_to_proc, _proc_fields       (~200줄)
│   ├── printing.py         get_printer_name, silent_print_html      (~60줄)
│   ├── mailer.py           _smtp_config, _send_purchase_email       (~60줄)
│   ├── stage.py            next_order_no, _fetch_item, _pair_barcode,
│   │                       move_stage(=_move), monitor_scan         (~220줄)
│   ├── inventory.py        inv_scan(재고 QR 차감/입고 로직)          (~120줄)
│   └── scanner.py          load_scanner_config, _serial_reader_worker,
│                           start_serial_scanners                    (~140줄)
├── routers/
│   ├── pages.py            HTML 서빙 전부                            (~90줄)
│   ├── public.py           /api/orders, /api/scan, /api/board,
│   │                       /api/events, /api/inventory,
│   │                       /api/accessories, /api/label,
│   │                       /api/shipping-slip, /api/monitor         (~330줄)
│   └── admin/
│       ├── __init__.py     admin 하위 라우터 집합                    (~20줄)
│       ├── auth.py         로그인                                    (~30줄)
│       ├── inventory.py    구 재고 + QR재고 v2 관리 API              (~300줄)
│       ├── purchase.py     발주 요청/등록/입하/설정                   (~200줄)
│       ├── orders.py       주문 조회/수정/취소/stage 수정             (~160줄)
│       ├── ops.py          출하 · 인쇄 · sync-logs                   (~90줄)
│       ├── reports.py      소방법 · 통계 · CSV export                (~130줄)
│       └── dbviewer.py     DB 뷰어                                   (~80줄)
└── print_templates.py      (변경 없음)
```

파일당 30~330줄. 가장 큰 `routers/admin/inventory.py`도 300줄대로, 현재 app.py의 1/6 수준.

### 의존 방향 (한 방향으로만)

```
main.py
   ↓
routers/*  ──→  services/*  ──→  db.py / config.py / schemas.py
   ↓                ↓
security.py    printing.py, mailer.py
```

`services`는 `routers`를 절대 import하지 않음. 이 규칙 하나로 순환 import가 원천 차단됨.

---

## 3. 핵심 설계 결정: 스캐너 순환 import 해소

현재 `_serial_reader_worker`는 이렇게 동작함:

```python
if re.match(r"^\d{2,4}-\d{3,6}$", barcode_data):
    result = api_inv_scan(InvScanIn(code=barcode_data))   # 라우트 핸들러 직접 호출
elif scan_type == "monitor":
    result = api_monitor_scan(proc, MonScan(barcode=...))  # 라우트 핸들러 직접 호출
elif scan_type == "worker":
    result = _move(barcode_data, +1)
```

**해결책 — 로직을 services로 내리고, 라우터는 얇은 껍데기로 만든다.**

```python
# services/inventory.py
def inv_scan(code: str) -> dict:      # ← 실제 로직
    ...

# routers/public.py
@router.post("/api/inventory/scan")
def api_inv_scan(body: InvScanIn):
    return inv_scan(body.code)        # ← 껍데기

# services/scanner.py
from services.inventory import inv_scan     # 라우터가 아닌 서비스를 import
from services.stage import move_stage, monitor_scan
```

모니터 스캔 후 송장 자동 출력 블록(1878~1912행)도 `services/shipping.py`나 `services/stage.py`의 `auto_print_slip(order_id)`로 함수화. 지금은 스캐너 스레드 안에 SQL 4개가 인라인으로 박혀 있어서 테스트가 불가능한 상태.

---

## 4. 실행 순서 — ✅ 전부 완료 (Claude 작업분)

아래 0~6단계는 **이미 실행되어 커밋까지 끝났습니다.** 각 단계가 독립 커밋입니다.

| 단계 | 내용 | 커밋 | 상태 |
|---|---|---|---|
| **0** | 브랜치 `refactor/split-app` 생성, API 기준 스냅샷 저장 | `45ffaf7` | ✅ |
| **1** | `config.py`, `schemas.py` 추출 (상수 14개 + 모델 21개) | `c03ced5` | ✅ |
| **2** | `db.py`, `security.py`, `services/printing.py`, `services/mailer.py` | `7c3bf0a` | ✅ |
| **3** | `services/formatting.py` (순수 함수 11개) | `cdba3cc` | ✅ |
| **4** | `services/stage.py` + `inventory.py` + `shipping.py` — 스캐너 순환 import 해소 | `c31f663` | ✅ |
| **5·6** | `routers/` 11개 분리, `main.py` 조립, `lifespan` 전환 | `ea150ca` | ✅ |

> 0단계에서 발견: 작업 트리에 보이던 2520줄 diff는 실제 변경이 아니라 CRLF 줄바꿈 차이였습니다.
> `core.autocrlf=true` 설정으로 해소했고, 그래서 리팩터링 전 상태는 `099d315` 그대로입니다.

---

## 5. 검증 결과

### 자동 검사 — ✅ 통과 (Claude 실행 완료)

| 검사 | 방법 | 결과 |
|---|---|---|
| API 계약 회귀 | `openapi.json` 전후 diff | ✅ 바이트 단위 동일 (63 paths / 69 routes) |
| 로직 동일성 | 원본과 AST 비교 | ✅ 정의 117개 완전 일치 (달라진 10개는 의도한 이름 변경) |
| 미정의 이름 | `pyflakes` | ✅ clean — `api_label`의 `_fetch_item` 누락을 사전 발견해 수정 |
| 라우트 순서 | 동적 세그먼트 가림 검사 | ✅ 문제 없음 |

언제든 다시 돌릴 수 있습니다:

```bash
cd screen_system
python check_api.py verify main          # 라우트 목록 + 순서 검사
python check_api.py dump main > /tmp/after.json
diff openapi_before.json /tmp/after.json # 비어 있어야 성공
```

### 🔴 실기 스모크 — 정현준님이 하실 부분

**여기만 남았습니다.** 실제 DB·프린터·바코드 스캐너가 붙은 공장 PC가 필요해서 자동 검사로는 대체가 안 됩니다.

```bash
cd screen_system
uvicorn main:app --host 0.0.0.0 --port 8000
```

- [ ] 주문 입력 → 라벨 인쇄
- [ ] 작업자 화면 스캔 진행 → UNDO  ← **가장 중요 (4단계에서 건드린 부분)**
- [ ] 공정 모니터 3종(裁断/ミシン/ハトメ) 스캔
- [ ] ハトメ完了 시 송장 자동 출력
- [ ] 재고 QR 발행 → 스캔 차감
- [ ] 관리자 로그인 → 재고/발주/주문/DB뷰어 각 탭
- [ ] CSV export 4종
- [ ] 시리얼 스캐너 스레드 기동 로그(`🚀 [System] …`) 확인

전부 통과하면 `main` 에 머지하세요. 문제가 생기면 `git reset --hard HEAD~1` 로 단계별 되돌리기가 됩니다.

---

## 6. 같이 정리한 것 (덤) — ✅ 완료

- `import code` 삭제 (미사용)
- 중간 import 3곳(구 610·1615·1834행)을 각 파일 상단으로 정리
- `@app.on_event("startup")` → `lifespan` 컨텍스트 매니저
- `_get_setting` / `_set_setting` 을 `db.py` 로 통합
- 하드코딩 경로(`printer_config.json`, `SumatraPDF.exe`, `scanner_config.json`)를 `config.py` 상수로 이관
- `app.py` 는 shim 으로 남겨 기존 `uvicorn app:app` 명령이 계속 동작

### 발견했지만 고치지 않은 것 (동작 변경 금지 원칙)

`services/stage.py` 의 `move_stage()` 송장 자동 출력에서 `orders.order_no` 에 **바코드**를 넣어 조회합니다. 바코드는 `order_items.barcode` 라 조회 결과가 비고, 고객 정보 없이 인쇄됩니다. 시리얼 스캐너 경로(`services/scanner.py`)는 `order_id` 로 제대로 조회하고 있어 두 경로의 동작이 다릅니다. 코드에 `NOTE` 를 달아뒀습니다 — 별건으로 처리 필요.

**손대지 않은 것** (범위를 지키기 위해):

- 프론트엔드 HTML — `label.html`(2734줄) / `label_gorilla.html`(2792줄) 중복, `PROC` 수동 동기화 문제는 다음 작업으로 분리
- DB 스키마·마이그레이션 스크립트
- `print_templates.py`

---

## 7. 롤백

각 단계가 독립 커밋이므로 문제 발생 시 `git reset --hard HEAD~1` 한 번으로 직전 정상 상태 복귀. 최악의 경우 `git checkout main` 으로 통째 원복.
