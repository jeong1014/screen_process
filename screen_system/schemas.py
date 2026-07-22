"""
リクエストボディの Pydantic モデル一覧。

app.py 内に散らばっていたモデルをここへ集約した。
フィールド名・既定値・エイリアスは一切変更していない(API契約を維持するため)。
"""

from typing import Optional, List

from pydantic import BaseModel, Field


# =============================================================================
# 注文入力
# =============================================================================
class ItemIn(BaseModel):
    product_type: str = "single"
    fabric_type: str = "LN"
    width_mm: int
    height_mm: int
    quantity: int = 1
    # 2枚セット(two_sheet_set)用: 裏面の生地/サイズ(表面と別に指定可能)
    back_fabric_type: Optional[str] = None
    back_width_mm: Optional[int] = None
    back_height_mm: Optional[int] = None
    process_top: str = "none"
    process_top_mm: Optional[int] = None
    process_bottom: str = "none"
    process_bottom_mm: Optional[int] = None
    process_left: str = "none"
    process_left_mm: Optional[int] = None
    process_right: str = "none"
    process_right_mm: Optional[int] = None
    # 販売サイトのオプション体系に合わせた追加項目
    # ベルクロ・ハトメ・スカートは同じ辺に同時に付くため、process_* とは別に持つ。
    velcro_sides: Optional[int] = None      # ベルクロ面数: None=なし / 3=上左右 / 4=四辺
    has_skirt: bool = False                 # スカート有無(下辺のみ)
    velcro_type: str = "male"               # male / female (全製品に必ず付くため既定値あり)
    skirt_attachment: Optional[str] = None  # sew / velcro
    skirt_no_seam: bool = False
    eyelet_method: Optional[str] = None     # A / B / C
    fire_cert_no: Optional[str] = None


class OrderIn(BaseModel):
    channel: str
    customer_name: str
    postal_code: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    payment_status: str = "paid"
    mall_order_no: Optional[str] = None
    ordered_at: Optional[str] = None
    items: List[ItemIn] = Field(default_factory=list)


# =============================================================================
# スキャン
# =============================================================================
class ScanIn(BaseModel):
    order_no: str            # = barcode


class MonScan(BaseModel):
    barcode: str


class InvScanIn(BaseModel):
    code: str                      # = スキャンされたシリアル(例 11-00001)
    worker: Optional[str] = None


# =============================================================================
# 管理者: 認証
# =============================================================================
class LoginIn(BaseModel):
    password: str


# =============================================================================
# 管理者: 在庫(旧)
# =============================================================================
class AdjustIn(BaseModel):
    kind: str                      # fabric / accessory
    id: str                        # fabric_type(LN..) or accessory_id
    delta: int                     # +入庫 / −消尽
    reason: str = "adjust"         # in / out / adjust
    note: Optional[str] = None
    worker: Optional[str] = None


class ReorderIn(BaseModel):
    kind: str
    id: str
    reorder_point: int


class AccIn(BaseModel):
    name: str
    unit: str = "箱"          # 付属品の単位は全て「箱」に統一
    capacity: int = 10
    reorder_point: int = 5


# =============================================================================
# 管理者: QR在庫 v2
# =============================================================================
class InvIssueIn(BaseModel):
    count: int = 1
    worker: Optional[str] = None


class InvAdjustIn(BaseModel):
    delta: int
    note: Optional[str] = None
    worker: Optional[str] = None


class InvReorderIn(BaseModel):
    reorder_point: int


class InvItemIn(BaseModel):
    code: str
    category: str = "accessory"
    group_no: int = 6
    group_name: str = "その他"
    name: str
    unit: Optional[str] = None
    fabric_type: Optional[str] = None
    flame: Optional[bool] = None


# =============================================================================
# 管理者: 発注(仕入れ)
# =============================================================================
class PurchaseReqIn(BaseModel):
    code: str
    qty: int
    requested_by: Optional[str] = None
    note: Optional[str] = None


class PurchaseOrderIn(BaseModel):
    eta: str                       # 'YYYY-MM-DD'
    order_note: Optional[str] = None


class PurchaseSettingsIn(BaseModel):
    to: str = ""
    host: str = ""
    port: str = "587"
    user: str = ""
    password: Optional[str] = None   # 空文字=変更なし
    from_: str = Field("", alias="from")
    tls: str = "starttls"

    class Config:
        populate_by_name = True


# =============================================================================
# 管理者: 注文 / 出荷
# =============================================================================
class OrderPatch(BaseModel):
    order_no: Optional[str] = None          # 新しい注文番号(変更時)
    customer_name: Optional[str] = None
    postal_code: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    payment_status: Optional[str] = None


class StageFix(BaseModel):
    stage: int


class ShipIn(BaseModel):
    order_no: str
    tracking_no: Optional[str] = None
    shipping_status: Optional[str] = None
    bizlogi_status: Optional[str] = None
    package_count: Optional[int] = None


# =============================================================================
# 管理者: 設定 / DBビューア
# =============================================================================
class SettingsIn(BaseModel):
    values: dict


class DbEdit(BaseModel):
    pk_value: str
    changes: dict
