from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.schemas.analysis import TextAnalysisRequest, ImageAnalysisRequest, AnalysisResponse
from app.services.text_analyzer import TextAnalyzerService
from app.services.image_analyzer import ImageAnalyzerService
from app.services.chat_service import ChatService
from app.services.auth_service import AuthService
from app.models.user import User
from app.utils.response_formatter import format_response

router = APIRouter()


@router.post("/text", response_model=AnalysisResponse)
async def analyze_text(
    request: TextAnalysisRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(AuthService.get_current_user_dependency)
):
    """
    텍스트 분석 API

    프론트엔드 요청: { description, type, chat_id? }
    """
    chat_service = ChatService(db)

    # chat_id가 없으면 새 채팅 생성
    if request.chat_id:
        chat = chat_service.get_chat(request.chat_id, current_user.id)
        if not chat:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="채팅을 찾을 수 없습니다."
            )
        chat_id = request.chat_id
    else:
        # 새 채팅 자동 생성
        title = request.description[:30] + "..." if len(request.description) > 30 else request.description
        chat = chat_service.create_chat(current_user.id, title)
        chat_id = chat.id

    # 사용자 메시지 저장
    user_message = chat_service.add_message(
        chat_id=chat_id,
        role="user",
        content=request.description,
        message_type="text"
    )

    # 텍스트 분석 수행
    analyzer = TextAnalyzerService(db)
    analysis = analyzer.analyze(
        message_id=user_message.id,
        product_description=request.description
    )

    # 어시스턴트 응답 저장
    formatted = format_response(analysis.result_json) if analysis.result_json else "분석 결과를 생성할 수 없습니다."

    chat_service.add_message(
        chat_id=chat_id,
        role="assistant",
        content=formatted,
        message_type="text"
    )

    # 프론트엔드 형식으로 응답
    return AnalysisResponse(
        analysis_id=analysis.id,
        input_type=analysis.input_type.value if analysis.input_type else "text",
        risk_level=analysis.risk_level.value if analysis.risk_level else None,
        result_json=analysis.result_json,
        model_used=analysis.model_used,
        processing_time_ms=analysis.processing_time_ms,
        created_at=analysis.created_at,
        formatted_response=formatted
    )


@router.post("/image", response_model=AnalysisResponse)
async def analyze_image(
    request: ImageAnalysisRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(AuthService.get_current_user_dependency)
):
    """
    이미지 분석 API (URL 기반)

    프론트엔드 요청: { image_url, description?, type, chat_id? }
    """
    chat_service = ChatService(db)

    # chat_id가 없으면 새 채팅 생성
    if request.chat_id:
        chat = chat_service.get_chat(request.chat_id, current_user.id)
        if not chat:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="채팅을 찾을 수 없습니다."
            )
        chat_id = request.chat_id
    else:
        # 새 채팅 자동 생성
        title = request.description[:30] if request.description else "이미지 분석"
        chat = chat_service.create_chat(current_user.id, title)
        chat_id = chat.id

    # 사용자 메시지 저장
    user_message = chat_service.add_message(
        chat_id=chat_id,
        role="user",
        content=f"[이미지 분석 요청] {request.image_url}",
        message_type="image"
    )

    # 이미지 분석 수행 (URL 기반)
    analyzer = ImageAnalyzerService(db)
    analysis = await analyzer.analyze_url(
        message_id=user_message.id,
        image_url=request.image_url,
        description=request.description
    )

    # 어시스턴트 응답 저장
    response_text = analysis.result_json.get("response", "이미지 분석 결과를 생성할 수 없습니다.") if analysis.result_json else "분석 결과를 생성할 수 없습니다."

    chat_service.add_message(
        chat_id=chat_id,
        role="assistant",
        content=response_text,
        message_type="text"
    )

    # 프론트엔드 형식으로 응답
    return AnalysisResponse(
        analysis_id=analysis.id,
        input_type=analysis.input_type.value if analysis.input_type else "image",
        risk_level=analysis.risk_level.value if analysis.risk_level else None,
        result_json=analysis.result_json,
        model_used=analysis.model_used,
        processing_time_ms=analysis.processing_time_ms,
        created_at=analysis.created_at,
        formatted_response=response_text
    )


@router.get("/{analysis_id}", response_model=AnalysisResponse)
async def get_analysis(
    analysis_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(AuthService.get_current_user_dependency)
):
    """분석 결과 조회"""
    from app.models.analysis import Analysis
    from app.models.chat import Message

    analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()

    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="분석 결과를 찾을 수 없습니다."
        )

    # 소유권 확인
    message = db.query(Message).filter(Message.id == analysis.message_id).first()
    if message:
        chat_service = ChatService(db)
        chat = chat_service.get_chat(message.chat_id, current_user.id)
        if not chat:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="접근 권한이 없습니다."
            )

    formatted = format_response(analysis.result_json) if analysis.result_json else None

    return AnalysisResponse(
        analysis_id=analysis.id,
        input_type=analysis.input_type.value if analysis.input_type else "text",
        risk_level=analysis.risk_level.value if analysis.risk_level else None,
        result_json=analysis.result_json,
        model_used=analysis.model_used,
        processing_time_ms=analysis.processing_time_ms,
        created_at=analysis.created_at,
        formatted_response=formatted
    )
