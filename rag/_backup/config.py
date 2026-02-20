"""RAG 시스템 설정. 모든 모듈이 이 파일의 상수를 참조합니다.

경로, 모델, 검색 파라미터, 토크나이저, 필터링 설정을 한곳에서 관리합니다.
값을 바꾸면 전체 파이프라인에 반영됩니다.

사용처: 거의 모든 .py 파일에서 import
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# .env 파일 로드 (프로젝트 루트 → workspace 순으로 탐색)
# RAG 디렉토리 기준으로 상위 폴더를 탐색하며 .env 로드
_rag_dir = Path(__file__).parent
for _env_candidate in [_rag_dir.parent / ".env", _rag_dir.parent.parent / ".env", _rag_dir.parent.parent.parent / ".env"]:
    if _env_candidate.exists():
        load_dotenv(_env_candidate)
        break

# ── 경로 ──────────────────────────────────────────────
RAG_DIR = _rag_dir
PROJECT_DIR = RAG_DIR.parent.parent          # SKN20-FINAL-2TEAM
DATA_DIR = RAG_DIR / "data"
INDEX_DIR = RAG_DIR / "index"
CHROMA_DIR = INDEX_DIR / "chroma_db"
BM25_PATH = INDEX_DIR / "bm25.pkl"                      # 레거시 (rank_bm25 전체순회)
SPARSE_INDEX_DIR = INDEX_DIR / "bm25_index"              # 신규 inverted index 폴더
CHUNKS_PATH = INDEX_DIR / "chunks.json"
CLAIMS_DB_PATH = INDEX_DIR / "claims_db.json"
CLAIMS_SQLITE_PATH = INDEX_DIR / "claims_db.sqlite"

# ── 임베딩 모델 ──────────────────────────────────────
EMBED_MODEL = "nlpai-lab/KURE-v1"
EMBED_DIM = 1024
EMBED_BATCH_SIZE = 32
DENSE_MAX_CHARS = 4000          # dense_text 글자수 한계 (초과 시 슬라이딩 윈도우 분할)
CHROMA_COLLECTION = "patent_chunks"

# ── Sparse 엔진 ────────────────────────────────────────
BM25_K1 = 1.5
BM25_B = 0.75

# ── 검색 파라미터 ────────────────────────────────────
DENSE_TOP_K = 50
BM25_TOP_K = 50
RRF_K = 60
RRF_WEIGHTS = (0.2, 0.8)       # (dense, sparse) — rrf_sweep 결과 최적값
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
MULTI_QUERY_MODE = "rule"       # "rule"(regex) / "llm"(GPT) / "hybrid"(regex→LLM 폴백)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
SLLM_MODEL_PATH = ""

# ── 필터링 ───────────────────────────────────────────
ESTOPPEL_ENABLED = True         # 금반언 처리 활성화 (삭제된 청구항 표시)
REGISTERED_ONLY = True          # 등록 특허만 결과에 포함
MIN_SCORE = 0.010               # RRF 최소 점수 (이하면 노이즈 제거). (0.2,0.8) 가중치 기준 재조정값

# ── 사전필터링 ─────────────────────────────────────────
PREFILTER_MAX_CHUNKS = 1000     # 사전필터링 후 리트리버에 전달할 최대 청크 수

# ── 리소스 관리 (Phase 3) ─────────────────────────────
CHECKPOINT_PATH    = INDEX_DIR / "dense_checkpoint.json"
VRAM_TARGET_USAGE  = 0.85     # VRAM 85% 목표 활용
VRAM_DANGER_USAGE  = 0.92     # 92% 초과 시 배치 축소
RAM_DANGER_USAGE   = 0.90     # RAM 90% 초과 시 GC
EMBED_BS_MIN       = 1        # 최소 encode 배치 사이즈
EMBED_BS_MAX       = 512      # 최대 encode 배치 사이즈
CHECKPOINT_INTERVAL = 2000    # 체크포인트 저장 간격 (청크 수)
PROCESSED_FILES_PATH = INDEX_DIR / "processed_files.json"
