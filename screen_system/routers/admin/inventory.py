"""
관리자 재고 — 구 재고(fabric/accessory) + QR재고 v2(inv_item/inv_unit/inv_tx).
"""

import csv
import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from config import (
    INV_GROUPS,
)
from db import db
from security import require_admin, _check_pw_query
from schemas import (
    AdjustIn, ReorderIn, AccIn, InvIssueIn, InvAdjustIn,
    InvReorderIn, InvItemIn,
)
from print_templates import render_inventory_label
from services.printing import silent_print_html

router = APIRouter()


# ---- 在庫 ----------------------------------------------------------------
@router.get("/api/admin/inventory")
def admin_inventory(_=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT fabric_type, remain_rolls, capacity_rolls, reorder_point FROM fabric_inventory ORDER BY fabric_type")
        fabric = [{"kind": "fabric", "id": r["fabric_type"], "name": r["fabric_type"],
                   "remain": r["remain_rolls"], "cap": r["capacity_rolls"],
                   "reorder": r["reorder_point"], "unit": "ロール",
                   "low": r["remain_rolls"] <= r["reorder_point"]} for r in cur.fetchall()]
        cur.execute("SELECT id, name, remain, capacity, unit, reorder_point FROM accessories ORDER BY sort_order, id")
        acc = [{"kind": "accessory", "id": r["id"], "name": r["name"], "remain": r["remain"],
                "cap": r["capacity"], "reorder": r["reorder_point"], "unit": r["unit"],
                "low": r["remain"] <= r["reorder_point"]} for r in cur.fetchall()]
    return {"fabric": fabric, "accessories": acc}


@router.post("/api/admin/inventory/adjust")
def admin_inventory_adjust(body: AdjustIn, _=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        if body.kind == "fabric":
            cur.execute("UPDATE fabric_inventory SET remain_rolls = remain_rolls + %s, updated_at=now() "
                        "WHERE fabric_type=%s RETURNING remain_rolls", (body.delta, body.id))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "生地が見つかりません")
            bal = row["remain_rolls"]
            cur.execute("""INSERT INTO inventory_transactions (kind, fabric_type, delta, reason, balance_after, note, worker)
                           VALUES ('fabric',%s,%s,%s,%s,%s,%s)""",
                        (body.id, body.delta, body.reason, bal, body.note, body.worker))
        elif body.kind == "accessory":
            cur.execute("UPDATE accessories SET remain = remain + %s WHERE id=%s RETURNING remain",
                        (body.delta, int(body.id)))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "付属品が見つかりません")
            bal = row["remain"]
            cur.execute("""INSERT INTO inventory_transactions (kind, accessory_id, delta, reason, balance_after, note, worker)
                           VALUES ('accessory',%s,%s,%s,%s,%s,%s)""",
                        (int(body.id), body.delta, body.reason, bal, body.note, body.worker))
        else:
            raise HTTPException(400, "kind は fabric / accessory")
        conn.commit()
    return {"ok": True, "balance": bal}


@router.post("/api/admin/inventory/reorder")
def admin_inventory_reorder(body: ReorderIn, _=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        if body.kind == "fabric":
            cur.execute("UPDATE fabric_inventory SET reorder_point=%s WHERE fabric_type=%s", (body.reorder_point, body.id))
        else:
            cur.execute("UPDATE accessories SET reorder_point=%s WHERE id=%s", (body.reorder_point, int(body.id)))
        conn.commit()
    return {"ok": True}


def _inv_hist_rows(cur, kind="", reason="", date_from="", date_to="", limit=500):
    where, params = ["1=1"], []
    if kind:      where.append("t.kind=%s");   params.append(kind)
    if reason:    where.append("t.reason=%s"); params.append(reason)
    if date_from: where.append("t.created_at >= %s"); params.append(date_from)
    if date_to:   where.append("t.created_at < (%s::date + 1)"); params.append(date_to)
    cur.execute(f"""SELECT t.created_at, t.kind, t.delta, t.reason, t.balance_after, t.note, t.worker,
                           COALESCE(t.fabric_type::text, a.name) AS target
                    FROM inventory_transactions t LEFT JOIN accessories a ON a.id = t.accessory_id
                    WHERE {' AND '.join(where)} ORDER BY t.created_at DESC LIMIT %s""", params + [limit])
    return cur.fetchall()


@router.get("/api/admin/inventory/history")
def admin_inventory_history(kind: str = "", reason: str = "", date_from: str = "",
                            date_to: str = "", limit: int = 300, _=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        rows = _inv_hist_rows(cur, kind, reason, date_from, date_to, limit)
    return [{"t": r["created_at"].strftime("%Y-%m-%d %H:%M"), "target": r["target"], "kind": r["kind"],
             "delta": r["delta"], "reason": r["reason"], "balance": r["balance_after"],
             "note": r["note"], "worker": r["worker"]} for r in rows]


@router.get("/api/admin/inventory/history.csv")
def admin_inventory_history_csv(kind: str = "", reason: str = "", date_from: str = "",
                                date_to: str = "", pw: str = ""):
    _check_pw_query(pw)
    with db() as conn, conn.cursor() as cur:
        rows = _inv_hist_rows(cur, kind, reason, date_from, date_to, 100000)
    buf = io.StringIO(); w = csv.writer(buf)
    w.writerow(["日時", "対象", "種別", "区分", "増減", "残", "メモ", "担当"])
    rmap = {"in": "入庫", "out": "消尽", "adjust": "調整"}
    for r in rows:
        w.writerow([r["created_at"].strftime("%Y-%m-%d %H:%M"), r["target"], r["kind"],
                    rmap.get(r["reason"], r["reason"]), r["delta"], r["balance_after"], r["note"], r["worker"]])
    return Response(content="\ufeff" + buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="inventory_history.csv"'})


@router.post("/api/admin/accessories")
def admin_accessory_create(body: AccIn, _=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT COALESCE(max(sort_order),0)+1 AS s FROM accessories")
        so = cur.fetchone()["s"]
        cur.execute("""INSERT INTO accessories (name, remain, capacity, unit, reorder_point, sort_order)
                       VALUES (%s,0,%s,%s,%s,%s) RETURNING id""",
                    (body.name, body.capacity, body.unit, body.reorder_point, so))
        nid = cur.fetchone()["id"]; conn.commit()
    return {"ok": True, "id": nid}


@router.delete("/api/admin/accessories/{acc_id}")
def admin_accessory_delete(acc_id: int, _=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM accessories WHERE id=%s", (acc_id,))
        n = cur.rowcount; conn.commit()
    if n == 0:
        raise HTTPException(404, "付属品が見つかりません")
    return {"ok": True}


# ---- 管理: 品目一覧 / QR発行(入庫) / 調整 / 発注点 / 履歴 / 品目CRUD ----
@router.get("/api/admin/inv")
def admin_inv_list(_=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM inv_item WHERE active ORDER BY group_no, sort_order, code")
        rows = cur.fetchall()
    items = [{"code": r["code"], "category": r["category"], "group_no": r["group_no"],
              "group_name": r["group_name"], "name": r["name"], "fabric_type": r["fabric_type"],
              "flame": r["flame"], "unit": r["unit"], "remain": r["remain"], "cap": r["capacity"],
              "reorder": r["reorder_point"], "low": r["remain"] <= r["reorder_point"]} for r in rows]
    return {"groups": [{"no": g[0], "name": g[1]} for g in INV_GROUPS], "items": items}


@router.post("/api/admin/inv/{code}/issue")
def admin_inv_issue(code: str, body: InvIssueIn, _=Depends(require_admin)):
    """QR発行 = 入庫(+count)。シリアル(コード-連番)を採番して返す。"""
    n = max(1, min(200, int(body.count or 1)))
    serials = []
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT code, name, unit FROM inv_item WHERE code=%s AND active FOR UPDATE", (code,))
        it = cur.fetchone()
        if not it:
            raise HTTPException(404, f"品目が見つかりません: {code}")
        for _i in range(n):
            cur.execute("""WITH nx AS (SELECT COALESCE(MAX(seq),0)+1 AS s FROM inv_unit WHERE code=%s)
                           INSERT INTO inv_unit (code, seq, serial)
                           SELECT %s, nx.s, %s || LPAD(nx.s::text, 5, '0') FROM nx
                           RETURNING serial""", (code, code, code + "-"))
            serials.append(cur.fetchone()["serial"])
        cur.execute("UPDATE inv_item SET remain = remain + %s WHERE code=%s RETURNING remain", (n, code))
        bal = cur.fetchone()["remain"]
        for s in serials:
            cur.execute("INSERT INTO inv_tx (code, serial, delta, reason, balance_after, worker) "
                        "VALUES (%s,%s,1,'issue',%s,%s)", (code, s, bal, body.worker))
        conn.commit()
    for s in serials:
        html_content = render_inventory_label(code=code, name=it["name"], serial=s, unit=it["unit"])
        silent_print_html(html_content, "inventory_printer")
    return {"ok": True, "code": code, "name": it["name"], "unit": it["unit"],
            "serials": serials, "balance": bal}


@router.post("/api/admin/inv/{code}/adjust")
def admin_inv_adjust(code: str, body: InvAdjustIn, _=Depends(require_admin)):
    """手動補正(棚卸差異など)。シリアルは発行しない。"""
    if not body.delta:
        return {"ok": True}
    with db() as conn, conn.cursor() as cur:
        cur.execute("UPDATE inv_item SET remain = GREATEST(0, remain + %s) WHERE code=%s AND active RETURNING remain",
                    (body.delta, code))
        r = cur.fetchone()
        if not r:
            raise HTTPException(404, "品目が見つかりません")
        cur.execute("INSERT INTO inv_tx (code, delta, reason, balance_after, note, worker) "
                    "VALUES (%s,%s,'adjust',%s,%s,%s)", (code, body.delta, r["remain"], body.note, body.worker))
        conn.commit()
    return {"ok": True, "balance": r["remain"]}


@router.post("/api/admin/inv/{code}/reorder")
def admin_inv_reorder(code: str, body: InvReorderIn, _=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        cur.execute("UPDATE inv_item SET reorder_point=%s WHERE code=%s", (max(0, body.reorder_point), code))
        conn.commit()
    return {"ok": True}


@router.get("/api/admin/inv/history")
def admin_inv_history(limit: int = 300, _=Depends(require_admin)):
    with db() as conn, conn.cursor() as cur:
        cur.execute("""SELECT t.id, t.created_at, t.code, i.name, t.serial, t.delta, t.reason,
                              t.balance_after, t.note, t.worker
                       FROM inv_tx t LEFT JOIN inv_item i ON i.code = t.code
                       ORDER BY t.created_at DESC LIMIT %s""", (limit,))
        rows = cur.fetchall()
    RJA = {"issue": "発行(入庫)", "consume": "消尽", "adjust": "調整"}
    return [{"id": r["id"],
             "t": r["created_at"].strftime("%Y-%m-%d %H:%M"), "code": r["code"], "name": r["name"],
             "serial": r["serial"], "delta": r["delta"], "reason": RJA.get(r["reason"], r["reason"]),
             "balance": r["balance_after"], "note": r["note"], "worker": r["worker"]} for r in rows]


@router.delete("/api/admin/inv/history/{tx_id}")
def admin_inv_history_delete(tx_id: int, _=Depends(require_admin)):
    """在庫履歴を1件削除する。

    注意: 履歴を消しても inv_item.remain(残数)は変わらない。
    残数を直したい場合は在庫画面の「調整」を使うこと。
    """
    with db() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM inv_tx WHERE id=%s", (tx_id,))
        deleted = cur.rowcount
        conn.commit()
    if not deleted:
        raise HTTPException(404, "該当する履歴がありません")
    return {"ok": True, "deleted": deleted}


@router.post("/api/admin/inv/item")
def admin_inv_item_create(body: InvItemIn, _=Depends(require_admin)):
    unit = body.unit or {"fabric": "ロール", "supply": "本"}.get(body.category, "箱")
    so = int(body.code) if body.code.isdigit() else 999
    with db() as conn, conn.cursor() as cur:
        try:
            cur.execute("""INSERT INTO inv_item (code, category, group_no, group_name, name,
                             fabric_type, flame, unit, sort_order)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (body.code, body.category, body.group_no, body.group_name, body.name,
                         body.fabric_type, body.flame, unit, so))
            conn.commit()
        except Exception as e:
            raise HTTPException(400, f"追加エラー: {str(e).splitlines()[0]}")
    return {"ok": True}


@router.delete("/api/admin/inv/item/{code}")
def admin_inv_item_delete(code: str, _=Depends(require_admin)):
    """在庫履歴を保つため論理削除(active=false)。"""
    with db() as conn, conn.cursor() as cur:
        cur.execute("UPDATE inv_item SET active=FALSE WHERE code=%s", (code,))
        n = cur.rowcount
        conn.commit()
    if not n:
        raise HTTPException(404, "品目が見つかりません")
    return {"ok": True}
