from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str
    remember_me: Optional[bool] = False


class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    created_at: datetime

    class Config:
        from_attributes = True


class UserInfo(BaseModel):
    """프론트엔드용 사용자 정보 (간소화)"""
    id: int
    email: str
    name: str

    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    """프론트엔드 로그인 응답 형식"""
    token: str
    user: UserInfo


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: Optional[int] = None
