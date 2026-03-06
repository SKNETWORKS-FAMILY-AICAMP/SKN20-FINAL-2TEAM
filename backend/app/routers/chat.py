from fastapi import APIRouter, Depends, HTTPException, status, Form
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from openai import OpenAI
import asyncio
import json
import os
import sys
import time
from app.logger import logger

# RAG 모듈 경로 추가 (backend/app/routers/chat.py 기준 4단계 상위 = 프로젝트 루트)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from app.database import get_db
from app.schemas.chat import ChatCreate, ChatResponse, ChatListResponse, MessageCreate, MessageResponse
from app.services.chat_service import ChatService
from app.services.auth_service import AuthService
from app.models.user import User

router = APIRouter()

# vLLM 클라이언트 (RunPod 서버리스)
VLLM_BASE_URL = os.getenv("RUNPOD_PATENT_BASE_URL") or os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1")
VLLM_MODEL = os.getenv("PATENT_VLLM_MODEL", "itsbini/qwen2.5-14b-fto-merged")
RUNPOD_API_KEY = os.getenv("RUNPOD_API_KEY", "")

SYSTEM_PROMPT = """당신은 화장품 특허 침해(FTO) 분석 전문가입니다.

[문구 규칙]
- "판단"이라는 단어 사용 금지 → "분석"으로 대체
- "리스크" 사용 금지 → "가능성"으로 대체

[분석 규칙]
- 구성요소 완비의 원칙: 모든 구성요소를 포함해야 침해
- 균등론: 특허 구성 수치가 경미하게 이탈 시 전문가 검토 대상
- 금반언: 공개청구항에는 있었지만, 등록청구항에는 삭제된 구성은 침해 주장 불가
- 내재성: 성분 동일 + 용도/효과 미언급 시 "미대응(내재성)"

[대응 여부]
- 대응: 동일/포함
- 미대응: 해당 구성 없음
- 미대응(균등): 수치 경미 이탈
- 미대응(내재성): 용도/효과 미언급
- 확인불가: 정보 부족

[출력 형식]
◆구성 대비◆ → 테이블
◆분석◆ → 분석 설명 (결론성 문구 금지)
◆결론◆ → 아래 4개 중 하나만:
- "침해 가능성이 높은 것으로 분석됩니다."
- "침해 가능성이 낮은 것으로 분석됩니다."
- "전문가의 추가 검토가 권고됩니다."
- "침해 여부 분석을 위해 보다 구체적인 실시 정보가 필요합니다."

사용자가 제품 설명을 하면 FTO 분석에 필요한 정보를 대화로 수집하고, 특허 청구항이 제공되면 침해 분석을 수행하세요."""


# ==================== 프론트엔드용 스키마 ====================

class ChatMessageRequest(BaseModel):
    """프론트엔드 채팅 메시지 요청"""
    session_id: Optional[int] = None  # chat_id
    message: str
    analysis_type: str = "fto"  # fto | design
    context: Optional[dict] = None


class ChatMessageResponse(BaseModel):
    """프론트엔드 채팅 메시지 응답"""
    message: str
    session_id: Optional[int] = None
    context: Optional[dict] = None
    analysis_complete: bool = False
    analysis_id: Optional[int] = None


# ==================== 라우터 ====================

def get_chat_service(db: Session = Depends(get_db)) -> ChatService:
    return ChatService(db)


@router.get("", response_model=List[ChatListResponse])
async def get_chats(
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(AuthService.get_current_user_dependency)
):
    """내 채팅 목록 조회"""
    return service.get_user_chats(current_user.id)


@router.post("", response_model=ChatResponse, status_code=status.HTTP_201_CREATED)
async def create_chat(
    chat_data: ChatCreate,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(AuthService.get_current_user_dependency)
):
    """새 채팅 생성"""
    return service.create_chat(current_user.id, chat_data.title)


@router.get("/analysis/{analysis_id}")
async def get_analysis_result(
    analysis_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(AuthService.get_current_user_dependency),
):
    """분석 결과 조회 (result_json의 patent_analyses 반환)"""
    from app.models.analysis import Analysis

    analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="분석 결과를 찾을 수 없습니다.")

    result = analysis.result_json or {}
    patent_analyses = result.get("fto_result", {}).get("patent_analyses", [])
    search_results = result.get("search_results", [])

    return {
        "analysis_id": analysis.id,
        "risk_level": analysis.risk_level.value if analysis.risk_level else None,
        "patent_analyses": patent_analyses,
        "search_results": search_results,
    }


@router.get("/{chat_id}")
async def get_chat(
    chat_id: int,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(AuthService.get_current_user_dependency)
):
    """채팅 상세 조회 (메시지 + analysis_id 포함)"""
    from app.schemas.chat import MessageResponse as MsgResp

    chat = service.get_chat(chat_id, current_user.id)

    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="채팅을 찾을 수 없습니다."
        )

    return {
        "id": chat.id,
        "title": chat.title,
        "created_at": chat.created_at,
        "updated_at": chat.updated_at,
        "messages": [MsgResp.from_message(m) for m in chat.messages],
    }


@router.patch("/{chat_id}")
async def rename_chat(
    chat_id: int,
    data: dict,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(AuthService.get_current_user_dependency),
    db: Session = Depends(get_db),
):
    """채팅 이름 변경"""
    chat = service.get_chat(chat_id, current_user.id)
    if not chat:
        raise HTTPException(status_code=404, detail="채팅을 찾을 수 없습니다.")
    title = data.get("title", "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="제목을 입력해주세요.")
    chat.title = title
    db.commit()
    return {"id": chat.id, "title": chat.title}


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(
    chat_id: int,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(AuthService.get_current_user_dependency)
):
    """채팅 삭제"""
    success = service.delete_chat(chat_id, current_user.id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="채팅을 찾을 수 없습니다."
        )


@router.post("/{chat_id}/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def add_message(
    chat_id: int,
    message_data: MessageCreate,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(AuthService.get_current_user_dependency)
):
    """채팅에 메시지 추가"""
    chat = service.get_chat(chat_id, current_user.id)

    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="채팅을 찾을 수 없습니다."
        )

    message = service.add_message(
        chat_id=chat_id,
        role="user",
        content=message_data.content,
        message_type=message_data.message_type.value
    )

    return message


@router.post("/message", response_model=ChatMessageResponse)
async def send_chat_message(
    message: str = Form(""),
    session_id: Optional[str] = Form(None),
    analysis_type: str = Form("fto"),
    context: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(AuthService.get_current_user_dependency)
):
    """
    프론트엔드 채팅 인터페이스용 메시지 API
    - FTO 분석: RAG 파이프라인(ChromaDB + vLLM) 호출 → analyses 테이블 저장
    - 폴백: vLLM 직접 호출
    """
    chat_service = ChatService(db)

    # session_id 처리
    chat_id = None
    if session_id and session_id.strip() and session_id not in ("null", "undefined", ""):
        try:
            chat_id = int(session_id)
            chat = chat_service.get_chat(chat_id, current_user.id)
            if not chat:
                chat_id = None
        except (ValueError, TypeError):
            chat_id = None

    if not chat_id:
        title = message[:30] + "..." if len(message) > 30 else message
        chat = chat_service.create_chat(current_user.id, title)
        chat_id = chat.id

    # 사용자 메시지 DB 저장 (message_id를 captures해야 analysis FK에 사용)
    user_msg = chat_service.add_message(
        chat_id=chat_id,
        role="user",
        content=message,
        message_type="text"
    )

    analysis_id = None
    analysis_complete = False
    response_message = ""

    # ── FTO 분석: RAG 파이프라인 ──────────────────────────────────
    if analysis_type == "fto" and message.strip():
        start_time = time.time()
        try:
            from rag.backend_adapter import analyze_product
            from app.models.analysis import Analysis, InputTypeEnum, RiskLevelEnum as ModelRiskLevel

            # 대화 히스토리 조회 (멀티턴 지원)
            history_messages = []
            if chat_id:
                chat_with_messages = chat_service.get_chat(chat_id, current_user.id)
                if chat_with_messages and hasattr(chat_with_messages, 'messages'):
                    for msg in list(chat_with_messages.messages)[-10:]:  # 최근 10개만
                        role = str(msg.role.value) if hasattr(msg.role, 'value') else str(msg.role)
                        if role in ("user", "assistant"):
                            history_messages.append({"role": role, "content": msg.content})

            rag_result = await asyncio.to_thread(analyze_product, message, 10, True, history_messages)
            fto_result = rag_result.get("fto_result", {})
            fto_opinion = fto_result.get("fto_opinion", "")
            patent_analyses = fto_result.get("patent_analyses", [])

            # risk_level 결정 (라벨 기반)
            labels = [p.get("label", "") for p in patent_analyses]
            if any(l == "침해" for l in labels):
                risk_val = "high"
            elif any(l in ("침해_전문가", "애매") for l in labels):
                risk_val = "medium"
            else:
                risk_val = "low"

            response_message = fto_opinion or "분석이 완료되었습니다. 결과 페이지에서 상세 내용을 확인하세요."

            # analyses 테이블에 저장
            elapsed_ms = int((time.time() - start_time) * 1000)
            analysis_obj = Analysis(
                message_id=user_msg.id,
                input_type=InputTypeEnum.text,
                risk_level=ModelRiskLevel(risk_val),
                result_json=rag_result,
                model_used=VLLM_MODEL,
                processing_time_ms=elapsed_ms,
            )
            db.add(analysis_obj)
            db.commit()
            db.refresh(analysis_obj)

            analysis_id = analysis_obj.id
            analysis_complete = True

        except Exception as e:
            # RAG 실패 시 vLLM 직접 호출 폴백
            response_message = await asyncio.to_thread(_call_vllm_fallback, db, chat_id, current_user.id, chat_service, e)

    else:
        # design 분석 또는 analysis_type이 fto가 아닌 경우: vLLM 직접 호출
        response_message = await asyncio.to_thread(_call_vllm_fallback, db, chat_id, current_user.id, chat_service, None)

    # 어시스턴트 응답 DB 저장
    chat_service.add_message(
        chat_id=chat_id,
        role="assistant",
        content=response_message,
        message_type="text"
    )

    return ChatMessageResponse(
        message=response_message,
        session_id=chat_id,
        context=None,
        analysis_complete=analysis_complete,
        analysis_id=analysis_id
    )


def _call_vllm_fallback(db, chat_id: int, user_id: int, chat_service: "ChatService", err) -> str:
    """RAG 실패 또는 design 분석 시 vLLM 직접 호출 폴백."""
    if err:
        print(f"[RAG 폴백] RAG 파이프라인 오류: {err}")

    # 대화 히스토리 불러오기
    from app.services.chat_service import ChatService as CS
    chat = chat_service.get_chat(chat_id, user_id)
    history = []
    if chat and hasattr(chat, "messages"):
        for msg in list(chat.messages)[-20:]:
            if msg.role in ("user", "assistant"):
                history.append({"role": str(msg.role.value) if hasattr(msg.role, 'value') else str(msg.role),
                                 "content": msg.content})

    messages_payload = [{"role": "system", "content": SYSTEM_PROMPT}] + history

    # 1순위: vLLM (RunPod 서버리스)
    try:
        api_key = RUNPOD_API_KEY if RUNPOD_API_KEY else "dummy"
        client = OpenAI(base_url=VLLM_BASE_URL, api_key=api_key, timeout=300)
        resp = client.chat.completions.create(
            model=VLLM_MODEL,
            messages=messages_payload,
            max_tokens=2048,
            temperature=0.1,
        )
        return resp.choices[0].message.content
    except Exception as vllm_err:
        print(f"[vLLM 폴백] RunPod 서버리스 호출 실패: {vllm_err}")

    # GPT 폴백 (보안 정책: 비활성화 — 외부 API로 데이터 유출 방지)
    # openai_key = os.getenv("OPENAI_API_KEY", "")
    # if openai_key:
    #     try:
    #         client = OpenAI(api_key=openai_key, timeout=60)
    #         resp = client.chat.completions.create(
    #             model="gpt-4o-mini",
    #             messages=messages_payload,
    #             max_tokens=2048,
    #             temperature=0.1,
    #         )
    #         return resp.choices[0].message.content
    #     except Exception as gpt_err:
    #         return f"모델 호출 중 오류가 발생했습니다 (vLLM + GPT 모두 실패): {str(gpt_err)}"

    return "모델 서버에 연결할 수 없습니다. RunPod 설정(.env)을 확인하세요."


# ==================== 단계별 분석 API ====================

class SearchResultItem(BaseModel):
    patent_id: str
    score: float
    metadata: dict

class SearchResponse(BaseModel):
    session_id: int
    message_id: int
    search_token: str
    search_results: list[SearchResultItem]

class PatentAnalysisResponse(BaseModel):
    patent_id: str
    patent_index: int
    label: str
    comparisons: list[dict]
    analysis_text: str
    conclusion_text: str
    raw_output: str
    metadata: dict

class FinalizeResponse(BaseModel):
    analysis_id: int
    session_id: int
    risk_level: str


@router.post("/warmup")
async def warmup_patent():
    """특허 분석 워밍업: RAG 모델 + RunPod sLLM 미리 로드."""
    results = {}

    # 1. RAG 컴포넌트 로드 (임베딩 모델, ChromaDB, BM25)
    try:
        def _load_rag():
            from rag.search.retriever import _get_model, _get_collection, _load_sparse_index
            _get_model()
            _get_collection()
            _load_sparse_index()
        await asyncio.to_thread(_load_rag)
        results["rag"] = "ok"
    except Exception as e:
        results["rag"] = f"fail: {e}"
        logger.warning(f"[워밍업] RAG 로드 실패: {e}")

    # 2. RunPod sLLM 워밍업 (최소 요청으로 워커 깨우기)
    try:
        api_key = RUNPOD_API_KEY if RUNPOD_API_KEY else "dummy"
        client = OpenAI(base_url=VLLM_BASE_URL, api_key=api_key, timeout=30)
        resp = await asyncio.to_thread(
            lambda: client.chat.completions.create(
                model=VLLM_MODEL,
                messages=[{"role": "user", "content": "test"}],
                max_tokens=1,
            )
        )
        results["sllm"] = "ok"
    except Exception as e:
        results["sllm"] = f"warming: {e}"

    logger.info(f"[워밍업] 특허: {results}")
    return results


@router.post("/search", response_model=SearchResponse)
async def search_patents(
    message: str = Form(""),
    session_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(AuthService.get_current_user_dependency),
):
    """Phase 1: RAG 검색만 수행하여 TOP 10 특허 반환."""
    chat_service = ChatService(db)

    # 세션 처리 (기존 로직 재사용)
    chat_id = None
    if session_id and session_id.strip() and session_id not in ("null", "undefined", ""):
        try:
            chat_id = int(session_id)
            chat = chat_service.get_chat(chat_id, current_user.id)
            if not chat:
                chat_id = None
        except (ValueError, TypeError):
            chat_id = None

    if not chat_id:
        title = message[:30] + "..." if len(message) > 30 else message
        chat = chat_service.create_chat(current_user.id, title)
        chat_id = chat.id

    # 사용자 메시지 저장
    user_msg = chat_service.add_message(
        chat_id=chat_id, role="user", content=message, message_type="text"
    )

    # 사용자 원본 질문 로깅
    logger.info(f"[사용자 질문] {message}")

    # 후속 질문 감지 → 쿼리 재작성
    search_query = message
    t0 = time.time()
    chat_with_msgs = chat_service.get_chat(chat_id, current_user.id)
    if chat_with_msgs and hasattr(chat_with_msgs, 'messages'):
        prev_messages = [m for m in list(chat_with_msgs.messages) if m.id != user_msg.id]
        if len(prev_messages) >= 2:  # 이전 대화가 2개 이상이면 후속 질문
            history = []
            for m in prev_messages[-6:]:
                role = str(m.role.value) if hasattr(m.role, 'value') else str(m.role)
                if role in ("user", "assistant"):
                    history.append({"role": role, "content": m.content})
            if history:
                from rag.backend_adapter import rewrite_query
                t_rw = time.time()
                search_query = await asyncio.to_thread(rewrite_query, history, message, True)
                logger.info(f"[검색] 쿼리 재작성 {time.time()-t_rw:.2f}s | 원본: {message} → 재작성: {search_query}")

    # RAG 검색
    from rag.backend_adapter import search_only
    t_search = time.time()
    search_results = await asyncio.to_thread(search_only, search_query, 10, True)
    logger.info(f"[검색] RAG 검색 {time.time()-t_search:.2f}s | {len(search_results)}건 | 쿼리: {search_query}")

    # sLLM 워커 keep-alive 시작 (분석 중 cold start 방지)
    from app.utils.runpod_keepalive import start_keepalive
    start_keepalive()

    # 캐시에 저장 (message_id를 키로)
    from app.utils.search_cache import store as cache_store
    cache_key = str(user_msg.id)
    cache_store(cache_key, {
        "search_results": search_results,
        "user_query": search_query,
        "chat_id": chat_id,
        "message_id": user_msg.id,
    })

    # 프론트에 전달할 간소화된 결과
    items = []
    for r in search_results:
        meta = r.get("metadata", {})
        items.append(SearchResultItem(
            patent_id=r.get("patent_id", ""),
            score=r.get("score", 0.0),
            metadata={
                "apply_num": meta.get("apply_num", ""),
                "regit_num": meta.get("regit_num", ""),
                "invention_title": meta.get("invention_title", ""),
                "register_status": meta.get("register_status", ""),
                "applicant": meta.get("applicant", ""),
                "application_date": meta.get("application_date", ""),
                "register_date": meta.get("register_date", ""),
            },
        ))

    return SearchResponse(
        session_id=chat_id,
        message_id=user_msg.id,
        search_token=cache_key,
        search_results=items,
    )


@router.post("/analyze-from-history", response_model=PatentAnalysisResponse)
async def analyze_from_history(
    analysis_id: int = Form(0),
    patent_index: int = Form(0),
    db: Session = Depends(get_db),
    current_user: User = Depends(AuthService.get_current_user_dependency),
):
    """이전 분석의 search_results를 사용하여 추가 특허 분석 (히스토리 재분석)."""
    from app.models.analysis import Analysis

    analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
    if not analysis:
        raise HTTPException(status_code=404, detail="분석 결과를 찾을 수 없습니다.")

    result_json = analysis.result_json or {}
    search_results = result_json.get("search_results", [])
    user_query = result_json.get("query", "")

    if patent_index < 0 or patent_index >= len(search_results):
        raise HTTPException(status_code=400, detail=f"patent_index {patent_index}가 범위를 벗어났습니다.")

    from rag.backend_adapter import analyze_single_patent
    t_analyze = time.time()
    result = await asyncio.to_thread(analyze_single_patent, search_results[patent_index], user_query, True)
    result["patent_index"] = patent_index
    logger.info(f"[분석-히스토리] 특허#{patent_index} {result.get('patent_id','')} {time.time()-t_analyze:.2f}s | label={result.get('label','')}")

    # result_json에 새 분석 결과 추가 저장
    fto_result = result_json.setdefault("fto_result", {})
    patent_analyses = fto_result.setdefault("patent_analyses", [])
    # 기존 동일 index 분석 제거 후 추가
    patent_analyses = [a for a in patent_analyses if a.get("patent_index") != patent_index]
    patent_analyses.append(result)
    fto_result["patent_analyses"] = patent_analyses
    analysis.result_json = result_json
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(analysis, "result_json")
    db.commit()

    return PatentAnalysisResponse(
        patent_id=result.get("patent_id", ""),
        patent_index=patent_index,
        label=result.get("label", ""),
        comparisons=result.get("comparisons", []),
        analysis_text=result.get("analysis_text", ""),
        conclusion_text=result.get("conclusion_text", ""),
        raw_output=result.get("raw_output", ""),
        metadata=result.get("metadata", {}),
    )


@router.post("/analyze-patent", response_model=PatentAnalysisResponse)
async def analyze_single_patent_endpoint(
    search_token: str = Form(""),
    patent_index: int = Form(0),
    db: Session = Depends(get_db),
    current_user: User = Depends(AuthService.get_current_user_dependency),
):
    """Phase 2: 단일 특허 sLLM 분석. 프론트에서 0, 1, 2 순서로 호출."""
    from app.utils.search_cache import get as cache_get

    cached = cache_get(search_token)
    if not cached:
        raise HTTPException(status_code=404, detail="검색 결과가 만료되었습니다. 다시 검색해주세요.")

    search_results = cached["search_results"]
    user_query = cached["user_query"]

    if patent_index < 0 or patent_index >= len(search_results):
        raise HTTPException(status_code=400, detail=f"patent_index {patent_index}가 범위를 벗어났습니다.")

    from rag.backend_adapter import analyze_single_patent
    t_analyze = time.time()
    result = await asyncio.to_thread(analyze_single_patent, search_results[patent_index], user_query, True)
    logger.info(f"[분석] 특허#{patent_index} {result.get('patent_id','')} {time.time()-t_analyze:.2f}s | label={result.get('label','')}")

    return PatentAnalysisResponse(
        patent_id=result.get("patent_id", ""),
        patent_index=patent_index,
        label=result.get("label", ""),
        comparisons=result.get("comparisons", []),
        analysis_text=result.get("analysis_text", ""),
        conclusion_text=result.get("conclusion_text", ""),
        raw_output=result.get("raw_output", ""),
        metadata=result.get("metadata", {}),
    )


@router.post("/finalize", response_model=FinalizeResponse)
async def finalize_analysis(
    search_token: str = Form(""),
    patent_analyses_json: str = Form("[]"),
    db: Session = Depends(get_db),
    current_user: User = Depends(AuthService.get_current_user_dependency),
):
    """Phase 3: 분석 결과를 analyses 테이블에 저장."""
    from app.utils.runpod_keepalive import stop_keepalive
    stop_keepalive()

    from app.utils.search_cache import get as cache_get, delete as cache_delete
    from app.models.analysis import Analysis, InputTypeEnum, RiskLevelEnum as ModelRiskLevel

    cached = cache_get(search_token)
    if not cached:
        raise HTTPException(status_code=404, detail="검색 결과가 만료되었습니다.")

    search_results = cached["search_results"]
    message_id = cached["message_id"]
    chat_id = cached["chat_id"]

    patent_analyses = json.loads(patent_analyses_json)

    # risk_level 결정
    labels = [p.get("label", "") for p in patent_analyses]
    if any(l == "침해" for l in labels):
        risk_val = "high"
    elif any(l in ("침해_전문가", "애매") for l in labels):
        risk_val = "medium"
    else:
        risk_val = "low"

    # 기존 analyze_product() 형식과 동일한 result_json 구성
    rag_result = {
        "query": cached["user_query"],
        "search_results": search_results,
        "fto_result": {
            "patent_analyses": patent_analyses,
            "fto_opinion": "",
            "raw_output": "",
        },
    }

    analysis_obj = Analysis(
        message_id=message_id,
        input_type=InputTypeEnum.text,
        risk_level=ModelRiskLevel(risk_val),
        result_json=rag_result,
        model_used=VLLM_MODEL,
        processing_time_ms=0,
    )
    db.add(analysis_obj)
    db.commit()
    db.refresh(analysis_obj)

    # 어시스턴트 응답 저장
    chat_service = ChatService(db)
    chat_service.add_message(
        chat_id=chat_id,
        role="assistant",
        content="FTO 분석이 완료되었습니다.",
        message_type="text",
    )

    cache_delete(search_token)

    return FinalizeResponse(
        analysis_id=analysis_obj.id,
        session_id=chat_id,
        risk_level=risk_val,
    )
