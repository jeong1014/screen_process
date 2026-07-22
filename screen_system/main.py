"""
スクリーン原団 工場工程管理システム — FastAPI バックエンド (v2)

役割: ブラウザHTML(入力/作業者/ダッシュボード)と PostgreSQL の仲介。
  進行状態 stage(0〜6) を order_items.current_stage で一元管理。
  「注文番号(製品番号)」= order_items.barcode。

実行:  uvicorn main:app --reload --host 0.0.0.0 --port 8000
必要:  pip install fastapi uvicorn "psycopg[binary]"
DB  :  環境変数 DATABASE_URL

구성:
  config.py    설정·상수      schemas.py  요청 모델
  db.py        DB 접속        security.py 관리자 인증
  services/    비즈니스 로직 (라우터를 import 하지 않음)
  routers/     HTTP 라우트 (얇은 껍데기)
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import FRONTEND_DIR
from routers import pages, public
from routers.admin import admin_router
from services.scanner import start_serial_scanners


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 서버 기동 시 시리얼 바코드 스캐너 리스너를 데몬 스레드로 띄운다.
    start_serial_scanners()
    yield


app = FastAPI(title="スクリーン原団 工程管理 v2", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# 라우터 등록 — 순서는 원본 app.py 의 정의 순서를 따른다.
app.include_router(pages.router)
app.include_router(public.router)
app.include_router(admin_router)

if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
