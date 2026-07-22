"""
HTML 화면 서빙 — frontend/*.html 을 그대로 돌려주는 라우트만 모았다.
"""

import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, RedirectResponse

from services.labels import resolve_path as resolve_label_path
from config import (
    BASE_DIR, FRONTEND_DIR, MON_PROC,
)

router = APIRouter()


# =============================================================================
# ページ
# =============================================================================
@router.get("/")
def root():
    return RedirectResponse("/input")


@router.get("/input")
def page_input():
    return FileResponse(os.path.join(FRONTEND_DIR, "input.html"))


@router.get("/worker")
def page_worker():
    return FileResponse(os.path.join(FRONTEND_DIR, "worker.html"))


@router.get("/dashboard")
def page_dashboard():
    return FileResponse(os.path.join(FRONTEND_DIR, "dashboard.html"))


@router.get("/shop")
def page_shop():
    # 販売サイトの商品ページ(detail_sizeGuide_v26.html)を同一オリジンで配信。
    # ここから「注文を確定」すると POST /api/orders でDBに登録される。
    #
    # 注意: このファイルは screen_system/ 直下にある。__file__ を使うと
    #       routers/ を指してしまうので、必ず config.BASE_DIR を使うこと。
    path = os.path.join(BASE_DIR, "detail_sizeGuide_v26.html")
    if not os.path.exists(path):
        raise HTTPException(404, f"商品ページが見つかりません: {path}")
    return FileResponse(path)


@router.get("/shipping-slip/{barcode}")
def page_shipping_slip(barcode: str):
    # ハトメ完了時などに開く送_り状(印刷)ページ。barcode から注文を引いて表示する。
    return FileResponse(os.path.join(FRONTEND_DIR, "shipping_slip.html"))


# =============================================================================
# ラベル自動化: /label/{barcode} でラベルを開くと DB から自動で埋まる
#   複数枚まとめて出す時は /label?serials=バーコード1,バーコード2&print=1 も使える
#   (2枚セットの表面/裏面を同時に印刷する時など。在庫QRラベルと同じ方式)
# =============================================================================
@router.get("/label")
def page_label_multi(tpl: str = ""):
    """ラベルを開く。?tpl=standard / small で版を指定できる。
       指定が無ければ管理画面で選んだ既定の版を使う。
       旧 label.html は使わずバックアップとして残置。"""
    return FileResponse(resolve_label_path(tpl))


@router.get("/label/{barcode}")
def page_label(barcode: str, tpl: str = ""):
    return FileResponse(resolve_label_path(tpl))


@router.get("/admin")
def page_admin():
    return FileResponse(os.path.join(FRONTEND_DIR, "admin.html"))


@router.get("/invscan")
def page_invscan():
    """QRシリアルを読み取って在庫を消尽する現場用スキャン画面。"""
    return FileResponse(os.path.join(FRONTEND_DIR, "invscan.html"))


@router.get("/invlabel/{serial}")
def page_invlabel(serial: str):
    """29×90mm QR在庫ラベル(QR=シリアル + 品名)。?print=1 で自動印刷。"""
    return FileResponse(os.path.join(FRONTEND_DIR, "invlabel.html"))


@router.get("/monitor/{proc}")
def page_monitor(proc: str):
    if proc not in MON_PROC:
        raise HTTPException(404, "不明な工程 (cutting/sewing/eyelet)")
    return FileResponse(os.path.join(FRONTEND_DIR, "monitor.html"))
