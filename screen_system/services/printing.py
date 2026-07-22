"""
프린터 출력 — HTML을 WeasyPrint로 PDF 변환 후 SumatraPDF로 무설정 출력.

printer_config.json 의 키(예: invoice_printer)로 실제 프린터명을 찾아 쓴다.
"""

import json
import os
import subprocess

from weasyprint import HTML

from config import PRINTER_CONFIG_PATH, SUMATRA_PATH


def get_printer_name(printer_key: str) -> str:
    if not os.path.exists(PRINTER_CONFIG_PATH):
        print("⚠️ 프린터 설정 파일(printer_config.json)이 없어 기본 기본 프린터를 사용합니다.")
        return ""
    try:
        with open(PRINTER_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            return cfg.get(printer_key, "")
    except Exception as e:
        print(f"❌ 프린터 설정 로드 실패: {e}")
        return ""


def silent_print_html(html_content: str, printer_key: str):
    """HTML 소스를 받아 PDF로 렌더링한 후, 지정된 프린터로 조용히 출력합니다."""
    printer_name = get_printer_name(printer_key)
    if not printer_name:
        print(f"⚠️ {printer_key}에 매핑된 프린터가 없습니다. 출력을 건너뜁니다.")
        return

    pdf_temp_path = "temp_print_job.pdf"

    try:
        # 1. WeasyPrint를 사용해 HTML을 규격에 맞는 PDF로 변환 (CSS @page 반영됨)
        HTML(string=html_content).write_pdf(pdf_temp_path)

        # 2. SumatraPDF를 이용해 백그라운드 무설정 출력 실행
        # -print-to <프린터명>: 해당 프린터로 즉시 전송
        # -print-settings "noscale": 라벨 인쇄 시 여백/스케일 왜곡 방지
        cmd = [
            SUMATRA_PATH,
            "-print-to", printer_name,
            "-print-settings", "noscale",
            pdf_temp_path
        ]

        print(f"🖨️ [{printer_name}] 출력 요청 전송 중...")
        subprocess.run(cmd, check=True)
        print("✅ 출력 완료!")

    except Exception as e:
        print(f"❌ 자동 출력 중 에러 발생: {e}")
    finally:
        # 임시 생성된 PDF 파일 제거
        if os.path.exists(pdf_temp_path):
            os.remove(pdf_temp_path)
