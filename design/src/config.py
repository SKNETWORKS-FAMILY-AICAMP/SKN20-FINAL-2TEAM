"""디자인 분석 모듈 설정.

design/src/ 내 모든 모듈이 이 파일의 상수를 참조합니다.
환경변수는 .env 파일에서 자동 로드됩니다.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# .env 파일 탐색 (design/src → design → 프로젝트 루트 → backend 순)
_src_dir = Path(__file__).parent
for _env_candidate in [
    _src_dir / ".env",
    _src_dir.parent / ".env",
    _src_dir.parent.parent / ".env",
    _src_dir.parent.parent / "backend" / ".env",
]:
    if _env_candidate.exists():
        load_dotenv(_env_candidate)
        break

# ── 경로 ──────────────────────────────────────────────
DESIGN_DIR = _src_dir.parent                          # design/
PROJECT_DIR = DESIGN_DIR.parent                       # SKN20-FINAL-2TEAM/
CHROMA_DB_PATH = str(PROJECT_DIR / "data" / "chroma-design")  # data/chroma-design/ (Docker/EC2 공유)
IMAGES_DIR = str(DESIGN_DIR / "data" / "images")      # design/data/images/

# ── RunPod 서버리스 ───────────────────────────────────
RUNPOD_API_KEY = os.environ.get("RUNPOD_API_KEY", "")
RUNPOD_DESIGN_BASE_URL = os.environ.get(
    "RUNPOD_DESIGN_BASE_URL",
    "",  # 예: https://api.runpod.ai/v2/hmh882ms5azjye/openai/v1
)

# ── VLM 설정 ─────────────────────────────────────────
VLLM_MODEL_NAME = os.environ.get(
    "DESIGN_VLLM_MODEL",
    "Qwen/Qwen2.5-VL-7B-Instruct",
)
VLLM_TIMEOUT = 300  # 서버리스 Cold Start 고려 5분

# ── GPT 폴백 ─────────────────────────────────────────
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
GPT_FALLBACK_MODEL = "gpt-4o"

# ── 검색 파라미터 ────────────────────────────────────
N_RESULTS = 15              # 벡터DB 유사 디자인 검색 개수
RETRIEVAL_TOP_K = 50        # Dense 1차 검색 개수 (BM25 재랭킹 전)
TOP_K = 10                  # 최종 반환 개수
DENSE_WEIGHT = 0.7          # Dense 가중치 (BM25 = 1 - DENSE_WEIGHT)

# ── LLM 선택 ─────────────────────────────────────────
# RunPod 서버리스 URL이 설정되어 있으면 VLM, 아니면 GPT 폴백
USE_RUNPOD = bool(RUNPOD_DESIGN_BASE_URL and RUNPOD_API_KEY)
