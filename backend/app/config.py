from pydantic_settings import BaseSettings
from typing import List
import os
from pathlib import Path

# 프로젝트 루트의 .env 파일을 단일 설정 파일로 사용
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_ENV_FILE = str(_PROJECT_ROOT / ".env")


class Settings(BaseSettings):
    # 데이터베이스 (MySQL)
    DATABASE_URL: str = "mysql+pymysql://root:newpassword123@localhost:3306/fto"

    # JWT 설정
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
        "null"  # file:// 프로토콜 지원
    ]

    # 파일 업로드
    UPLOAD_DIR: str = "uploads"
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB

    # 모델 설정 (HuggingFace API 사용)
    HF_MODEL_ID: str = "itsbini/qwen2.5-14b-fto"

    # 개발 모드 (배포 시 False로 변경!)
    DEV_BYPASS_AUTH: bool = False

    # Hugging Face
    HF_TOKEN: str = ""

    # vLLM 서버
    VLLM_BASE_URL: str = "http://localhost:8000/v1"
    VLLM_MODEL: str = "/workspace/qwen2.5-14b-fto-merged"

    # ChromaDB (EC2)
    CHROMA_HOST: str = ""
    CHROMA_PORT: int = 8001
    CHROMA_IMAGE_PORT: int = 8002

    # OpenAI GPT 폴백
    OPENAI_API_KEY: str = ""

    class Config:
        env_file = _ENV_FILE
        extra = "allow"


settings = Settings()

# 업로드 디렉토리 생성
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
