from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    # 데이터베이스 (MySQL)
    DATABASE_URL: str = "mysql+pymysql://root:newpassword123@localhost:3306/bini"

    # JWT 설정
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    # 파일 업로드
    UPLOAD_DIR: str = "uploads"
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB

    # 모델 설정
    SLLM_MODEL_PATH: str = "../bini/outputs/gemma3-1b-it-lora"

    # Hugging Face
    HF_TOKEN: str = ""

    class Config:
        env_file = ".env"
        extra = "allow"


settings = Settings()

# 업로드 디렉토리 생성
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
