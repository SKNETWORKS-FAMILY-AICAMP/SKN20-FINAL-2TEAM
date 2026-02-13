"""RAG 시스템 설정. 모든 모듈이 이 파일의 상수를 참조합니다.

경로, 모델, 검색 파라미터, 토크나이저, 필터링 설정을 한곳에서 관리합니다.
값을 바꾸면 전체 파이프라인에 반영됩니다.

사용처: 거의 모든 .py 파일에서 import
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# .env 파일 로드 (프로젝트 루트 → workspace 순으로 탐색)
_rag_dir = Path(__file__).parent
for _env_candidate in [_rag_dir.parent / ".env", _rag_dir.parent.parent / ".env"]:
    if _env_candidate.exists():
        load_dotenv(_env_candidate)
        break

# ── 경로 ──────────────────────────────────────────────
RAG_DIR = _rag_dir
PROJECT_DIR = RAG_DIR.parent.parent          # SKN20-FINAL-2TEAM
DATA_DIR = RAG_DIR / "data"
INDEX_DIR = RAG_DIR / "index"
CHROMA_DIR = INDEX_DIR / "chroma_db"
BM25_PATH = INDEX_DIR / "bm25.pkl"
CHUNKS_PATH = INDEX_DIR / "chunks.json"
CLAIMS_DB_PATH = INDEX_DIR / "claims_db.json"

# ── 임베딩 모델 ──────────────────────────────────────
EMBED_MODEL = "nlpai-lab/KURE-v1"
EMBED_DIM = 1024
EMBED_BATCH_SIZE = 32
DENSE_MAX_CHARS = 4000          # dense_text 글자수 한계 (배치 패딩 고려, KURE-v1 8192토큰)
CHROMA_COLLECTION = "patent_chunks"

# ── BM25 ──────────────────────────────────────────────
BM25_K1 = 1.5
BM25_B = 0.75

# ── 검색 파라미터 ────────────────────────────────────
DENSE_TOP_K = 50
BM25_TOP_K = 50
RRF_K = 60
RRF_WEIGHTS = (0.4, 0.6)       # (dense, sparse)
FINAL_TOP_K = 10

# ── 토크나이저 ───────────────────────────────────────
KIWI_TARGET_TAGS = {"NNG", "NNP", "SL"}    # 일반명사, 고유명사, 외래어

# ── Sparse 전처리 ────────────────────────────────────
SPARSE_LEGAL_STOPWORDS = [
    "에 있어서", "를 특징으로 하는", "을 특징으로 하는",
    "를 포함하는", "을 포함하는", "로 이루어진",
    "상기", "내지", "제1항", "제2항", "제3항", "제4항",
    "제5항", "제6항", "제7항", "제8항", "제9항", "제10항",
]
SPARSE_REMOVE_NUMBERS = True

# ── 멀티쿼리 ─────────────────────────────────────────
MULTI_QUERY_MODE = "rule"       # "rule" / "llm" / "hybrid"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
SLLM_MODEL_PATH = ""

# ── 필터링 ───────────────────────────────────────────
ESTOPPEL_ENABLED = True
REGISTERED_ONLY = True
