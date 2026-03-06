from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
import os
import time

import threading

from app.config import settings
from app.database import init_db
from app.routers import auth, chat, analysis, search, design, project
from app.logger import logger

# 앱 시작 시 DB 테이블 생성
init_db()


def _preload_rag():
    """서버 시작 시 RAG 모델을 백그라운드로 미리 로딩."""
    try:
        from rag.search.retriever import _get_model, _get_collection, _load_sparse_index
        _get_model()
        _get_collection()
        _load_sparse_index()
        logger.info("RAG 모델 사전 로딩 완료")
    except Exception as e:
        logger.warning(f"RAG 사전 로딩 실패 (첫 요청 시 재시도): {e}")


def _preload_design():
    """서버 시작 시 디자인 그래프를 백그라운드로 미리 로딩."""
    try:
        from app.routers.design import _ensure_design_graph_loaded
        _ensure_design_graph_loaded()
        logger.info("디자인 그래프 사전 로딩 완료")
    except Exception as e:
        logger.warning(f"디자인 사전 로딩 실패 (첫 요청 시 재시도): {e}")


threading.Thread(target=_preload_rag, daemon=True).start()
threading.Thread(target=_preload_design, daemon=True).start()

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
app.include_router(project.router, prefix="/api/projects", tags=["프로젝트"])


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
