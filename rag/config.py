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
for _env_candidate in [_rag_dir.parent / ".env", _rag_dir.parent / "backend" / ".env", _rag_dir.parent.parent / ".env"]:
    if _env_candidate.exists():
        load_dotenv(_env_candidate)
        break

# ── 경로 ──────────────────────────────────────────────
RAG_DIR = _rag_dir
PROJECT_DIR = RAG_DIR.parent                  # SKN20-FINAL-2TEAM
DATA_DIR = RAG_DIR / "data"
INDEX_DIR = RAG_DIR / "index"
CHROMA_DIR = PROJECT_DIR / "data" / "chroma-patent"  # data/chroma-patent/ (Docker/EC2 공유)
SPARSE_INDEX_DIR = INDEX_DIR / "bm25_index"
CLAIM_KEYWORDS_SQLITE_PATH = INDEX_DIR / "claim_keywords.sqlite"
PARENT_DB_PATH = INDEX_DIR / "parent_store" / "parents.sqlite"

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

# ── 키워드 추출 상수 (filter.py, tokenizer.py 공용) ──────
# regex 패턴은 문자열로 저장, 사용처에서 re.compile
# ※ 수정 시 filter.py와 tokenizer.py 양쪽에 반영됨 (단일 소스)
JOSA_PATTERN = r"(을|를|이|가|은|는|의|에|로|와|과)$"
EOMI_PATTERN = (
    r"(으로부터|포함하는|구성되는|구성된|선택된|되는|하는|된|하여|으로|에서|이며|이고"
    r"|시키고|시켜|시키|시킨|시키지|하고|으로서|하기|하며|되고"
    # v2 추가: 로부터, 에게
    r"|로부터|에게"
    # v2 추가: ~거나 계열 (긴 패턴 우선)
    r"|시키거나|하거나|되거나|거나"
    # v2 추가: ~하되, ~하지, ~되지, ~하지만
    r"|하되|하지만|하지|되지"
    # v2 추가: ~도록 계열
    r"|시키도록|하도록|되도록|도록"
    # v2 추가: ~면서 계열
    r"|하면서|되면서"
    # v2 추가: ~으로써 계열 (긴 패턴 우선)
    r"|함으로써|됨으로써|으로써"
    # v2 추가: 시키 계열 확장
    r"|시키기|시킬|시키며|시켜서|시키고자|시킨다|시키는|시킴"
    # v3 추가: 로서, 된다, 하게, 이다, 한다, 으며
    r"|로서|된다|하게|이다|한다|으며"
    # v4 추가: 되며, 인지
    r"|되며|인지"
    r")$"
)
SPECIAL_CHARS_PATTERN = r"[().,;:!?\[\]{}\"\'/±]"
CLAIM_PREFIX_PATTERNS = [
    r"제\s*\d+\s*항에\s*있어서\s*[,.]?\s*",
    r"\d+\s*항에\s*있어서\s*[,.]?\s*",
    r"제\s*\d+\s*항\s*내지\s*제\s*\d+\s*항",
    r"제\s*\d+\s*항\s*또는\s*제\s*\d+\s*항",
    r"어느\s*한\s*항에\s*있어서\s*[,.]?\s*",
]
NOISE_PATTERNS = [
    r"^제\s*\d+\s*항?$",
    r"^\d+\s*항$",
    r"^제?\s*\d+\s*항에$",
    r"^\d+[a-z]?$",
    r"^[0-9.]+$",
    r"^\d+중량",
    r"^[\d.~∼\-]+중량",      # 40~70중량%, 0.1-5중량%
    r"^\d+%$",
    r"^-?\d+℃$",
    r"^[\d.~∼\-]+℃",           # 30℃인, 266℃에서, 15-25℃인
    r"^\d+°",                   # 1°, 5°2θ에서
    r"^\d+분$",
    r"^\d+시간$",
    r"^\d+rpm$",
    r"^\d+대\d+$",
    r"^[\d./~∼%\-]+$",
    r"^-?\d+[~∼]-?\d+$",
    r"^\d+[x×]\d+$",
    r"^\d+wt%$",
    r"^\d+t%$",
    r"^\d+배$",
    r"^\d+단계$",
    r"^제?\d+집단$",
    r"^[RC]\d+$",
    r"^C\d+~?C?\d*$",
    r"^[a-zA-Z]\d*[a-zA-Z]\d*[a-zA-Z]?$",
    # 또는+알파벳/숫자 (/ 분리 후 남는 잔여)
    r"^또는[a-zA-Z0-9]",
    # 숫자+단위 추가
    r"^\d+μm$",
    r"^\d+nm$",
    r"^\d+mm$",
    # 오류 토큰
    r"^및[a-z]$",
    r"^\d+이다$",
    r"^\d+인$",
    r"^\d+종$",
    r"^\d+개$",
    r"^\d+회$",
    r"^\d+차$",
    r"^\d+일$",
]
STOPWORDS = {
    "본", "것", "및", "또는", "관한", "특히", "상기",
    "그", "이", "수", "등", "더", "각", "해당",
    "것이다", "것으로서", "것으로써", "것인", "의한", "위한",
    "있다", "된다", "한다", "않", "있", "없", "됨", "함",
    "통한", "대한", "따른", "의할", "대해", "여기서",
    "더욱", "보다", "또", "매우", "가장", "다시",
    "하기", "상기식", "특징", "포함", "함유", "발명",
    "포함하는", "구성된", "있어서",
    "중량", "중량부", "중량%", "중량비", "함량", "비율", "농도",
    "몰비", "부피비", "범위", "내지", "이상", "이하", "미만", "초과",
    "g", "mg", "kg", "ml", "mL", "L", "wt%", "w/v%",
    "μm", "nm", "mm", "cm", "m",
    "℃", "°C", "°F", "도",
    "rpm", "pH",
    "회", "분", "초", "시간", "동안",
    "사용", "이용",
    "어느", "하나", "함께", "이루어진", "선택", "적어도",
    "가능한", "있으며", "나타내어질",
    "함유함", "포함함", "포함됨", "함유한",
    "동일한", "상이한", "특정", "최종",
    "의해", "각각", "이들", "추가", "청구항", "및/또",
    "독립적", "임의", "다음", "표시", "관련",
    # v2 추가: 형식어/부정어
    "이루어지", "경우", "통해", "이상인", "나타내",
    "않고", "있도록",
    # v3 추가: 형식어/부사/접속
    "있고", "갖고", "위해", "들어", "따라",
    "다른", "전체", "부분", "사이",
    "제시", "제공", "수행", "기재", "수득", "비교",
    "바람직", "허용가능한", "하나인",
    # v4 추가: 형식어/부사
    "여기", "실질적", "유사한", "완전히", "아닌",
    "의해서", "항중", "한항", "이하인", "미만인",
}

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
SLLM_MODEL_PATH = ""

# ── 필터링 ───────────────────────────────────────────
ESTOPPEL_ENABLED = True         # 금반언 처리 활성화 (삭제된 청구항 표시)
ALLOWED_STATUSES = {"등록", "공개"}   # 허용할 행정상태 (이외 소멸/거절/취하 등 제외)
MIN_SCORE = 0.010               # RRF 최소 점수 (이하면 노이즈 제거). (0.2,0.8) 가중치 기준 재조정값

# ── 사전필터링 ─────────────────────────────────────────
PREFILTER_MAX_CHUNKS = 1000     # 사전필터링 후 리트리버에 전달할 최대 청크 수

# ── 리소스 관리 (Phase 3) ─────────────────────────────
CHECKPOINT_PATH    = INDEX_DIR / "dense_checkpoint.json"
VRAM_TARGET_USAGE  = 0.85     # VRAM 85% 목표 활용
VRAM_DANGER_USAGE  = 0.92     # 92% 초과 시 배치 축소
RAM_DANGER_USAGE   = 0.90     # RAM 90% 초과 시 GC
EMBED_BS_MIN       = 1        # 최소 encode 배치 사이즈
EMBED_BS_MAX       = 512      # 최대 encode 배치 사이즈 (RTX 5090 32GB)
CHECKPOINT_INTERVAL = 2000    # 체크포인트 저장 간격 (청크 수)
PROCESSED_FILES_PATH = INDEX_DIR / "processed_files.json"

# ── Generation (G 모듈) ─────────────────────────────
# RunPod 서버리스 설정
RUNPOD_API_KEY = os.environ.get("RUNPOD_API_KEY", "")
RUNPOD_TEXT_BASE_URL = os.environ.get("RUNPOD_TEXT_BASE_URL", "")
RUNPOD_DESIGN_BASE_URL = os.environ.get("RUNPOD_DESIGN_BASE_URL", "")

# vLLM 설정 (RunPod 서버리스 또는 로컬)
VLLM_API_URL = os.environ.get("RUNPOD_PATENT_BASE_URL") or os.environ.get("VLLM_API_URL") or os.environ.get("VLLM_BASE_URL", "")
VLLM_MODEL_NAME = os.environ.get("PATENT_VLLM_MODEL", "itsbini/qwen2.5-14b-fto-merged")
VLLM_TIMEOUT = 600  # 서버리스 Cold Start + 추론 고려하여 10분

GPT_FALLBACK_MODEL = "gpt-4o-mini"
GPT_TIMEOUT = 60

GENERATE_MAX_TOKENS = 4096
GENERATE_TEMPERATURE = 0
GENERATE_REPETITION_PENALTY = 1.1  # 반복 루프 방지
GENERATE_INPUT_N = 5              # LLM에 전달할 특허 수
GENERATE_OUTPUT_N = 3             # LLM이 FTO 관점으로 선별할 특허 수
GENERATE_TOP_N = 3                # (레거시) sLLM 개별 분석용 — 추후 삭제
