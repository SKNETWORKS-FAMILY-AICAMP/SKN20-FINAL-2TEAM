# 수정사항 6가지 반영 :
# 1. CLIP 임베딩 정규화 + metric 명시
# get_image_embedding()에서 L2 normalize 적용
# CHROMA_METRIC = "cosine" 상수로 명시하고, distance_to_similarity() 함수로 metric별 변환 지원

# 2. VLM JSON 파싱 안정화
# DesignAnalysis, ComparisonResult 등 Pydantic 스키마로 검증
# parse_json_safe()로 마크다운 코드블록 등 처리
# 파싱 실패 시 max_retries만큼 재시도, 최종 실패 시 raw fallback

# 3. 비용/속도 최적화
# MAX_CANDIDATES = 5로 VLM 호출 수 제한 (21회 → 7회 수준)
# DISTANCE_THRESHOLD로 비유사 후보 사전 제거
# 일괄 비교: 후보 전체를 1회 LLM 호출로 비교 (10회 → 1회)

# 4. VLM 키워드 rerank + 메타데이터 활용
# _keyword_rerank()로 물품명 키워드 매칭 시 미세 보너스 적용
# 필터링 후 거리순 정렬 보장 (sorted())

# 5. 코드 중복 제거 + 캐싱
# encode_image_to_data_url(), analyze_image_vlm() 함수화
# vlm_chain은 루프 밖에서 1회만 생성
# 파일 기반 VLM 캐시 (.vlm_cache/ 디렉토리)

# 6. 구조 정리
# 상수/스키마/유틸/기능별 섹션 분리
# main() 함수로 진입점 명확화


# 수정사항 (기존 6가지 + 추가 3가지):
# 7. ChromaDB nested dict 안전 처리
#    - status 필드가 dict/JSON string 혼용 → _parse_status()로 통일 처리
#    - _safe_meta()로 모든 메타데이터 필드 안전하게 접근
# 8. MPS(Mac) 디바이스 지원
#    - DEVICE 감지: cuda → mps → cpu 우선순위
# 9. Streamlit 연동을 위한 retrieve_similar_designs() 반환 구조 개선
#    - imagePath URL + 로컬 경로 모두 지원
#    - 반환값에 applicantName, agentName, designDescription 추가

"""
멀티스테이지 RAG + VLM 기반 디자인 FTO 비교분석 파이프라인

    [입력 이미지]
        ↓
    [VLM 분석] ← GPT-4O (구조화된 JSON, Pydantic 검증)
        ↓
    [CLIP 벡터 검색] → 유사 디자인 Top-K 추출
        ↓  필터: 자기 도면 제거 + 출원번호별 1개 + 거리 threshold + 거리순 정렬
        ↓  (선택) VLM 키워드 기반 메타데이터 rerank
        ↓
    [각 유사 디자인 VLM 분석] (캐싱 적용)
        ↓
    [비교 분석 LLM] — 후보 일괄 비교 (1회 호출)
        ↓
    [상세 리포트 생성]
"""

import base64
import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

import chromadb
import clip
import numpy as np
import torch
from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from PIL import Image
from pydantic import BaseModel, Field

load_dotenv()

if not os.environ.get("OPENAI_API_KEY"):
    raise ValueError("OPENAI_API_KEY 없음 — .env 확인!")

# ─────────────────────────────────────────────
# 0. 설정 상수
# ─────────────────────────────────────────────
CHROMA_DB_PATH  = "3차_테스트/chroma_db_v2"
COLLECTION_NAME = "design"
CHROMA_METRIC   = "cosine"  # "cosine" | "l2" | "ip"

CLIP_MODEL_NAME = "ViT-B/32"

# ── [수정 8] MPS(Mac Apple Silicon) 지원 추가 ──
DEVICE = (
    "cuda" if torch.cuda.is_available() else
    "mps"  if torch.backends.mps.is_available() else
    "cpu"
)

RETRIEVAL_TOP_K    = 10
MAX_CANDIDATES     = 5
DISTANCE_THRESHOLD = 0.95

VLM_CACHE_DIR = Path("./design/.vlm_cache")
VLM_CACHE_DIR.mkdir(exist_ok=True)

LLM_MODEL       = "gpt-4o"
LLM_TEMPERATURE = 0

# ─────────────────────────────────────────────
# 1. Pydantic 스키마 (VLM 출력 검증)
# ─────────────────────────────────────────────
class ShapeObservation(BaseModel):
    전체_실루엣: str
    몸체_형태:   str
    상부_구조:   str
    하부_형태:   str
    비례_관계:   str


class DesignAnalysis(BaseModel):
    물품:     str
    형상_관찰: ShapeObservation


class ComparisonItem(BaseModel):
    항목: str
    설명: str


class ComparisonResult(BaseModel):
    유사한_점:  list[ComparisonItem] = Field(default_factory=list)
    비유사한_점: list[ComparisonItem] = Field(default_factory=list)


class BatchComparisonEntry(BaseModel):
    출원번호:  str
    비교결과: ComparisonResult


# ─────────────────────────────────────────────
# 2. 프롬프트
# ─────────────────────────────────────────────
FEW_SHOT_CAPTIONING = """
당신의 임무는 제품 도면 이미지를 보고,
'실제로 도면에서 관찰되는 형상 요소'만을 단계적으로 기록하는 것입니다.

⚠️ 중요 규칙
- 비교, 평가, 유사/비유사 판단을 하지 마십시오.
- 일반적인 제품 특성이나 추측을 작성하지 마십시오.
- 도면에 명확히 보이지 않는 요소는 "관찰되지 않음"이라고 명시하십시오.
- 표현은 객관적 형상 중심으로 작성하십시오.

아래 사고 단계를 반드시 순서대로 수행하십시오.

[사고 단계]
1단계: 전체 실루엣을 관찰한다.
2단계: 몸체 형태를 관찰한다.
3단계: 상부(캡/결합부) 구조를 관찰한다.
4단계: 하부 형태를 관찰한다.
5단계: 전체 비례 관계를 관찰한다.

출력 형식은 반드시 다음 JSON만 출력하십시오 (다른 텍스트 없이):

{{
    "물품": "...",
    "형상_관찰": {{
    "전체_실루엣": "...",
    "몸체_형태": "...",
    "상부_구조": "...",
    "하부_형태": "...",
    "비례_관계": "..."
    }}
}}

이제 아래 이미지를 분석하십시오.
"""

BATCH_COMPARE_PROMPT = """
당신은 대한민국 특허청 디자인 심사관의 판단 기준을 설명하는
FTO(Freedom To Operate) 보조 어시스턴트입니다.

아래에 입력디자인 1개와, 비교디자인 여러 개의 '형상 관찰 결과'가 주어집니다.
각 비교디자인에 대해 형상, 실루엣, 전체 형태 측면에서만 비교하십시오.

⚠️ 중요 규칙
- 기능, 재질, 사용 용도는 고려하지 마십시오.
- 억지로 유사하다고 판단하지 마십시오.
- 차이가 더 명확한 경우, 비유사점을 중심으로 작성하십시오.

각 비교디자인에 대해 아래 사고 단계를 순서대로 수행하십시오.

[사고 단계]
1단계: 전체 실루엣, 상부 구조, 몸체 형태, 비례 중
        가장 차이가 큰 항목 하나를 먼저 선택한다.
2단계: 선택한 항목에서의 구체적인 차이를 서술한다.
3단계: 구조적으로 불가피한 공통 요소만 유사점으로 정리한다.

출력 형식은 반드시 다음 JSON 배열만 출력하십시오 (다른 텍스트 없이):

[
    {{
    "출원번호": "...",
    "비교결과": {{
    "유사한_점": [{{"항목": "...", "설명": "..."}}],
    "비유사한_점": [{{"항목": "...", "설명": "..."}}]
    }}
    }},
    ...
]

─────────────────────────────────
[입력디자인 분석 결과]
{input_analysis}

─────────────────────────────────
[비교디자인 목록]
{candidates_analyses}
"""

# ─────────────────────────────────────────────
# 3. 유틸리티 함수
# ─────────────────────────────────────────────
def encode_image_to_data_url(image_path: str) -> str:
    """이미지 파일 → base64 data URL 변환"""
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}"


def _cache_key_for_path(image_path: str) -> str:
    """이미지 경로의 해시 기반 캐시 키 생성"""
    return hashlib.md5(image_path.encode()).hexdigest()


def parse_json_safe(text: str) -> Optional[dict | list]:
    """
    LLM 출력에서 JSON을 안전하게 추출.
    마크다운 코드 블록(```json ... ```)도 처리.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines   = cleaned.split("\n")
        lines   = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return None


def distance_to_similarity(distance: float, metric: str = CHROMA_METRIC) -> float:
    """
    Chroma distance → [0, 1] 유사도 변환.
    - cosine: sim = 1 - dist  (dist ∈ [0, 2])
    - l2:     sim = 1 / (1 + dist)
    - ip:     sim = dist  (inner product 자체가 유사도)
    """
    if metric == "cosine":
        return 1.0 - distance
    elif metric == "l2":
        return 1.0 / (1.0 + distance)
    elif metric == "ip":
        return distance
    else:
        raise ValueError(f"지원하지 않는 metric: {metric}")


# ── [수정 7] ChromaDB nested dict 안전 파싱 ──
def _parse_status(metadata: dict) -> dict:
    """
    ChromaDB는 nested dict를 저장할 수 없어 JSON string으로 저장됨.
    status 필드가 dict 또는 JSON string 모두 안전하게 처리.
    """
    status = metadata.get("status", {})
    if isinstance(status, str):
        try:
            status = json.loads(status)
        except Exception:
            return {}
    return status if isinstance(status, dict) else {}


def _safe_meta(metadata: dict, key: str, default: str = "") -> str:
    """
    메타데이터에서 값을 안전하게 추출.
    status 내부 필드(regFg, admstStat 등)는 flat 저장 방식도 fallback 지원.
    """
    # 직접 키 접근
    val = metadata.get(key, None)
    if val is not None:
        return str(val)
    # status 내부 필드 fallback (flat 저장된 경우)
    status = _parse_status(metadata)
    val = status.get(key, None)
    if val is not None:
        return str(val)
    return default


# ─────────────────────────────────────────────
# 4. CLIP 임베딩
# ─────────────────────────────────────────────
print("CLIP 모델 로드 중...")
clip_model, clip_preprocess = clip.load(CLIP_MODEL_NAME, device=DEVICE)
print(f"CLIP 모델 로드 완료! (device={DEVICE})")


def get_image_embedding(image_path: str) -> Optional[list[float]]:
    """
    이미지 파일 경로 → 정규화된 CLIP 임베딩 벡터.
    DB 저장 시점과 동일하게 L2 normalize 적용.
    """
    try:
        image = clip_preprocess(Image.open(image_path)).unsqueeze(0).to(DEVICE)
        with torch.no_grad():
            embedding = clip_model.encode_image(image)
            embedding = embedding / embedding.norm(dim=-1, keepdim=True)
            return embedding.cpu().numpy()[0].tolist()
    except Exception as e:
        print(f"[CLIP 임베딩 실패] {image_path}: {e}")
        return None


# ─────────────────────────────────────────────
# 5. VLM 분석 (캐싱 포함)
# ─────────────────────────────────────────────
llm           = ChatOpenAI(model=LLM_MODEL, temperature=LLM_TEMPERATURE)
output_parser = StrOutputParser()

vlm_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "당신은 화장품 도면 분석가입니다. "
        "주어진 제품 도면 이미지를 분석해 JSON 형식으로 설명합니다. "
        "JSON 외의 텍스트는 출력하지 마십시오.",
    ),
    (
        "user",
        [
            {"type": "text",      "text": FEW_SHOT_CAPTIONING},
            {"type": "image_url", "image_url": {"url": "{image_url}"}},
        ],
    ),
])
vlm_chain = vlm_prompt | llm | output_parser  # 루프 밖에서 1회만 생성


def analyze_image_vlm(image_path: str, max_retries: int = 2) -> dict:
    """
    VLM으로 도면 분석 → Pydantic 검증된 dict 반환.
    파일 기반 캐시를 사용하여 동일 이미지 재분석 방지.
    """
    cache_key  = _cache_key_for_path(image_path)
    cache_file = VLM_CACHE_DIR / f"{cache_key}.json"

    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            DesignAnalysis(**cached)  # 검증
            return cached
        except Exception:
            cache_file.unlink(missing_ok=True)  # 깨진 캐시 삭제

    data_url = encode_image_to_data_url(image_path)

    for attempt in range(1, max_retries + 1):
        raw    = vlm_chain.invoke({"image_url": data_url})
        parsed = parse_json_safe(raw)
        if parsed is not None:
            try:
                validated = DesignAnalysis(**parsed)
                result    = validated.model_dump()
                cache_file.write_text(
                    json.dumps(result, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                return result
            except Exception:
                pass
        print(f"  [VLM 파싱 재시도 {attempt}/{max_retries}] {image_path}")

    print(f"  [VLM 파싱 실패 — raw 텍스트 사용] {image_path}")
    return {"_raw": raw, "물품": "파싱실패", "형상_관찰": {}}


# ─────────────────────────────────────────────
# 6. 벡터 검색 + 필터링 + 정렬
# ─────────────────────────────────────────────
def retrieve_similar_designs(
    image_path: str,
    collection: chromadb.Collection,
    top_k: int            = RETRIEVAL_TOP_K,
    max_candidates: int   = MAX_CANDIDATES,
    distance_threshold: float = DISTANCE_THRESHOLD,
    input_analysis: Optional[dict] = None,
) -> list[dict]:
    """
    입력 이미지에 대해 벡터 검색 → 필터링 → 정렬된 후보 리스트 반환.

    [수정 9] 반환값 구조 개선:
    - applicantName, agentName, designDescription, publicationNumber 포함
    - status 필드 flat 접근 보장 (_safe_meta 활용)
    """
    query_embedding = get_image_embedding(image_path)
    if query_embedding is None:
        raise RuntimeError(f"입력 이미지 임베딩 실패: {image_path}")

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
    )

    input_app_number = Path(image_path).stem.split("-")[0]

    best_by_app: dict[str, dict] = {}
    for i in range(len(results["ids"][0])):
        design_id = results["ids"][0][i]
        distance  = results["distances"][0][i]
        metadata  = results["metadatas"][0][i]
        app_number = metadata.get("applicationNumber", "N/A")

        # 자기 도면 제거
        if app_number == input_app_number and distance < 0.01:
            continue

        # distance threshold 초과 제거
        if distance > distance_threshold:
            continue

        # 동일 출원번호 중 최소 거리만 유지
        if app_number not in best_by_app or distance < best_by_app[app_number]["distance"]:
            status = _parse_status(metadata)   # ← [수정 7] 안전 파싱
            best_by_app[app_number] = {
                "design_id":  design_id,
                "distance":   distance,
                "similarity": distance_to_similarity(distance),
                "metadata":   metadata,
                # ── [수정 9] 자주 쓰는 필드 flat으로 꺼내두기 ──
                "applicationNumber":  app_number,
                "registrationNumber": _safe_meta(metadata, "registrationNumber"),
                "publicationNumber":  _safe_meta(metadata, "publicationNumber"),
                "articleName":        _safe_meta(metadata, "articleName"),
                "regFg":              status.get("regFg",              _safe_meta(metadata, "regFg")),
                "admstStat":          status.get("admstStat",          _safe_meta(metadata, "admstStat")),
                "lastDispositionDate":status.get("lastDispositionDate",_safe_meta(metadata, "lastDispositionDate")),
                "applicantName":      _safe_meta(metadata, "applicantName"),
                "agentName":          _safe_meta(metadata, "agentName"),
                "designSummary":      _safe_meta(metadata, "designSummary").replace("&quot;", '"'),
                "designDescription":  _safe_meta(metadata, "designDescription").replace("&quot;", '"'),
                "imagePath":          _safe_meta(metadata, "imagePath"),
            }

    candidates = sorted(best_by_app.values(), key=lambda x: x["distance"])

    if input_analysis:
        candidates = _keyword_rerank(candidates, input_analysis)

    return candidates[:max_candidates]


def _keyword_rerank(candidates: list[dict], input_analysis: dict) -> list[dict]:
    """
    VLM 분석에서 키워드를 추출하여 articleName과 매칭되는 후보에 보너스 부여.
    """
    input_article = input_analysis.get("물품", "")
    if not input_article:
        return candidates

    keywords = set(input_article)

    for c in candidates:
        article_name = c.get("articleName", "") or c["metadata"].get("articleName", "")
        overlap = sum(1 for kw in keywords if kw in article_name)
        c["_rerank_bonus"] = overlap * 0.001
        c["_sort_key"]     = c["distance"] - c["_rerank_bonus"]

    candidates.sort(key=lambda x: x.get("_sort_key", x["distance"]))
    return candidates


# ─────────────────────────────────────────────
# 7. 일괄 비교 분석 (1회 LLM 호출)
# ─────────────────────────────────────────────
compare_prompt_template = ChatPromptTemplate.from_messages([
    (
        "system",
        "당신은 대한민국 특허청 디자인 심사관의 판단 기준을 설명해주는 "
        "FTO(Freedom To Operate) 보조 어시스턴트이다. "
        "출력은 반드시 JSON 배열만 출력하고, 다른 텍스트는 출력하지 마라.",
    ),
    ("user", "{comparison_input}"),
])
compare_chain = compare_prompt_template | llm | output_parser


def run_batch_comparison(
    input_analysis: dict,
    candidates: list[dict],
    max_retries: int = 2,
) -> list[dict]:
    """입력디자인과 모든 후보를 한 번의 LLM 호출로 비교."""
    candidate_texts = []
    for i, c in enumerate(candidates, 1):
        app_num = c.get("applicationNumber", c["metadata"].get("applicationNumber", "N/A"))
        vlm     = c.get("vlm_analysis", {})
        vlm_str = json.dumps(vlm, ensure_ascii=False, indent=2) if isinstance(vlm, dict) else str(vlm)
        candidate_texts.append(
            f"--- 비교디자인 {i} (출원번호: {app_num}) ---\n{vlm_str}"
        )

    input_str      = json.dumps(input_analysis, ensure_ascii=False, indent=2)
    candidates_str = "\n\n".join(candidate_texts)
    comparison_input = BATCH_COMPARE_PROMPT.format(
        input_analysis=input_str,
        candidates_analyses=candidates_str,
    )

    for attempt in range(1, max_retries + 1):
        raw    = compare_chain.invoke({"comparison_input": comparison_input})
        parsed = parse_json_safe(raw)
        if parsed is not None and isinstance(parsed, list):
            try:
                validated = [BatchComparisonEntry(**entry) for entry in parsed]
                return [v.model_dump() for v in validated]
            except Exception:
                pass
        print(f"  [비교 분석 파싱 재시도 {attempt}/{max_retries}]")

    print("  [비교 분석 파싱 실패 — raw 텍스트 사용]")
    return [{"_raw": raw}]


# ─────────────────────────────────────────────
# 8. 리포트 생성
# ─────────────────────────────────────────────
def generate_report(
    input_image_path: str,
    input_analysis: dict,
    candidates: list[dict],
    comparison_results: list[dict],
) -> str:
    """최종 FTO 비교 분석 리포트 문자열 생성."""
    input_app_number = Path(input_image_path).stem.split("-")[0]
    lines = [
        "",
        "=" * 70,
        "디자인 FTO(Freedom To Operate) 비교 분석 리포트",
        "=" * 70,
        "",
        f"[입력 디자인 (출원번호: {input_app_number})]",
        json.dumps(input_analysis, ensure_ascii=False, indent=2),
        "",
    ]

    comp_map = {}
    for cr in comparison_results:
        if "출원번호" in cr:
            comp_map[cr["출원번호"]] = cr.get("비교결과", cr)

    for i, c in enumerate(candidates, 1):
        # ── [수정 9] flat 필드 우선 사용 ──
        app_num    = c.get("applicationNumber", c["metadata"].get("applicationNumber", "N/A"))
        article    = c.get("articleName",       c["metadata"].get("articleName", "N/A"))
        admst_stat = c.get("admstStat",         "N/A")
        img_path   = c.get("imagePath",         c["metadata"].get("imagePath", "N/A"))
        applicant  = c.get("applicantName",     "")
        agent      = c.get("agentName",         "")
        summary    = c.get("designSummary",     "")
        desc       = c.get("designDescription", "")

        lines.append("-" * 70)
        lines.append(f"[비교 대상 {i}]")
        lines.append(f"  출원번호    : {app_num}")
        lines.append(f"  상품명      : {article}")
        lines.append(f"  유사도 거리 : {c['distance']:.4f}  (similarity: {c['similarity']:.4f})")
        lines.append(f"  상태        : {admst_stat}")
        lines.append(f"  출원인      : {applicant or 'N/A'}")
        lines.append(f"  대리인      : {agent or 'N/A'}")
        lines.append(f"  창작의 요점 : {summary or 'N/A'}")
        lines.append(f"  디자인 설명 : {desc or 'N/A'}")
        lines.append(f"  이미지 경로 : {img_path}")
        lines.append("")

        vlm = c.get("vlm_analysis", {})
        lines.append("  [VLM 분석]")
        lines.append(
            "  " + json.dumps(vlm, ensure_ascii=False, indent=2).replace("\n", "\n  ")
        )
        lines.append("")

        comp = comp_map.get(app_num, {})
        lines.append("  [특허청 심사 기준 유사성 분석]")
        lines.append(
            "  " + json.dumps(comp, ensure_ascii=False, indent=2).replace("\n", "\n  ")
        )
        lines.append("")

    lines.append("=" * 70)
    return "\n".join(lines)


# ─────────────────────────────────────────────
# 9. 메인 실행
# ─────────────────────────────────────────────
def main(image_path: str):
    chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    collection    = chroma_client.get_collection(name=COLLECTION_NAME)

    print("[1/4] 입력 이미지 VLM 분석 중...")
    input_analysis = analyze_image_vlm(image_path)
    print("입력 이미지 분석 결과:")
    print(json.dumps(input_analysis, ensure_ascii=False, indent=2))

    print(f"\n[2/4] 벡터 검색 (top_k={RETRIEVAL_TOP_K}) + 필터링 → 최대 {MAX_CANDIDATES}건...")
    candidates = retrieve_similar_designs(
        image_path, collection, input_analysis=input_analysis,
    )
    print(f"  → 후보 {len(candidates)}건 선정")

    if not candidates:
        print("유사 디자인이 검색되지 않았습니다.")
        return

    print(f"\n[3/4] 후보 {len(candidates)}건 VLM 분석 중 (캐시 활용)...")
    for c in candidates:
        img_path = c.get("imagePath", c["metadata"].get("imagePath", ""))
        if img_path and os.path.exists(img_path):
            c["vlm_analysis"] = analyze_image_vlm(img_path)
        else:
            c["vlm_analysis"] = {"_error": f"이미지 없음: {img_path}"}

    print("\n[4/4] 일괄 비교 분석 중 (1회 LLM 호출)...")
    comparison_results = run_batch_comparison(input_analysis, candidates)

    report = generate_report(image_path, input_analysis, candidates, comparison_results)
    print(report)
    return report


if __name__ == "__main__":
    INPUT_IMAGE = r"2024-2026/images/3020250027386-09-01-1_001.jpg"
    main(INPUT_IMAGE)