from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
import os
import time

from app.config import settings
from app.database import init_db
from app.routers import auth, chat, analysis, search, design
from app.logger import logger

# 앱 시작 시 DB 테이블 생성
init_db()

app = FastAPI(
    title="BINI API",
    description="상품 출시 전 특허 침해 여부 사전 검증 서비스",
    version="1.0.0"
)


# 요청 시간 측정 미들웨어
@app.middleware("http")
async def log_request_time(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    elapsed = time.time() - start
    # 정적 파일(.html, .css, .js, 이미지)은 로깅 스킵
    path = request.url.path
    if path.startswith("/api/"):
        logger.info(f"{request.method} {path} {response.status_code} [{elapsed:.2f}s]")
    return response


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


@app.get("/favicon.ico")
async def favicon():
    svg_path = os.path.join(FRONTEND_DIR, "favicon.svg")
    if os.path.exists(svg_path):
        return FileResponse(svg_path, media_type="image/svg+xml")
    return Response(status_code=204)


# 프론트엔드 정적 파일 서빙 (API 라우터 등록 후 마지막에 마운트)
FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../FRONTEND"))

if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
