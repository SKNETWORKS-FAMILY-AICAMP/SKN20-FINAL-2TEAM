from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List
from enum import Enum


class RiskLevelEnum(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class MatchEnum(str, Enum):
    match = "대응"
    no_match = "미대응"
    uncertain = "판단불가"


class AnalysisTypeEnum(str, Enum):
    fto = "fto"
    design = "design"


class ComparisonItem(BaseModel):
    patent_element: str
    user_product_element: Optional[str]
    match: MatchEnum


# ==================== 프론트엔드 요청 형식 ====================

class TextAnalysisRequest(BaseModel):
    """프론트엔드 텍스트 분석 요청"""
    description: str
    type: AnalysisTypeEnum = AnalysisTypeEnum.fto
    chat_id: Optional[int] = None  # 선택적 - 없으면 새 채팅 생성


class ImageAnalysisRequest(BaseModel):
    """프론트엔드 이미지 분석 요청"""
    image_url: str
    description: Optional[str] = None
    type: AnalysisTypeEnum = AnalysisTypeEnum.design
    chat_id: Optional[int] = None  # 선택적


# ==================== 응답 형식 ====================

class AnalysisResultJson(BaseModel):
    regit_num: str
    comparisons: List[ComparisonItem]
    risk_level: RiskLevelEnum
    decision_reason: str


class AnalysisResponse(BaseModel):
    """프론트엔드 응답 형식"""
    analysis_id: int
    input_type: str
    risk_level: Optional[str] = None
    result_json: Optional[dict] = None
    model_used: Optional[str] = None
    processing_time_ms: Optional[int] = None
    created_at: datetime

    # 포맷된 응답 (테이블 형식)
    formatted_response: Optional[str] = None

    class Config:
        from_attributes = True


class KeywordResponse(BaseModel):
    keyword: str
    importance: Optional[float]

    class Config:
        from_attributes = True


class ClaimMatchResponse(BaseModel):
    claim_id: int
    patent_regit_num: str
    claim_text: str
    rag_score: Optional[float]
    rerank_score: Optional[float]
    match_result: Optional[str]
    rank: Optional[int]

    class Config:
        from_attributes = True


class ImageMatchResponse(BaseModel):
    design_patent_id: int
    regit_num: str
    title: str
    rag_score: Optional[float]
    model_score: Optional[float]
    is_similar: Optional[bool]
    rank: Optional[int]

    class Config:
        from_attributes = True
