"""
시리얼 바코드 스캐너 백그라운드 스레드 (JSON 설정 기반).
"""

import json
import os
import re
import threading
import time

import serial
from fastapi import HTTPException

from config import SCANNER_CONFIG_PATH
from db import db
from services.stage import (
    move_stage, monitor_scan,
)
from services.inventory import inv_scan
from services.shipping import fetch_order_by_id, auto_print_shipping_slip


# JSON 설정 파일을 읽어오는 함수
def load_scanner_config():
    config_path = SCANNER_CONFIG_PATH
    if not os.path.exists(config_path):
        print(f"⚠️ 설정 파일({config_path})이 없습니다. 스캐너 연동 없이 시작합니다.")
        return []
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            print(f"📄 스캐너 설정 파일 로드 완료! (총 {len(config)}대 스캐너 연결 예정)")
            return config
    except Exception as e:
        print(f"❌ 설정 파일 읽기 오류: {e}")
        return []


def _serial_reader_worker(config):
    port = config.get("port")
    baudrate = config.get("baudrate", 9600)
    scan_type = config.get("type")
    proc = config.get("proc")
    
    while True:
        try:
            print(f"🔌 [{port}] 시리얼 포트 연결 시도 중...")
            with serial.Serial(port, baudrate, timeout=1) as ser:
                print(f"🟢 [{port}] 연결 성공! 바코드 대기 중... (매핑: {scan_type} / {proc or '없음'})")
                
                while ser.is_open:
                    if ser.in_waiting > 0:
                        barcode_data = ser.readline().decode('utf-8').strip()
                        if barcode_data:
                            print(f"📥 [{port}] 바코드 스캔 감지: {barcode_data}")
                            
                            try:
                                # 🌟 1. 재고 바코드인지 먼저 검사 (형식: 숫자2~4자리 - 숫자3~6자리)
                                if re.match(r"^\d{2,4}-\d{3,6}$", barcode_data):
                                    result = inv_scan(barcode_data)  # 재고 차감 서비스 직접 호출
                                    print(f"📦 [{port}] 재고 스캔 처리 완료: {result}")
                                    continue  # 재고 처리를 완료했으므로 아래의 공정 진행 로직은 건너뜀 (중요)
                                
                                # 🌟 2. 일반 생산/공정 바코드인 경우 기존 로직 수행
                                if scan_type == "monitor":
                                    result = monitor_scan(proc, barcode_data)
                                    print(f"✅ [{port}] 모니터 스캔 처리 완료: {result}")
                                    if result.get("ok") and result.get("stage_name") == "ハトメ完了":
                                        print(f"📦 [{port}] 제품 {barcode_data} 최종 공정 완료 -> 송장 자동 출력 개시")
                                        
                                        with db() as conn, conn.cursor() as cur:
                                            # order_items 에는 order_no 가 없으므로 order_id 로 주문을 역추적한다.
                                            cur.execute("SELECT order_id FROM order_items WHERE barcode=%s", (barcode_data,))
                                            item_info = cur.fetchone()
                                            if item_info:
                                                order_id = item_info["order_id"]
                                                order_info = fetch_order_by_id(cur, order_id)
                                                order_no = order_info.get("order_no", "UNKNOWN")
                                                auto_print_shipping_slip(cur, order_no, order_id, order_info)
                                elif scan_type == "worker":
                                    result = move_stage(barcode_data, +1)
                                    print(f"✅ [{port}] 작업자 스캔 처리 완료: {result['order_no']} (Stage: {result['stage']})")
                                    
                            except HTTPException as he:
                                print(f"⚠️ [{port}] 거부됨 ({he.status_code}): {he.detail}")
                            except Exception as e:
                                print(f"❌ [{port}] DB 처리 오류: {e}")
                                
                    time.sleep(0.05)
                    
        except serial.SerialException as e:
            print(f"❌ [{port}] 연결 실패 또는 유실 (5초 후 재시도)...")
            time.sleep(5)
        except Exception as e:
            time.sleep(5)


def start_serial_scanners():
    """서버 시작 시 JSON 파일을 읽고 백그라운드 스레드를 구동합니다.

    main.py 의 lifespan 에서 호출된다."""
    # 하드코딩 대신 함수를 호출해 JSON 데이터를 가져옵니다.
    ports_config = load_scanner_config()
    
    if ports_config:
        print("🚀 [System] 통합 시리얼 포트 백그라운드 리스너 구동을 시작합니다.")
        for config in ports_config:
            t = threading.Thread(target=_serial_reader_worker, args=(config,), daemon=True)
            t.start()
