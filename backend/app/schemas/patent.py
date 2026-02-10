from pydantic import BaseModel
from datetime import datetime, date
from typing import Optional, List
from enum import Enum


class ClaimTypeEnum(str, Enum):
    independent = "independent"
    dependent = "dependent"


# ==================== 디자인 특허 ====================

class DesignPatentCreate(BaseModel):
    regit_num: str
    title: str
    locarno_class: Optional[str] = None
    applicant: Optional[str] = None
    image_path: Optional[str] = None
    filing_date: Optional[date] = None


class DesignPatentResponse(BaseModel):
    id: int
    regit_num: str
    title: str
    locarno_class: Optional[str]
    applicant: Optional[str]
    image_path: Optional[str]
    filing_date: Optional[date]
    created_at: datetime

    class Config:
        from_attributes = True


# ==================== 일반 특허 ====================

class ClaimCreate(BaseModel):
    claim_number: int
    claim_text: str
    claim_type: ClaimTypeEnum = ClaimTypeEnum.independent


class ClaimResponse(BaseModel):
    id: int
    claim_number: int
    claim_text: str
    claim_type: ClaimTypeEnum
    created_at: datetime

    class Config:
        from_attributes = True


class PatentCreate(BaseModel):
    regit_num: str
    title: str
    applicant: Optional[str] = None
    ipc_code: Optional[str] = None
    abstract: Optional[str] = None
    filing_date: Optional[date] = None
    claims: List[ClaimCreate] = []


class PatentResponse(BaseModel):
    id: int
    regit_num: str
    title: str
    applicant: Optional[str]
    ipc_code: Optional[str]
    abstract: Optional[str]
    filing_date: Optional[date]
    created_at: datetime
    claims: List[ClaimResponse] = []

    class Config:
        from_attributes = True
