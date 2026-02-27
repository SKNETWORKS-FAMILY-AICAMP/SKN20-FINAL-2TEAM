"""FastAPI 앱 엔트리포인트 — GPT 전용 버전.

원본: main.py
변경:
  1. chat → chat_gpt 라우터 사용
  2. design → design_gpt 라우터 사용

실행:
  cd backend
  uvicorn app.main_gpt:app --host 0.0.0.0 --port 8080 --reload
"""

from pathlib import Path
from dotenv import load_dotenv

# 프로젝트 루트 .env 로드 (라우터 import 전에 실행해야 함)
_PROJECT_ROOT = Path(__file__).parent.parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from app.config import settings
from app.database import init_db

# ── 변경: chat_gpt 라우터 사용 (design_gpt는 메모리 절약을 위해 선택적 로드) ──
from app.routers import auth, chat_gpt, analysis, search
try:
    from app.routers import design_gpt
    _DESIGN_LOADED = True
except Exception as e:
    _DESIGN_LOADED = False
    print(f"[main_gpt] 디자인 모듈 미로드 (메모리 절약): {e}")

# 앱 시작 시 DB 테이블 생성
init_db()

app = FastAPI(
    title="BINI API (GPT 버전)",
    description="상품 출시 전 특허 침해 여부 사전 검증 서비스 (OpenAI GPT)",
    version="1.0.0"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 라우터 등록
app.include_router(auth.router, prefix="/api/auth", tags=["인증"])
app.include_router(chat_gpt.router, prefix="/api/chat", tags=["채팅"])
app.include_router(analysis.router, prefix="/api/analysis", tags=["분석"])
app.include_router(search.router, prefix="/api/search", tags=["검색"])
if _DESIGN_LOADED:
    app.include_router(design_gpt.router, prefix="/api/analysis", tags=["디자인분석"])


@app.get("/health")
async def health_check():
    return {"status": "healthy", "variant": "gpt"}


# 프론트엔드 정적 파일 서빙 (API 라우터 등록 후 마지막에 마운트)
FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../FRONTEND"))

if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
