from typing import Optional
from sqlalchemy.orm import Session
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.database import get_db
from app.models.user import User
from app.schemas.user import UserCreate
from app.config import settings
from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    decode_access_token
)

security = HTTPBearer()


class AuthService:
    def __init__(self, db: Session):
        self.db = db

    def get_user_by_email(self, email: str) -> Optional[User]:
        """이메일로 사용자 조회"""
        return self.db.query(User).filter(User.email == email).first()

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """ID로 사용자 조회"""
        return self.db.query(User).filter(User.id == user_id).first()

    def create_user(self, user_data: UserCreate) -> User:
        """사용자 생성"""
        hashed_password = get_password_hash(user_data.password)

        user = User(
            email=user_data.email,
            password=hashed_password,
            name=user_data.name
        )

        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)

        return user

    def authenticate_user(self, email: str, password: str) -> Optional[User]:
        """사용자 인증"""
        user = self.get_user_by_email(email)

        if not user:
            return None

        if not verify_password(password, user.password):
            return None

        return user

    def create_token(self, user_id: int) -> str:
        """액세스 토큰 생성"""
        # JWT 표준: sub 클레임은 문자열이어야 함
        return create_access_token(data={"sub": str(user_id)})

    @staticmethod
    async def get_current_user_dependency(
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=not settings.DEV_BYPASS_AUTH)),
        db: Session = Depends(get_db)
    ) -> User:
        """현재 로그인된 사용자 의존성"""
        # 개발 모드: 토큰 없으면 더미 유저 반환
        if settings.DEV_BYPASS_AUTH and (credentials is None):
            dummy = User(id=0, email="dev@test.com", name="개발자")
            dummy.id = 0
            return dummy

        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="인증 정보가 유효하지 않습니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )

        token = credentials.credentials
        token_data = decode_access_token(token)

        if token_data is None or token_data.user_id is None:
            raise credentials_exception

        user = db.query(User).filter(User.id == token_data.user_id).first()

        if user is None:
            raise credentials_exception

        return user
