"""
HTML 화면 서빙 — frontend/*.html 을 그대로 돌려주는 라우트만 모았다.
"""

import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, RedirectResponse

from config import (
    FRONTEND_DIR, MON_PROC,
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
    base = os.path.dirname(os.path.abspath(__file__))
    return FileResponse(os.path.join(base, "detail_sizeGuide_v26.html"))


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
def page_label_multi():
    # 本番ラベル = label_gorilla.html(ゴリラインパクトデザイン)。
    # 旧 label.html は使わずバックアップとして残置。
    return FileResponse(os.path.join(FRONTEND_DIR, "label_gorilla.html"))


@router.get("/label/{barcode}")
def page_label(barcode: str):
    return FileResponse(os.path.join(FRONTEND_DIR, "label_gorilla.html"))


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
