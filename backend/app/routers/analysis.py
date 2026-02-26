from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.schemas.analysis import AnalysisResponse
from app.services.chat_service import ChatService
from app.services.auth_service import AuthService
from app.models.user import User
from app.utils.response_formatter import format_response

router = APIRouter()

# NOTE: /text, /image 엔드포인트는 chat.py의 RAG 파이프라인으로 대체됨.
# 디자인 분석은 design.py 라우터에서 처리됨.


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
