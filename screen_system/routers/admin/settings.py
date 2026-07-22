"""
관리자 설정 — settings 테이블 조회/저장.
"""

from fastapi import APIRouter, Depends

from config import LABEL_TEMPLATE_KEY
from db import db, _get_setting
from schemas import SettingsIn
from security import require_admin
from services.labels import listing as label_template_listing, resolve as resolve_label

router = APIRouter()


@router.get("/api/admin/label-templates")
def admin_label_templates(_=Depends(require_admin)):
    """ラベルの版の一覧と、現在選ばれている既定の版。

    HTML ファイルがまだ無い版は ready=false で返る(選択させない)。
    同僚が小型ラベルを frontend/ に置いた時点で自動的に ready=true になる。
    """
    with db() as conn, conn.cursor() as cur:
        saved = _get_setting(cur, LABEL_TEMPLATE_KEY, "")
    return {"templates": label_template_listing(),
            "saved": saved,          # settings に入っている生の値
            "current": resolve_label()}   # 実際に使われる版


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
