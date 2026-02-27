import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
from app.database import init_db
from app.routers import auth, chat, analysis, search

# 앱 시작 시 DB 테이블 생성
init_db()

app = FastAPI(
    title="BINI API",
    description="상품 출시 전 특허 침해 여부 사전 검증 서비스",
    version="1.0.0"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록 (프론트엔드 API 경로에 맞춤)
app.include_router(auth.router, prefix="/api/auth", tags=["인증"])
app.include_router(chat.router, prefix="/api/chat", tags=["채팅"])
app.include_router(analysis.router, prefix="/api/analysis", tags=["분석"])
app.include_router(search.router, prefix="/api/search", tags=["검색"])


# FRONTEND 정적 파일 서빙 (http://localhost:8000 에서 HTML 접속 가능)
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "FRONTEND"

@app.get("/")
async def root():
    """메인 페이지 → FRONTEND/index.html"""
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "BINI API 서버가 실행 중입니다."}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


# FRONTEND 정적 파일 (CSS, JS, 이미지 등) - 반드시 라우터 등록 이후에 마운트
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
