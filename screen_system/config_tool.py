import tkinter as tk
from tkinter import ttk, messagebox
import serial.tools.list_ports
import json
import os

# 저장될 JSON 파일 이름 (app.py와 같은 경로)
CONFIG_FILE = "scanner_config.json"

def get_com_ports():
    """현재 PC에 연결된 모든 COM 포트를 가져옵니다."""
    ports = serial.tools.list_ports.comports()
    return [p.device for p in ports]

class ScannerConfigurator:
    def __init__(self, root):
        self.root = root
        self.root.title("QR 스캐너 포트 설정 매니저")
        self.root.geometry("600x400")
        self.root.configure(padx=20, pady=20)
        
        # 상단 제목
        tk.Label(root, text="연결된 스캐너(COM 포트) 설정", font=("맑은 고딕", 16, "bold")).pack(pady=(0, 20))
        
        # 포트 목록을 담을 프레임
        self.frame = tk.Frame(root)
        self.frame.pack(fill=tk.BOTH, expand=True)
        
        # 테이블 헤더
        headers = ["COM 포트", "통신속도", "스캔 용도", "할당 공정(모니터 전용)"]
        for col, text in enumerate(headers):
            tk.Label(self.frame, text=text, font=("맑은 고딕", 10, "bold"), bg="#e2e8f0", width=15).grid(row=0, column=col, padx=2, pady=5)
        
        self.rows = []
        self.load_ui()
        
        # 하단 저장 버튼
        save_btn = tk.Button(root, text="설정 저장하기 (JSON)", font=("맑은 고딕", 12, "bold"), 
                             bg="#0e9f5a", fg="white", width=25, command=self.save_config)
        save_btn.pack(pady=20)
        
    def load_ui(self):
        # 1. 기존에 저장된 설정(scanner_config.json) 읽어오기
        existing = {}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    for item in json.load(f):
                        existing[item['port']] = item
            except:
                pass
                
        # 2. 현재 꽂혀있는 포트 감지
        ports = get_com_ports()
        if not ports:
            tk.Label(self.frame, text="현재 PC에 연결된 COM 포트(스캐너)가 없습니다.", fg="red").grid(row=1, columnspan=4, pady=20)
            return
            
        # 3. 각 포트별로 설정 UI (콤보박스) 생성
        for i, port in enumerate(ports, start=1):
            conf = existing.get(port, {})
            
            # 포트 이름
            tk.Label(self.frame, text=port, font=("Arial", 11, "bold")).grid(row=i, column=0, pady=10)
            
            # 통신속도(Baudrate)
            baud_var = tk.StringVar(value=str(conf.get("baudrate", 9600)))
            baud_cb = ttk.Combobox(self.frame, textvariable=baud_var, values=["9600", "115200"], state="readonly", width=12)
            baud_cb.grid(row=i, column=1, padx=5)
            
            # 용도 (monitor=공정모니터, worker=일반작업자, 사용안함)
            type_var = tk.StringVar(value=conf.get("type", "사용안함"))
            type_cb = ttk.Combobox(self.frame, textvariable=type_var, values=["사용안함", "monitor", "worker"], state="readonly", width=12)
            type_cb.grid(row=i, column=2, padx=5)
            
            # 공정 (용도가 monitor일 때만 적용됨)
            proc_var = tk.StringVar(value=conf.get("proc", ""))
            proc_cb = ttk.Combobox(self.frame, textvariable=proc_var, values=["", "cutting", "sewing", "eyelet", "packing"], state="readonly", width=12)
            proc_cb.grid(row=i, column=3, padx=5)
            
            self.rows.append({
                "port": port,
                "baud_var": baud_var,
                "type_var": type_var,
                "proc_var": proc_var
            })

    def save_config(self):
        config_list = []
        for row in self.rows:
            typ = row["type_var"].get()
            if typ == "사용안함":
                continue  # 사용 안하는 포트는 JSON에 저장하지 않음
            
            config_list.append({
                "port": row["port"],
                "baudrate": int(row["baud_var"].get()),
                "type": typ,
                "proc": row["proc_var"].get() if typ == "monitor" else ""
            })
            
        # JSON 파일로 저장
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config_list, f, indent=4, ensure_ascii=False)
            messagebox.showinfo("저장 완료", f"'{CONFIG_FILE}' 파일이 성공적으로 생성되었습니다.\n\napp.py를 재시작하면 변경된 스캐너가 즉시 적용됩니다.")
        except Exception as e:
            messagebox.showerror("저장 실패", f"파일을 저장하는 중 오류가 발생했습니다:\n{e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = ScannerConfigurator(root)
    root.mainloop()