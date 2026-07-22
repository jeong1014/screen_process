"""
DB 접속과 settings 테이블 접근.

settings 읽기/쓰기 헬퍼(_get_setting/_set_setting)가 재고·발주·설정 세 곳에
흩어져 있던 것을 여기로 통합했다.
"""

import psycopg
from psycopg.rows import dict_row

from config import DATABASE_URL


def db():
    """psycopg 커넥션. 호출부는 `with db() as conn, conn.cursor() as cur:` 형태로 사용."""
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def _get_setting(cur, key, default=None):
    cur.execute("SELECT value FROM settings WHERE key=%s", (key,))
    r = cur.fetchone()
    return r["value"] if r else default


def _set_setting(cur, key, value):
    cur.execute("""INSERT INTO settings (key, value, updated_at) VALUES (%s,%s,now())
                   ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=now()""",
                (key, value))


# 이전 이름과의 호환용 별칭 (외부에서 언더스코어 없는 이름으로 쓰고 싶을 때)
get_setting = _get_setting
set_setting = _set_setting
