# app.py 모듈 분리 계획 — ✅ 완료 (브랜치 `refactor/split-app`)

> **실기 검증이 남아 있습니다.** 아래 6번 항목의 스모크 테스트를 공장 환경에서
> 한 번 돌린 뒤 `main` 에 머지하세요. 특히 **스캔 진행 / UNDO / 송장 자동 출력**.
>
> 실행: `uvicorn main:app --host 0.0.0.0 --port 8000` (기존 `app:app` 도 동작)
> 회귀 검사: `python check_api.py verify main`


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

## 4. 실행 순서 (7단계)

각 단계 끝날 때마다 서버가 정상 기동해야 함. 한 번에 다 옮기지 않음.

| 단계 | 내용 | 위험도 | 검증 |
|---|---|---|---|
| **0** | 브랜치 `refactor/split-app` 생성. `.bak` 3개 정리. **기준 스냅샷 저장**: 서버 띄우고 `/openapi.json`을 `openapi_before.json`으로 저장 | 없음 | — |
| **1** | `config.py`, `schemas.py` 추출. 순수 데이터라 부작용 없음. app.py는 `from config import *` 로 임시 유지 | 낮음 | 서버 기동 |
| **2** | `db.py`, `security.py`, `services/printing.py`, `services/mailer.py` 추출 | 낮음 | 서버 기동 + 라벨 인쇄 1회 |
| **3** | `services/formatting.py` 추출 (순수 함수 뭉치, 의존성 거의 없음) | 낮음 | 대시보드/작업자 화면 로드 |
| **4** | **`services/stage.py` + `services/inventory.py` 추출.** 여기가 이번 작업의 고비 — 로직을 라우트에서 서비스로 실제로 끌어내림 | **높음** | 스캔 진행/UNDO, 재고 QR 스캔 실기 테스트 |
| **5** | `routers/` 분리. 라우트를 `APIRouter`로 옮기고 도메인별 파일로 배치 | 중간 | `/openapi.json` diff |
| **6** | `main.py` 조립. `services/scanner.py`를 서비스 참조로 전환하고 `lifespan`으로 교체. app.py 삭제 | 중간 | 전체 스모크 |

### 4단계를 쪼개는 이유

`_move()`는 스캔 진행·UNDO·시리얼 스캐너 세 곳에서 쓰이는 시스템의 심장부입니다. 여기서 사고가 나면 공장 라인이 멈추므로, 이 단계만 따로 커밋하고 실기 검증 후 다음으로 넘어갑니다.

---

## 5. 검증 방법

**자동 — 엔드포인트 회귀 검사 (가장 중요)**

```bash
# 0단계에서 저장해둔 것과 비교
curl -s localhost:8000/openapi.json | python -m json.tool > openapi_after.json
diff openapi_before.json openapi_after.json
```

경로·메서드·요청 스키마가 하나라도 바뀌면 diff에 잡힙니다. 프론트엔드를 안 건드리므로 **diff가 비어 있어야 성공**입니다.

**수동 — 실기 스모크 (6단계 완료 후)**

1. 주문 입력 → 라벨 인쇄
2. 작업자 화면 스캔 진행 → UNDO
3. 공정 모니터 3종(裁断/ミシン/ハトメ) 스캔
4. ハトメ完了 시 송장 자동 출력
5. 재고 QR 발행 → 스캔 차감
6. 관리자 로그인 → 재고/발주/주문/DB뷰어 각 탭
7. CSV export 4종
8. 시리얼 스캐너 백그라운드 스레드 기동 로그 확인

---

## 6. 같이 정리할 것 (덤)

옮기는 김에 처리:

- `import code` 삭제 (미사용)
- 중간 import 3곳(610, 1615, 1834행)을 각 파일 상단으로 정리
- `@app.on_event("startup")` → `lifespan` 컨텍스트 매니저
- `_get_setting` / `_set_setting`이 재고·발주·설정 3곳에 흩어져 있는 것을 `db.py`로 통합

**손대지 않을 것** (범위를 지키기 위해):

- 프론트엔드 HTML — `label.html`(2734줄) / `label_gorilla.html`(2792줄) 중복, `PROC` 수동 동기화 문제는 다음 작업으로 분리
- DB 스키마·마이그레이션 스크립트
- `print_templates.py`

---

## 7. 롤백

각 단계가 독립 커밋이므로 문제 발생 시 `git reset --hard HEAD~1` 한 번으로 직전 정상 상태 복귀. 최악의 경우 `git checkout main` 으로 통째 원복.
