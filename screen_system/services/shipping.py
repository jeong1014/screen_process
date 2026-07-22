"""
送り状(送장) 자동 출력.

ハトメ完了(최종 공정) 시점에 호출된다. 호출 지점이 두 곳(작업자 스캔 _move,
시리얼 스캐너 모니터 스캔)이라 중복돼 있던 코드를 여기로 합쳤다.

주의: 두 호출 지점은 주문 정보를 찾는 방식이 서로 다르다.
  - move_stage      : orders.order_no = 스캔한 바코드 로 조회
  - 시리얼 스캐너    : order_items.order_id → orders.id 로 조회
리팩터링 시 동작을 바꾸지 않기 위해 조회 방식은 각각 그대로 두고,
공통 부분(명세 조회 → HTML 생성 → 출력)만 이 모듈로 뽑았다.
"""

from config import MAX_STAGE
from print_templates import render_shipping_slip
from services.printing import silent_print_html


def fetch_order_by_no(cur, order_no):
    cur.execute("SELECT * FROM orders WHERE order_no=%s", (order_no,))
    return cur.fetchone() or {}


def fetch_order_by_id(cur, order_id):
    cur.execute("SELECT * FROM orders WHERE id=%s", (order_id,))
    return cur.fetchone() or {}


def mark_order_shipped(cur, order_id):
    """注文の全明細が最終工程(stage 6 = ハトメ完了)まで進んだら出荷済みとして記録する。

    まだ終わっていない明細が1つでもあれば何もしない。
    既に記録済みの注文に対して何度呼んでも二重登録にならない(ON CONFLICT)。
    戻り値: 出荷レコードを作った/更新したら True。
    """
    cur.execute(
        """SELECT count(*) FILTER (WHERE current_stage < %s) AS remaining,
                  count(*) AS total
             FROM order_items WHERE order_id = %s""",
        (MAX_STAGE, order_id),
    )
    r = cur.fetchone()
    if not r or r["total"] == 0 or r["remaining"] > 0:
        return False

    cur.execute("SELECT order_no FROM orders WHERE id = %s", (order_id,))
    o = cur.fetchone()
    if not o:
        return False

    cur.execute(
        """INSERT INTO shipments (order_id, shipment_no, package_no, shipping_status, shipped_at)
           VALUES (%s, %s, 1, 'completed', now())
           ON CONFLICT (order_id, package_no)
           DO UPDATE SET shipping_status = 'completed',
                         shipped_at      = COALESCE(shipments.shipped_at, now()),
                         updated_at      = now()""",
        (order_id, f"{o['order_no']}-01"),
    )
    cur.execute(
        "UPDATE orders SET order_status = 'shipped' WHERE id = %s AND order_status <> 'cancelled'",
        (order_id,),
    )
    print(f"🚚 注文 {o['order_no']} 全明細ハトメ完了 → 出荷済みとして記録")
    return True


def auto_print_shipping_slip(cur, order_no, order_id, order_info):
    """주문에 속한 전체 제품 목록을 붙여 송장 HTML을 만들고 송장 프린터로 보낸다."""
    cur.execute(
        "SELECT barcode, fabric_type as fabric, width_mm, height_mm "
        "FROM order_items WHERE order_id=%s",
        (order_id,),
    )
    items_db = cur.fetchall()
    items_list = [
        {"barcode": i["barcode"], "fabric": i["fabric"],
         "size": f"W{i['width_mm']}xH{i['height_mm']}"}
        for i in items_db
    ]
    html_content = render_shipping_slip(
        order_no=order_no, order_info=order_info, items=items_list
    )
    silent_print_html(html_content, "invoice_printer")
