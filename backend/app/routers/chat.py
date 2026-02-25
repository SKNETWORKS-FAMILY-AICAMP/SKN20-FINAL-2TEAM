from fastapi import APIRouter, Depends, HTTPException, status, Form
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from openai import OpenAI
import os

from app.database import get_db
from app.schemas.chat import ChatCreate, ChatResponse, ChatListResponse, MessageCreate, MessageResponse
from app.services.chat_service import ChatService
from app.services.auth_service import AuthService
from app.models.user import User

router = APIRouter()

# vLLM 클라이언트
VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1")
VLLM_MODEL = os.getenv("VLLM_MODEL", "/workspace/qwen2.5-14b-fto-merged")

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


@router.get("/{chat_id}", response_model=ChatResponse)
async def get_chat(
    chat_id: int,
    service: ChatService = Depends(get_chat_service),
    current_user: User = Depends(AuthService.get_current_user_dependency)
):
    """채팅 상세 조회 (메시지 포함)"""
    chat = service.get_chat(chat_id, current_user.id)

    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="채팅을 찾을 수 없습니다."
        )

    return chat


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
    - FormData로 수신 (이미지 첨부 포함 가능)
    - 대화 히스토리를 DB에서 불러와 vLLM에 전달
    - vLLM(14B) 응답 반환
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

    # 사용자 메시지 DB 저장
    chat_service.add_message(
        chat_id=chat_id,
        role="user",
        content=message,
        message_type="text"
    )

    # 대화 히스토리 불러오기 (최근 20개)
    chat = chat_service.get_chat(chat_id, current_user.id)
    history = []
    if chat and hasattr(chat, "messages"):
        for msg in list(chat.messages)[-20:]:
            if msg.role in ("user", "assistant"):
                history.append({"role": msg.role, "content": msg.content})

    # vLLM 호출
    try:
        client = OpenAI(base_url=VLLM_BASE_URL, api_key="dummy", timeout=120)
        messages_payload = [{"role": "system", "content": SYSTEM_PROMPT}] + history
        resp = client.chat.completions.create(
            model=VLLM_MODEL,
            messages=messages_payload,
            max_tokens=2048,
            temperature=0.1,
        )
        response_message = resp.choices[0].message.content
    except Exception as e:
        response_message = f"모델 호출 중 오류가 발생했습니다: {str(e)}"

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
        analysis_complete=False,
        analysis_id=None
    )
