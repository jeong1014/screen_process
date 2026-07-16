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
    logo_cdi = "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"
    
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
      #perfBottom {{ margin-top: 0; }}
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
            <div class="logo"><img src="data:image/png;base64,{logo_cdi}" alt="CDI"></div>
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
        <div class="eyelets" id="eyelets">{eyelet_dots}</div>
        <div class="perf" id="perfBottom">{perf_dots}</div>
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