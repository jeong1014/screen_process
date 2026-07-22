"""
관리자 로그인.
"""


from fastapi import APIRouter, HTTPException

from db import db
from security import _admin_password
from schemas import (
    LoginIn,
)

router = APIRouter()


@router.post("/api/admin/login")
def admin_login(body: LoginIn):
    with db() as conn, conn.cursor() as cur:
        ok = body.password == _admin_password(cur)
    if not ok:
        raise HTTPException(401, "パスワードが違います")
    return {"ok": True}
