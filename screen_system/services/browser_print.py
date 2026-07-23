"""
ラベルを Chrome(ヘッドレス)で PDF 化して印刷する。

なぜ必要か:
  自動印刷を「画面で見えているラベル(label_gorilla.html)」と完全に一致させるため。
  WeasyPrint は JavaScript を実行できず、CSS の一部(scaleX 等)も画面と差が出る。
  そこで PC に入っている Chrome/Edge で /label ページをそのまま PDF 化する。

安全策:
  Chrome が見つからない・失敗・PDF が空 のいずれでも False を返す。
  呼び出し側(create_order)はその時だけ従来の WeasyPrint 経路に自動で切り替える。
  → ラベルが1枚も出ない、という事態は起きない。
"""

import os
import subprocess
import tempfile

from config import (
    CHROME_CANDIDATES, SERVER_BASE_URL, SUMATRA_PATH,
)
from services.printing import get_printer_name


def find_chrome():
    """Chrome / Edge の実行ファイルを探す。無ければ None。"""
    for p in CHROME_CANDIDATES:
        if os.path.exists(p):
            return p
    # PATH 上に chrome / msedge があれば拾う
    from shutil import which
    return which("chrome") or which("chrome.exe") or which("msedge") or which("msedge.exe")


def render_label_pdf(barcode: str, out_path: str, tpl: str = "") -> bool:
    """/label/{barcode} を Chrome でレンダリングして PDF 化する。成功なら True。"""
    chrome = find_chrome()
    if not chrome:
        print("⚠️ Chrome/Edge が見つかりません → WeasyPrint 経路に切替")
        return False

    # ?print=1 は付けない(画面の window.print() を誘発しないため)。
    # tpl を渡すと注文ごとに選んだ版(小型など)で描画される。空なら管理画面の既定版。
    url = f"{SERVER_BASE_URL}/label/{barcode}"
    if tpl:
        url += f"?tpl={tpl}"
    user_data = tempfile.mkdtemp(prefix="cdi_chrome_")
    cmd = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        f"--user-data-dir={user_data}",
        "--no-pdf-header-footer",
        "--prefer-css-page-size",          # @page のサイズ(110×412mm)を尊重
        "--virtual-time-budget=5000",      # JS(バーコード/QR/データ取得)の完了を待つ
        f"--print-to-pdf={out_path}",
        url,
    ]
    try:
        subprocess.run(cmd, check=True, timeout=40,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"⚠️ Chrome 印刷失敗({e}) → WeasyPrint 経路に切替")
        return False

    if not os.path.exists(out_path) or os.path.getsize(out_path) < 1000:
        print("⚠️ Chrome が有効な PDF を作れませんでした → WeasyPrint 経路に切替")
        return False
    return True


def print_label_via_chrome(barcode: str, printer_key: str, tpl: str = "") -> bool:
    """バーコード1枚を Chrome で PDF 化 → SumatraPDF で印刷。成功なら True。

    tpl: この注文で使うラベル版のキー(小型など)。画面と同じ版で印刷させる。
    どこかで失敗したら False を返すだけで例外は投げない(呼び出し側がフォールバック)。
    """
    printer_name = get_printer_name(printer_key)
    if not printer_name:
        print(f"⚠️ {printer_key} にプリンタ未設定 → 印刷スキップ")
        return True   # 印刷しない設定なので「フォールバック不要」の意味で True

    pdf_path = os.path.join(tempfile.gettempdir(), f"cdi_label_{barcode}.pdf")
    try:
        if not render_label_pdf(barcode, pdf_path, tpl):
            return False
        subprocess.run([SUMATRA_PATH, "-print-to", printer_name,
                        "-print-settings", "noscale", pdf_path],
                       check=True, timeout=40)
        print(f"🖨️ [{printer_name}] Chrome経路で印刷完了: {barcode}")
        return True
    except Exception as e:
        print(f"⚠️ Chrome経路の印刷で失敗({e}) → WeasyPrint 経路に切替")
        return False
    finally:
        if os.path.exists(pdf_path):
            try:
                os.remove(pdf_path)
            except OSError:
                pass
