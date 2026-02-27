from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from app.config import settings
from app.database import init_db
from app.routers import auth, chat, analysis, search, design

# 앱 시작 시 DB 테이블 생성
try:
    init_db()
except Exception as e:
    print(f"[WARNING] DB 초기화 실패 (로컬 개발 시 무시 가능): {e}")

app = FastAPI(
    title="BINI API",
    description="상품 출시 전 특허 침해 여부 사전 검증 서비스",
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
app.include_router(chat.router, prefix="/api/chat", tags=["채팅"])
app.include_router(analysis.router, prefix="/api/analysis", tags=["분석"])
app.include_router(search.router, prefix="/api/search", tags=["검색"])
app.include_router(design.router, prefix="/api/analysis", tags=["디자인분석"])


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


# 디자인 독립 페이지 (design/src/index.html)
DESIGN_SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../design/src"))


@app.get("/design-standalone")
async def design_standalone():
    """design/src/index.html 독립 페이지"""
    index_path = os.path.join(DESIGN_SRC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path, media_type="text/html")
    raise HTTPException(status_code=404, detail="design/src/index.html not found")


# 프론트엔드 정적 파일 서빙 (API 라우터 등록 후 마지막에 마운트)
FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../FRONTEND"))

if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
