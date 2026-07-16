import base64
import os
import datetime  # <== 누락되었던 날짜 모듈 추가
from io import BytesIO
import qrcode
from barcode import Code128
from barcode.writer import ImageWriter

# ---------------------------------------------------------
# 이미지 렌더링 헬퍼 함수
# ---------------------------------------------------------
def get_base64_qr(data: str) -> str:
    if not data: return ""
    qr = qrcode.QRCode(box_size=4, border=0)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

def get_base64_barcode(data: str) -> str:
    if not data: return ""
    rv = BytesIO()
    Code128(data, writer=ImageWriter()).write(rv, options={"write_text": False, "module_height": 12, "quiet_zone": 1})
    return base64.b64encode(rv.getvalue()).decode("utf-8")

def get_local_image_b64(filename: str) -> str:
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
    sub_text = f"{code}" + (f" ({unit})" if unit else "")
    
    return f"""
    <!DOCTYPE html>
    <html lang="ja">
    <head>
    <meta charset="UTF-8">
    <style>
      @page {{ size: 90mm 29mm; margin: 0; }}
      html, body {{ margin: 0; padding: 0; background: #fff; }}
      * {{ box-sizing: border-box; }}
      .label {{
        width: 90mm; height: 29mm;
        display: flex; align-items: center; gap: 2.5mm;
        padding: 2mm 2.5mm;
        background: #fff; color: #000;
        font-family: Arial, Helvetica, "Yu Gothic", "Hiragino Kaku Gothic ProN", "Noto Sans JP", sans-serif;
        overflow: hidden;
      }}
      .qr {{ width: 25mm; height: 25mm; flex: 0 0 25mm; }}
      .qr img {{ width: 25mm; height: 25mm; display: block; image-rendering: pixelated; }}
      .info {{ flex: 1 1 auto; min-width: 0; }}
      .info .sub    {{ font-size: 2.5mm; font-weight: 600; color: #333; letter-spacing: .2mm; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
      .info .title  {{ font-size: 4.6mm; font-weight: 800; line-height: 1.08; margin: .5mm 0; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }}
      .info .serial {{ font-size: 5.4mm; font-weight: 900; letter-spacing: .4mm; font-family: "Consolas","Courier New",monospace; }}
    </style>
    </head>
    <body>
      <div class="label">
        <div class="qr"><img src="data:image/png;base64,{qr_b64}"></div>
        <div class="info">
          <div class="sub">{sub_text}</div>
          <div class="title">{name}</div>
          <div class="serial">{serial}</div>
        </div>
      </div>
    </body>
    </html>
    """

# ---------------------------------------------------------
# 2. 주문/공정 라벨 템플릿 (110mm x 290mm) - 실수로 지워진 원본 디자인 복구!
# ---------------------------------------------------------
def render_order_label(item_data: dict):
    barcode_val = item_data.get('barcode', item_data.get('order_no', ''))
    bc_b64 = get_base64_barcode(barcode_val)
    qr_b64 = get_base64_qr("https://cdigolf.base.ec/")
    logo_b64 = get_local_image_b64("gorilla_logo.png")
    
    fabric = item_data.get('fabric', 'DP')
    fabric_name = "ダブルレイヤーポリエステル生地" if fabric == "DP" else "ローノイズポリエステル生地" if fabric == "LN" else "スペシャルダブルレイヤーポリエステル生地" if fabric == "SDP" else fabric
    
    perf_dots = "".join(["<i></i>" for _ in range(22)])
    eyelet_dots = "".join(["<i></i>" for _ in range(7)])
    
    return f"""
    <!DOCTYPE html>
    <html lang="ja">
    <head>
    <meta charset="UTF-8">
    <style>
      @page {{ size: 110mm 290mm; margin: 0; }}
      html, body {{ margin: 0; padding: 0; background: #fff; }}
      * {{ box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; color-adjust: exact; }}
      .label {{ width: 110mm; height: 290mm; margin: 0; padding: 30mm 8mm 6mm 8mm; background: #fff; color: #000; font-family: Arial, Helvetica, "Yu Gothic", "Hiragino Kaku Gothic ProN", "Noto Sans JP", sans-serif; display: flex; flex-direction: column; justify-content: flex-end; overflow: hidden; }}
      .perf {{ display: flex; justify-content: space-between; align-items: center; padding: 0 1mm; }}
      .perf i {{ width: 1.9mm; height: 1.9mm; border-radius: 50%; background: #111; display: block; }}
      .cluster-top {{ margin-top: 8mm; }}
      .cluster-top > * {{ margin: 0; }}
      .head .code {{ font-size: 23mm; font-weight: 900; line-height: 1; letter-spacing: -0.5mm; }}
      .head .name {{ font-size: 6.2mm; font-weight: 800; margin-top: 1.8mm; letter-spacing: 0.05mm; }}
      table.spec {{ border-collapse: collapse; margin-top: 1.5mm; width: 100%; }}
      table.spec td {{ font-size: 4.8mm; line-height: 8.1mm; padding: 0; vertical-align: top; white-space: nowrap; font-weight: 800; }}
      table.spec .en {{ font-weight: 900; width: 23mm; }}
      table.spec .jp {{ font-weight: 800; width: 28mm; }}
      table.spec .v1 {{ font-weight: 900; width: 27mm; }}
      .barcode-wrap {{ margin-top: 3mm; text-align: center; }}
      .barcode-wrap img.bc-img {{ width: 92mm; height: 30mm; }}
      .barcode-text {{ font-size: 4.2mm; font-weight: 900; letter-spacing: 0.45mm; margin-top: 1.2mm; }}
      .mid {{ display: flex; gap: 6mm; align-items: stretch; margin-top: 2mm; }}
      .qr {{ width: 48mm; position: relative; }}
      .qr img.qr-img {{ width: 48mm; height: 48mm; display: block; image-rendering: pixelated; }}
      .qr .logo {{ position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%); width: 11mm; height: 11mm; background: #fff; border-radius: 1mm; display: flex; align-items: center; justify-content: center; }}
      .qr .logo img {{ width: 9.5mm; height: auto; display: block; }}
      .orient {{ flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; }}
      .orient .title {{ font-size: 3.4mm; font-weight: 800; margin-bottom: 4mm; letter-spacing: 0.2mm; }}
      .odiagram {{ border-collapse: collapse; }}
      .odiagram td {{ text-align: center; vertical-align: middle; padding: 1mm 1.5mm; }}
      .odiagram .oc {{ font-size: 3.0mm; font-weight: 800; white-space: nowrap; }}
      .odiagram .obox {{ width: 22mm; height: 27mm; border: 0.5mm solid #000; }}
      .obox .oarrow {{ display: block; font-size: 5.5mm; line-height: 1; }}
      .obox .oup {{ display: block; font-size: 3.6mm; font-weight: 800; margin-top: 0.5mm; }}
      .obox .ofront {{ display: block; font-size: 3.6mm; font-weight: 800; margin-top: 0.8mm; }}
      .foot {{ text-align: center; line-height: 5.8mm; margin-top: 7mm; }}
      .foot .company {{ font-size: 3.8mm; font-weight: 900; }}
      .foot .addr {{ font-size: 3.2mm; font-weight: 700; }}
      .foot .design {{ font-size: 3.8mm; font-weight: 900; margin-top: 1.8mm; letter-spacing: 0.2mm; }}
      .foot .brand-logo {{ display: block; width: 100mm; max-width: none; height: auto; margin: 2.6mm -3mm 0; }}
      .eyelets {{ display: flex; justify-content: space-between; padding: 0 3mm; margin-top: 2.4mm; margin-bottom: 2.0mm; }}
      .eyelets i {{ width: 7mm; height: 7mm; border-radius: 50%; border: 0.9mm solid #111; position: relative; display: block; }}
      .eyelets i::after {{ content: ""; position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%); width: 3.2mm; height: 3.2mm; border-radius: 50%; border: 0.7mm solid #111; }}
    </style>
    </head>
    <body>
      <div class="label">
        <div class="perf">{perf_dots}</div>
        <div class="cluster-top">
          <div class="head">
            <div class="code">{fabric}</div>
            <div class="name">{fabric_name}</div>
          </div>
          <table class="spec">
            <tr><td class="en">Fabric</td><td class="jp">生地</td><td class="v1" colspan="2">{fabric}</td></tr>
            <tr><td class="en">Size</td><td class="jp">サイズ</td><td class="v1" colspan="2">{item_data.get('size', '-')}</td></tr>
            <tr><td class="en">Top</td><td class="jp">上端</td><td class="v1" colspan="2">{item_data.get('e_top', '-')}</td></tr>
            <tr><td class="en">Bottom</td><td class="jp">下端</td><td class="v1" colspan="2">{item_data.get('e_bottom', '-')}</td></tr>
            <tr><td class="en">Left</td><td class="jp">左側</td><td class="v1" colspan="2">{item_data.get('e_left', '-')}</td></tr>
            <tr><td class="en">Right</td><td class="jp">右側</td><td class="v1" colspan="2">{item_data.get('e_right', '-')}</td></tr>
          </table>
          <div class="barcode-wrap">
            <img class="bc-img" src="data:image/png;base64,{bc_b64}">
            <div class="barcode-text">{barcode_val}</div>
          </div>
        </div>
        <div class="mid">
          <div class="qr">
            <img class="qr-img" src="data:image/png;base64,{qr_b64}">
            <div class="logo"><img src="data:image/png;base64,{logo_b64}"></div>
          </div>
          <div class="orient">
            <div class="title">取付方向 / ORIENTATION</div>
            <table class="odiagram">
              <tr><td></td><td class="oc">上：{item_data.get('e_top', '-')}</td><td></td></tr>
              <tr>
                <td class="oc">左：{item_data.get('e_left', '-').replace('ハトメ ', '')}</td>
                <td class="obox"><span class="oarrow">▲</span><span class="oup">上</span><span class="ofront">表</span></td>
                <td class="oc">右：{item_data.get('e_right', '-').replace('ハトメ ', '')}</td>
              </tr>
              <tr><td></td><td class="oc">下：{item_data.get('e_bottom', '-')}</td><td></td></tr>
            </table>
          </div>
        </div>
        <div class="foot">
          <div class="company">株式会社シーディアイ</div>
          <div class="addr">〒491-0922 愛知県一宮市大和町妙興寺字丹波12番</div>
          <div class="addr">Tel 0586-27-0123&nbsp;&nbsp;&nbsp;https://www.cdi.jpn.com/</div>
          <div class="design">Design and Quality CDI of JAPAN</div>
          <img class="brand-logo" src="data:image/png;base64,{logo_b64}">
        </div>
        <div class="eyelets">{eyelet_dots}</div>
        <div class="perf" style="margin-top:0;">{perf_dots}</div>
      </div>
    </body>
    </html>
    """

# ---------------------------------------------------------
# 3. 송장 / 출하 명세서 템플릿 (A4 사이즈)
# ---------------------------------------------------------
def render_shipping_slip(order_no, order_info: dict, items: list):
    today_str = datetime.datetime.now().strftime("%Y/%m/%d")
    
    rows_html = ""
    if items:
        for it in items:
            rows_html += f"<tr><td>{it.get('barcode')}</td><td>{it.get('fabric')}</td><td>{it.get('size')}</td></tr>"
    else:
        rows_html = '<tr><td colspan="3">明細なし</td></tr>'

    postal = order_info.get("postal_code") or "—"
    addr = order_info.get("address") or "住所未登録"
    name = order_info.get("customer_name") or ""
    phone = order_info.get("phone") or "—"
    channel = order_info.get("channel") or ""
    pay_status = order_info.get("payment_status") or ""

    return f"""
    <!DOCTYPE html>
    <html lang="ja">
    <head>
    <meta charset="UTF-8">
    <style>
      *{{box-sizing:border-box}}
      @page {{ size: A4; margin: 15mm; }}
      body{{font-family:"Yu Gothic UI","Noto Sans JP",sans-serif;margin:0;padding:18px;color:#111;background:#fff}}
      .slip{{border:2px solid #111;border-radius:6px;max-width:460px;margin:0 auto;background:#fff}}
      .hd{{background:#111;color:#fff;padding:9px 13px;font-weight:800;font-size:15px;display:flex;justify-content:space-between}}
      .sec{{padding:11px 15px;border-bottom:1px dashed #999}}
      .lbl{{font-size:11px;color:#666;margin-bottom:2px}}
      .val{{font-size:15px;font-weight:700}} .big{{font-size:21px;letter-spacing:1px}}
      .row{{display:flex;gap:14px}} .row>div{{flex:1}}
      .foot{{padding:8px 15px;font-size:11px;color:#666;display:flex;justify-content:space-between}}
      table{{width:100%;border-collapse:collapse;margin-top:6px;font-size:13px;text-align:left;}}
      th{{color:#666;font-weight:normal;font-size:11px;border-bottom:1px solid #ddd;padding-bottom:4px}}
      td{{padding:6px 0;border-bottom:1px solid #eee}}
    </style>
    </head>
    <body>
      <div class="slip">
        <div class="hd">CDI 出荷明細書 (Packing Slip) <span>{today_str}</span></div>
        <div class="sec">
          <div class="lbl">お届け先 / TO</div>
          <div class="val big">〒 {postal}</div>
          <div class="val">{addr}</div>
          <div class="val" style="margin-top:6px">{name} 様</div>
          <div class="val">TEL: {phone}</div>
        </div>
        <div class="sec row">
          <div><div class="lbl">ご依頼主 / FROM</div><div class="val">株式会社シーディアイ</div>
            <div style="font-size:12px">〒491-0922 愛知県一宮市</div></div>
          <div><div class="lbl">個口数</div><div class="val big">{len(items)}</div>
            <div class="lbl" style="margin-top:6px">注文番号</div><div class="val">{order_no}</div></div>
        </div>
        <div class="sec">
          <div class="lbl">内容品 / ITEMS</div>
          <table>
            <tr><th>製品番号</th><th>生地</th><th>サイズ</th></tr>
            {rows_html}
          </table>
        </div>
        <div class="foot">
          <span>チャネル: {channel}</span>
          <span>決済: {pay_status}</span>
        </div>
      </div>
    </body>
    </html>
    """