import os
from pathlib import Path
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# 기본 경로 설정 (상대 경로 사용으로 이식성 확보)
BASE_DIR = Path(__file__).parent

# 셀럽 코디 이미지 폴더명 (변경 시 여기만 수정)
RAG_IMAGE_DIR_NAME = "RAG"
RAG_IMAGE_DIR = BASE_DIR / RAG_IMAGE_DIR_NAME

CHROMA_DB_DIR = BASE_DIR / "chroma_db"

# OpenAI 설정 (추천 메시지 생성용)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Korean CLIP 모델 설정
# 한국어 특화 CLIP 모델 (이미지 직접 임베딩)
CLIP_MODEL_NAME = "ViT-B-32"
CLIP_PRETRAINED = "laion2b_s34b_b79k"  # 다국어 지원 pretrained

# 임베딩 차원
EMBEDDING_DIM = 512

# LangChain Chroma 컬렉션 이름
COLLECTION_NAME = "celeb_fashion"

# 추천 설정
TOP_K_RESULTS = 3  # 상위 몇 개 추천할지

# 디바이스 설정 (GPU 있으면 cuda, 없으면 cpu)
import torch
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# 추천 메시지 생성용 프롬프트
RECOMMENDATION_PROMPT = """당신은 친근한 패션 스타일리스트입니다.

사용자가 업로드한 이미지와 유사한 셀럽 코디를 찾았습니다.
아래 정보를 바탕으로 사용자에게 코디 추천 메시지를 작성해주세요.

유사한 셀럽 코디:
{recommendations}

- 왜 이 코디들이 사용자의 스타일과 유사한지 설명
- 셀럽 코디에서 참고할 만한 스타일링 팁 제공
- 친근하고 자연스러운 톤으로 작성
- 한국어로 작성"""
