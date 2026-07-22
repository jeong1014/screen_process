"""
호환용 shim — 기존 실행 명령(`uvicorn app:app`)을 그대로 쓸 수 있게 남겨둔다.

실제 앱은 main.py 에 있다. 새 스크립트는 `uvicorn main:app` 을 쓸 것.
"""

from main import app  # noqa: F401
