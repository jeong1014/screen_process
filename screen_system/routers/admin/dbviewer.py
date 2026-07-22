"""
관리자 DB 뷰어 — 임의 테이블 열람 + 셀 편집.
"""


from fastapi import APIRouter, Depends, HTTPException
from psycopg import sql as _sql

from config import (
    DB_TABLES,
)
from db import db
from security import require_admin
from schemas import (
    DbEdit,
)

router = APIRouter()


def _col_types(cur, table):
    cur.execute("""SELECT column_name, udt_name FROM information_schema.columns
                   WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position""", (table,))
    return {r["column_name"]: r["udt_name"] for r in cur.fetchall()}


@router.get("/api/admin/db/tables")
def db_tables(_=Depends(require_admin)):
    out = []
    with db() as conn, conn.cursor() as cur:
        for t, pk in DB_TABLES.items():
            cur.execute(_sql.SQL("SELECT count(*) AS c FROM {}").format(_sql.Identifier(t)))
            out.append({"table": t, "pk": pk, "count": cur.fetchone()["c"]})
    return out


@router.get("/api/admin/db/{table}")
def db_view(table: str, limit: int = 300, _=Depends(require_admin)):
    if table not in DB_TABLES:
        raise HTTPException(404, "不明なテーブル")
    with db() as conn, conn.cursor() as cur:
        columns = list(_col_types(cur, table).keys())
        cur.execute(_sql.SQL("SELECT * FROM {} ORDER BY 1 DESC LIMIT %s").format(_sql.Identifier(table)), (limit,))
        rows = cur.fetchall()
    return {"table": table, "pk": DB_TABLES[table], "columns": columns, "rows": rows}


@router.patch("/api/admin/db/{table}")
def db_edit(table: str, body: DbEdit, _=Depends(require_admin)):
    if table not in DB_TABLES:
        raise HTTPException(404, "不明なテーブル")
    pk = DB_TABLES[table]
    with db() as conn, conn.cursor() as cur:
        ct = _col_types(cur, table)
        sets, vals = [], []
        for col, v in body.changes.items():
            if col not in ct or col == pk:
                continue
            if v is None or v == "":
                sets.append(_sql.SQL("{}=NULL").format(_sql.Identifier(col)))
            else:
                sets.append(_sql.SQL("{}=%s::{}").format(_sql.Identifier(col), _sql.SQL(ct[col])))
                vals.append(v)
        if not sets:
            return {"ok": True, "updated": 0}
        q = _sql.SQL("UPDATE {} SET {} WHERE {}=%s::{}").format(
            _sql.Identifier(table), _sql.SQL(", ").join(sets),
            _sql.Identifier(pk), _sql.SQL(ct[pk]))
        try:
            cur.execute(q, vals + [body.pk_value])
            n = cur.rowcount
            conn.commit()
        except Exception as e:
            raise HTTPException(400, f"更新エラー: {str(e).splitlines()[0]}")
    return {"ok": True, "updated": n}
