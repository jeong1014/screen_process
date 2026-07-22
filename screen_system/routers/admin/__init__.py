"""
관리자 라우터 묶음.

여기서 하나의 APIRouter 로 합쳐 main.py 는 admin_router 하나만 include 하면 된다.
등록 순서는 원본 app.py 와 동일하게 유지한다 (경로 매칭 순서 보존).
"""

from fastapi import APIRouter

from routers.admin import (
    auth, inventory, purchase, orders, ops, reports, settings, dbviewer,
)

admin_router = APIRouter()

for _m in (auth, inventory, purchase, orders, ops, reports, settings, dbviewer):
    admin_router.include_router(_m.router)
