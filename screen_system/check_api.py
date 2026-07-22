"""
API 계약 스냅샷 / 회귀 검사 도구.

DB나 프린터 없이 앱 모듈만 import 해서 검사한다.
(weasyprint / serial 은 검사에 불필요하므로 없으면 더미로 대체)

사용법:
    python check_api.py dump main > openapi_after.json   # OpenAPI 스키마 덤프
    diff openapi_before.json openapi_after.json          # 아무것도 안 나와야 성공

    python check_api.py verify main                      # 라우트 목록/순서 검사
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


def _load(target):
    _stub("weasyprint", ("HTML", "CSS"))
    _stub("serial", ("Serial", "SerialException"))
    return importlib.import_module(target)


def _flat(routes, out=None):
    """include_router 로 중첩된 라우트를 등록 순서대로 펼친다."""
    out = [] if out is None else out
    for r in routes:
        if hasattr(r, "methods") and getattr(r, "path", None):
            out.append((r.path, set(r.methods) - {"HEAD"}))
        elif type(r).__name__ == "_IncludedRouter":
            _flat(r.original_router.routes, out)
        elif hasattr(r, "routes"):
            _flat(r.routes, out)
    return out


def dump(target):
    schema = _load(target).app.openapi()
    # 정렬해서 덤프 — 라우트 등록 순서가 바뀌어도 diff 가 나지 않게 한다
    print(json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True))


def verify(target, baseline="route_baseline.txt"):
    routes = [r for r in _flat(_load(target).app.routes)
              if not r[0].startswith(("/openapi", "/docs", "/redoc"))]

    ok = True

    # 1) 메서드+경로 집합이 기준과 같은가
    now = sorted((m, p) for p, ms in routes for m in ms)
    with open(baseline, encoding="utf-8") as f:
        old = sorted(tuple(l.split()) for l in f.read().strip().split("\n"))
    if now == old:
        print(f"✅ 라우트 {len(now)}개 — 기준과 일치")
    else:
        ok = False
        print(f"❌ 라우트 불일치\n   누락: {set(old) - set(now)}\n   추가: {set(now) - set(old)}")

    # 2) 동적 세그먼트가 뒤에 오는 리터럴 경로를 가리지 않는가
    #    예) /api/admin/db/{table} 이 /api/admin/db/tables 보다 먼저 등록되면 안 된다
    bad = []
    for i, (p, m) in enumerate(routes):
        if "{" not in p:
            continue
        pre = p.split("{")[0]
        for q, n in routes[i + 1:]:
            if "{" not in q and q.startswith(pre) and q.count("/") == p.count("/") and (m & n):
                bad.append(f"{p} 가 {q} 를 가림")
    if bad:
        ok = False
        print("❌ 경로 가림:", *bad, sep="\n   ")
    else:
        print("✅ 경로 가림 없음")

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "dump"
    tgt = sys.argv[2] if len(sys.argv) > 2 else "main"
    if cmd == "verify":
        verify(tgt)
    elif cmd == "dump":
        dump(tgt)
    else:                      # 이전 사용법 호환: check_api.py <module>
        dump(cmd)
