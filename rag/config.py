"""RAG 설정.

모든 설정을 한 곳에서 관리합니다.
"""
from pathlib import Path

# 경로
RAG_DIR = Path(__file__).parent
INDEX_DIR = RAG_DIR / "index"
CHROMA_DIR = INDEX_DIR / "chroma_db"
BM25_PATH = INDEX_DIR / "bm25.pkl"

# 임베딩 모델
EMBED_MODEL = "nlpai-lab/KURE-v1"
EMBED_DIM = 1024
CHROMA_COLLECTION = "patent_chunks"

# 검색 파라미터
DENSE_TOP_K = 50          # Dense 검색 결과 수
SPARSE_TOP_K = 50         # Sparse 검색 결과 수
FINAL_TOP_K = 10          # 최종 반환 수
RRF_K = 60                # RRF 파라미터
RRF_WEIGHT_DENSE = 0.4    # Dense 가중치
RRF_WEIGHT_SPARSE = 0.6   # Sparse 가중치

# 필터링
REGISTERED_ONLY = True    # 등록된 특허만 반환
ESTOPPEL_ENABLED = True   # 금반언 표시

# MySQL 연결 (backend와 동일)
DATABASE_URL = "mysql+pymysql://root:newpassword123@localhost:3306/fto"
