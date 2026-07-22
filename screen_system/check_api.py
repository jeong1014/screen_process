"""
API 계약 스냅샷 도구 — 리팩터링 전후 엔드포인트가 바뀌지 않았는지 검사한다.

DB나 프린터 없이 앱 모듈만 import 해서 OpenAPI 스키마를 뽑는다.
(weasyprint / serial 은 스키마 생성에 불필요하므로 없으면 더미로 대체)

사용법:
    # 리팩터링 전 기준 저장
    python check_api.py app > openapi_before.json

    # 리팩터링 후 비교
    python check_api.py main > openapi_after.json
    diff openapi_before.json openapi_after.json     # 아무것도 안 나와야 성공
"""
import importlib
import json
import sys
import types


def _stub(name: str, attrs=()):
    """import 만 되면 되는 무거운 모듈을 더미로 끼워넣는다."""
    try:
        importlib.import_module(name)
        return
    except Exception:
        pass
    mod = types.ModuleType(name)
    for attr in attrs:
        setattr(mod, attr, type(attr, (), {"__init__": lambda self, *a, **k: None}))
    sys.modules[name] = mod


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "app"

    _stub("weasyprint", ("HTML", "CSS"))
    _stub("serial", ("Serial", "SerialException"))

    mod = importlib.import_module(target)
    schema = mod.app.openapi()

    # 정렬해서 덤프 — 라우트 등록 순서가 바뀌어도 diff 가 나지 않게 한다
    print(json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
