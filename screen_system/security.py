"""
관리자 인증 — settings 테이블의 admin_password 기반 간이 인증.

- require_admin : X-Admin-Pass 헤더 검사 (FastAPI Depends 용)
- _check_pw_query : 다운로드 링크용 ?pw= 쿼리 검사
"""

from fastapi import Header, HTTPException

from db import db, _get_setting


def _admin_password(cur):
    return _get_setting(cur, "admin_password", "1234")


def require_admin(x_admin_pass: str = Header(default="")):
    with db() as conn, conn.cursor() as cur:
        if x_admin_pass != _admin_password(cur):
            raise HTTPException(401, "認証が必要です(パスワード)")
    return True


def _check_pw_query(pw: str):
    """ダウンロードリンク用: クエリ ?pw= で認証。"""
    with db() as conn, conn.cursor() as cur:
        if pw != _admin_password(cur):
            raise HTTPException(401, "認証が必要です(パスワード)")
