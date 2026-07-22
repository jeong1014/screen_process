"""
라벨 版(템플릿) 선택.

우선순위:  URL 의 ?tpl=  →  settings.label_template(관리자 기본값)  →  DEFAULT_LABEL_TEMPLATE

HTML 파일이 실제로 존재하지 않는 版은 절대 선택되지 않는다.
동료가 소형 라벨을 만들기 전에 잘못 골라도 인쇄가 깨지지 않도록 하기 위함.
"""

import os

from config import (
    FRONTEND_DIR, LABEL_TEMPLATES, DEFAULT_LABEL_TEMPLATE, LABEL_TEMPLATE_KEY,
)
from db import db, _get_setting


def template_path(key: str):
    """版のHTMLファイルの絶対パス。定義が無ければ None。"""
    meta = LABEL_TEMPLATES.get(key)
    return os.path.join(FRONTEND_DIR, meta["file"]) if meta else None


def is_ready(key: str) -> bool:
    """定義があり、かつ HTML ファイルが実在するか。"""
    p = template_path(key)
    return bool(p) and os.path.exists(p)


def resolve(tpl=None) -> str:
    """使用する版のキーを決める。存在しない版は既定に落とす。"""
    if tpl and is_ready(tpl):
        return tpl
    try:
        with db() as conn, conn.cursor() as cur:
            saved = _get_setting(cur, LABEL_TEMPLATE_KEY, DEFAULT_LABEL_TEMPLATE)
    except Exception:
        saved = DEFAULT_LABEL_TEMPLATE
    return saved if is_ready(saved) else DEFAULT_LABEL_TEMPLATE


def resolve_path(tpl=None) -> str:
    return template_path(resolve(tpl))


def printer_key(tpl=None) -> str:
    """その版を印刷するプリンタ設定キー。未設定なら order_printer。"""
    meta = LABEL_TEMPLATES.get(resolve(tpl), {})
    return meta.get("printer") or "order_printer"


def listing():
    """管理画面用: 版の一覧(未作成のものも「未作成」として見せる)。"""
    return [{"key": k, "name": v["name"], "file": v["file"],
             "page": v.get("page", ""), "printer": v.get("printer", "order_printer"),
             "ready": is_ready(k)}
            for k, v in LABEL_TEMPLATES.items()]
