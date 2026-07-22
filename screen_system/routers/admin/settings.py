"""
관리자 설정 — settings 테이블 조회/저장.
"""

from fastapi import APIRouter, Depends

from db import db
from schemas import SettingsIn
from security import require_admin

router = APIRouter()


@router.get("/api/admin/settings")
def admin_settings_get(_=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT key, value FROM settings ORDER BY key")
        rows = {r["key"]: r["value"] for r in cur.fetchall()}
    rows.pop("admin_password", None)   # パスワードは返さない
    return rows


@router.post("/api/admin/settings")
def admin_settings_set(body: SettingsIn, _=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        for k, v in body.values.items():
            cur.execute("""INSERT INTO settings (key, value, updated_at) VALUES (%s,%s,now())
                           ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=now()""", (k, str(v)))
        conn.commit()
    return {"ok": True}
