from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from app.database import get_db
from app.schemas.chat import ChatCreate, ChatResponse, ChatListResponse, MessageCreate, MessageResponse
from app.services.chat_service import ChatService
from app.services.auth_service import AuthService
from app.services.text_analyzer import TextAnalyzerService
from app.models.user import User
from app.utils.response_formatter import format_response

router = APIRouter()


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
    request: ChatMessageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(AuthService.get_current_user_dependency)
):
    """
    프론트엔드 채팅 인터페이스용 메시지 API

    - session_id가 없으면 새 채팅 생성
    - 메시지 분석 후 AI 응답 반환
    - 분석 완료 시 analysis_id 포함
    """
    chat_service = ChatService(db)

    # session_id(chat_id)가 없으면 새 채팅 생성
    if request.session_id:
        chat = chat_service.get_chat(request.session_id, current_user.id)
        if not chat:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="채팅을 찾을 수 없습니다."
            )
        chat_id = request.session_id
    else:
        # 새 채팅 생성
        title = request.message[:30] + "..." if len(request.message) > 30 else request.message
        chat = chat_service.create_chat(current_user.id, title)
        chat_id = chat.id

    # 사용자 메시지 저장
    user_message = chat_service.add_message(
        chat_id=chat_id,
        role="user",
        content=request.message,
        message_type="text"
    )

    # 컨텍스트 분석하여 응답 생성
    context = request.context or {}
    analysis_complete = False
    analysis_id = None
    response_message = ""

    # 간단한 대화 로직 (실제로는 LLM 연동)
    message_lower = request.message.lower()

    if "제품" in request.message or "정보" in request.message:
        response_message = "제품 정보를 확인했습니다. 출시 예정 국가와 제품의 주요 기능을 알려주시겠어요?"
        context["step"] = "product_info"

    elif "한국" in request.message or "대한민국" in request.message:
        response_message = "한국 시장을 타겟으로 하시는군요. 제품의 핵심 기능이나 구성 요소에 대해 좀 더 자세히 설명해주시겠어요?"
        context["country"] = "대한민국"
        context["step"] = "country_set"

    elif len(request.message) > 50:  # 상세 설명으로 판단
        # 분석 수행
        analyzer = TextAnalyzerService(db)
        analysis = analyzer.analyze(
            message_id=user_message.id,
            product_description=request.message
        )

        formatted = format_response(analysis.result_json) if analysis.result_json else "분석이 완료되었습니다."
        response_message = formatted
        analysis_complete = True
        analysis_id = analysis.id

    else:
        response_message = "질문을 잘 이해했습니다. 제품에 대해 좀 더 자세히 설명해주시면 특허 침해 리스크를 분석해드리겠습니다."

    # 어시스턴트 응답 저장
    chat_service.add_message(
        chat_id=chat_id,
        role="assistant",
        content=response_message,
        message_type="text"
    )

    return ChatMessageResponse(
        message=response_message,
        session_id=chat_id,
        context=context if context else None,
        analysis_complete=analysis_complete,
        analysis_id=analysis_id
    )
