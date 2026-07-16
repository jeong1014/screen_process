import base64
import os
from io import BytesIO
import qrcode
from barcode import Code128
from barcode.writer import ImageWriter

# ---------------------------------------------------------
# 이미지 렌더링 헬퍼 함수
# ---------------------------------------------------------
def get_base64_qr(data: str) -> str:
    """텍스트를 QR코드 이미지(Base64)로 변환"""
    if not data: return ""
    qr = qrcode.QRCode(box_size=4, border=0)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

def get_base64_barcode(data: str) -> str:
    """텍스트를 Code128 바코드 이미지(Base64)로 변환"""
    if not data: return ""
    rv = BytesIO()
    Code128(data, writer=ImageWriter()).write(rv, options={"write_text": False, "module_height": 12, "quiet_zone": 1})
    return base64.b64encode(rv.getvalue()).decode("utf-8")

def get_local_image_b64(filename: str) -> str:
    """고릴라 로고 등 로컬 이미지를 Base64로 변환하여 HTML에 삽입"""
    filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    if os.path.exists(filepath):
        with open(filepath, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    return ""

# ---------------------------------------------------------
# 1. 재고 QR 라벨 템플릿 (90mm x 29mm)
# ---------------------------------------------------------
def render_inventory_label(code, name, serial, unit):
    qr_b64 = get_base64_qr(serial)
    return f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
    <meta charset="UTF-8">
    <style>
        @page {{ size: 90mm 29mm; margin: 0; }}
        body {{ margin: 0; padding: 2mm 2.5mm; background: #fff; font-family: "Malgun Gothic", sans-serif; }}
        .label {{ display: flex; align-items: center; gap: 2.5mm; width: 100%; height: 25mm; }}
        .qr {{ flex: 0 0 25mm; height: 25mm; }}
        .qr img {{ width: 100%; height: 100%; }}
        .info {{ flex: 1; display: flex; flex-direction: column; justify-content: center; overflow: hidden; }}
        .sub {{ font-size: 11px; color: #333; margin-bottom: 2px; }}
        .title {{ font-size: 15px; font-weight: bold; margin-bottom: 4px; white-space: nowrap; overflow: hidden; }}
        .serial {{ font-size: 18px; font-weight: bold; letter-spacing: 1px; }}
    </style>
    </head>
    <body>
        <div class="label">
            <div class="qr"><img src="data:image/png;base64,{qr_b64}"></div>
            <div class="info">
                <div class="sub">품목코드: {code} ({unit})</div>
                <div class="title">{name}</div>
                <div class="serial">{serial}</div>
            </div>
        </div>
    </body>
    </html>
    """

# ---------------------------------------------------------
# 2. 주문/공정 라벨 템플릿 (110mm x 290mm)
# ---------------------------------------------------------
def render_order_label(item_data: dict):
    # item_data는 app.py의 worker_payload 형식의 데이터를 받습니다.
    barcode_val = item_data.get('barcode', item_data.get('order_no', ''))
    bc_b64 = get_base64_barcode(barcode_val)
    qr_b64 = get_base64_qr("https://cdigolf.base.ec/")
    
    return f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
    <style>
        @page {{ size: 110mm 290mm; margin: 0; }}
        body {{ margin: 0; padding: 10mm; font-family: "Malgun Gothic", sans-serif; background: #fff; }}
        .header {{ text-align: center; font-size: 24px; font-weight: bold; margin-bottom: 10mm; border-bottom: 2px solid #000; padding-bottom: 5mm; }}
        .barcode-box {{ text-align: center; margin-bottom: 10mm; }}
        .barcode-box img {{ width: 80%; height: 30mm; }}
        .barcode-text {{ font-size: 18px; font-weight: bold; letter-spacing: 2px; margin-top: 2px; }}
        table {{ width: 100%; border-collapse: collapse; margin-bottom: 10mm; }}
        th, td {{ border: 1px solid #333; padding: 12px; font-size: 16px; text-align: left; }}
        th {{ background-color: #eee; width: 30%; }}
        .qr-box {{ text-align: right; position: absolute; bottom: 10mm; right: 10mm; }}
        .qr-box img {{ width: 25mm; height: 25mm; }}
    </style>
    </head>
    <body>
        <div class="header">CDI 스크린 작업지시서</div>
        
        <div class="barcode-box">
            <img src="data:image/png;base64,{bc_b64}">
            <div class="barcode-text">{barcode_val}</div>
        </div>

        <table>
            <tr><th>원단 종류</th><td>{item_data.get('fabric', '-')}</td></tr>
            <tr><th>사이즈</th><td>{item_data.get('size', '-')}</td></tr>
            <tr><th>옵션/비고</th><td>{item_data.get('sheet_side') or '단일 상품'}</td></tr>
        </table>
        
        <div class="qr-box">
            <img src="data:image/png;base64,{qr_b64}">
            <div style="font-size:10px; text-align:center;">판매 사이트</div>
        </div>
    </body>
    </html>
    """

# ---------------------------------------------------------
# 3. 송장 / 패킹 슬립 템플릿 (A4 사이즈)
# ---------------------------------------------------------
def render_shipping_slip(order_no, items):
    logo_b64 = get_local_image_b64("gorilla_logo.png")
    logo_html = f'<img src="data:image/png;base64,{logo_b64}" style="max-height:40px;">' if logo_b64 else '<h2>CDI LOGISTICS</h2>'
    
    bc_b64 = get_base64_barcode(order_no)
    
    rows_html = ""
    for it in items:
        rows_html += f"<tr><td>{it.get('barcode')}</td><td>{it.get('fabric')}</td><td>{it.get('size')}</td></tr>"

    return f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
    <style>
        @page {{ size: A4; margin: 20mm; }}
        body {{ font-family: "Malgun Gothic", sans-serif; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 3px solid #000; padding-bottom: 10mm; margin-bottom: 10mm; }}
        .title {{ font-size: 28px; font-weight: 900; letter-spacing: -1px; }}
        .info-section {{ margin-bottom: 15mm; }}
        .info-section p {{ font-size: 16px; margin: 5px 0; }}
        .barcode-box {{ text-align: right; margin-bottom: 10mm; }}
        .barcode-box img {{ height: 20mm; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ border: 1px solid #aaa; padding: 12px; text-align: center; }}
        th {{ background-color: #f5f5f5; font-weight: bold; }}
    </style>
    </head>
    <body>
        <div class="header">
            {logo_html}
            <div class="title">출고 명세서 (Packing Slip)</div>
        </div>
        
        <div class="barcode-box">
            <img src="data:image/png;base64,{bc_b64}">
            <div>{order_no}</div>
        </div>

        <div class="info-section">
            <p><strong>주문 번호 :</strong> {order_no}</p>
            <p><strong>출력 일시 :</strong> 출력완료 시점</p>
        </div>

        <table>
            <thead>
                <tr>
                    <th>제품 바코드</th>
                    <th>원단/품목</th>
                    <th>사이즈/규격</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>
        
        <div style="margin-top: 30mm; text-align: center; color: #555;">
            검수가 완료된 상품입니다. 이용해 주셔서 감사합니다.
        </div>
    </body>
    </html>
    """