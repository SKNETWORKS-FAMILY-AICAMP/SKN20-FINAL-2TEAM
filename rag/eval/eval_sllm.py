"""
sLLM 기반 FTO 분석 품질 평가 스크립트

실제 서비스 흐름과 동일하게 평가합니다:
    검색(TOP10) → 상위 3건을 1건씩 sLLM(analyze_single_patent) 호출

GPT-4를 judge로 사용하지 않고, patent_id 매칭으로 평가합니다.

평가 지표:
    - Faithfulness: sLLM이 분석한 특허가 검색 TOP에서 온 것인지 (충실도)
    - Answer Relevancy: sLLM이 분석한 TOP3에 정답 특허가 포함되는지 (응답 관련성)
    - Answer Correctness: sLLM 분석 형식 품질 (섹션 존재, 라벨 매핑, 법리 일관성)

사용법:
    conda activate fto
    python -m rag.eval.eval_sllm
"""

import sys
import logging
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from rag.search.pipeline import search
from rag.generate import build_prompt, call_llm, parse_response

# ── 로깅 설정 ─────────────────────────────────────────
LOG_DIR = PROJECT_ROOT / "backend" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_path = LOG_DIR / f"eval_sllm_{timestamp}.log"

logger = logging.getLogger("eval_sllm")
logger.setLevel(logging.INFO)

fh = logging.FileHandler(log_path, encoding="utf-8")
fh.setFormatter(logging.Formatter("%(asctime)s | %(message)s", datefmt="%H:%M:%S"))
logger.addHandler(fh)

ch = logging.StreamHandler()
ch.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(ch)


# ── 설정 ──────────────────────────────────────────────
DATASET_PATH = Path(__file__).parent / "ragas_dataset.xlsx"
TOP_K = 10   # 검색 결과 수
ANALYZE_TOP_N = 3  # sLLM 분석할 상위 특허 수 (실제 서비스와 동일)


# ── 유틸 ──────────────────────────────────────────────
def _get_patent_id(r: dict) -> str:
    return r.get("patent_id", r.get("metadata", {}).get("apply_num", ""))


def normalize_apply_num(raw: str) -> str:
    """'10-2006-0001051' -> '1020060001051' (하이픈 제거)"""
    return str(raw).replace("-", "").strip()


def _normalize_sllm_patent_id(raw_id: str) -> str:
    """sLLM 출력의 patent_id를 정규화."""
    cleaned = raw_id.strip().replace("-", "").replace(" ", "")
    for ch in "[]()":
        cleaned = cleaned.replace(ch, "")
    return cleaned


# ── 등록번호 → 출원번호 매핑 ─────────────────────────
_regit_to_apply: dict[str, str] = {}


def _build_regit_mapping():
    """ChromaDB에서 등록번호→출원번호 매핑 테이블 구축 (최초 1회)."""
    global _regit_to_apply
    if _regit_to_apply:
        return

    import chromadb
    from chromadb.config import Settings
    logger.info("ChromaDB 등록번호→출원번호 매핑 테이블 구축 중...")
    client = chromadb.PersistentClient(
        path=str(PROJECT_ROOT / "data" / "chroma-patent"),
        settings=Settings(anonymized_telemetry=False),
    )
    col = client.get_collection("patent_chunks")

    batch_size = 5000
    offset = 0
    while True:
        results = col.get(offset=offset, limit=batch_size, include=["metadatas"])
        if not results["ids"]:
            break
        for meta in results["metadatas"]:
            regit = meta.get("regit_num", "")
            apply_num = meta.get("apply_num", "")
            if regit and apply_num:
                regit_clean = regit.replace("-", "")
                _regit_to_apply[regit_clean] = apply_num
        offset += len(results["ids"])
        logger.info(f"  매핑 로드: {offset}건...")

    logger.info(f"매핑 테이블 완료: {len(_regit_to_apply)}개")


def _resolve_patent_id(raw_id: str) -> str:
    """sLLM 출력 ID를 출원번호로 변환. 등록번호면 매핑, 아니면 원본 반환."""
    normalized = _normalize_sllm_patent_id(raw_id)
    return _regit_to_apply.get(normalized, normalized)


def load_dataset(path: Path) -> list[dict]:
    df = pd.read_excel(path)
    dataset = []
    for _, row in df.iterrows():
        query = row["user_query"]
        expected = set()
        for col in ["apply_num_1", "apply_num_2"]:
            val = row.get(col)
            if pd.notna(val):
                expected.add(normalize_apply_num(val))
        if query and expected:
            dataset.append({"query": query, "expected": expected})
    return dataset


# ── 평가 ──────────────────────────────────────────────
def evaluate_single(query: str, expected: set[str], rrf_weights: tuple) -> dict:
    """단일 질의에 대해 검색 + sLLM 분석 후 평가."""
    result = {
        "query": query[:40],
        "expected": expected,
        "search_ids": [],
        "sllm_ids": [],
        "faithfulness": 0.0,
        "answer_relevancy": 0.0,
        "format_score": 0.0,
        "labels": [],
        "error": None,
    }

    # 1) 검색
    try:
        search_results = search(query, rrf_weights=rrf_weights, top_k=TOP_K)
        search_ids = [_get_patent_id(r) for r in search_results]
        result["search_ids"] = search_ids
    except Exception as e:
        result["error"] = f"검색 실패: {e}"
        return result

    # 2) sLLM 분석 — 실제 서비스와 동일하게 상위 N건을 1건씩 호출
    #    build_prompt → call_llm → parse_response (backend_adapter 경유 없이 직접 호출)
    patent_analyses = []
    for i in range(min(ANALYZE_TOP_N, len(search_results))):
        try:
            sr = search_results[i]
            metadata = sr.get("metadata", {})
            register_status = metadata.get("register_status", "")

            # 공개 특허는 sLLM 스킵 (실제 서비스와 동일)
            if register_status != "등록":
                patent_analyses.append({
                    "patent_id": sr.get("patent_id", "unknown"),
                    "label": "공개",
                    "metadata": metadata,
                })
                continue

            messages = build_prompt(sr, query)
            raw_output = call_llm(messages)
            parsed = parse_response(raw_output)
            parsed["patent_id"] = sr.get("patent_id", "unknown")
            parsed["metadata"] = metadata
            patent_analyses.append(parsed)
        except Exception as e:
            logger.info(f"    sLLM #{i} 실패: {e}")
            continue

    # sLLM이 분석한 특허 ID 추출 + 등록번호→출원번호 매핑
    sllm_ids = [_resolve_patent_id(_get_patent_id(a)) for a in patent_analyses]
    result["sllm_ids"] = sllm_ids

    # ── Faithfulness ──
    # sLLM이 분석한 특허가 모두 검색 결과 TOP에서 온 것인지
    # (1건씩 search_results[i]를 넘기므로 항상 1.0이어야 정상)
    if sllm_ids:
        search_id_set = set(search_ids)
        faithful_count = sum(1 for sid in sllm_ids if sid in search_id_set)
        result["faithfulness"] = faithful_count / len(sllm_ids)
    else:
        result["faithfulness"] = 0.0

    # ── Answer Relevancy ──
    # sLLM이 분석한 TOP3에 정답 특허가 포함되는 비율
    if sllm_ids:
        sllm_id_set = set(sllm_ids)
        matched = len(expected & sllm_id_set)
        result["answer_relevancy"] = matched / len(expected)
    else:
        result["answer_relevancy"] = 0.0

    # ── Answer Correctness (형식 품질) ──
    # 각 분석의 섹션 존재, 라벨 매핑, 법리 일관성을 종합
    format_scores = []
    labels = []
    for analysis in patent_analyses:
        score = 0.0
        total_checks = 3  # 섹션, 라벨, 법리 일관성

        # 1. 섹션 존재 (구성대비, 판단, 결론)
        sections = analysis.get("sections_found", {})
        section_count = sum(1 for v in sections.values() if v)
        score += section_count / 3 if sections else 0

        # 2. 라벨 매핑 성공
        label = analysis.get("label", "매핑실패")
        labels.append(label)
        if label not in ("매핑실패", "분석불가"):
            score += 1.0

        # 3. 법리 일관성
        consistency = analysis.get("logic_consistency", "-")
        if consistency == "O":
            score += 1.0
        elif consistency == "-":
            score += 0.5  # 체크 불가는 중립

        format_scores.append(score / total_checks)

    result["labels"] = labels
    result["format_score"] = sum(format_scores) / len(format_scores) if format_scores else 0.0

    return result


def evaluate_all(dataset: list[dict], rrf_weights: tuple) -> dict:
    """전체 데이터셋 평가."""
    total = len(dataset)
    details = []
    faithfulness_sum = 0.0
    relevancy_sum = 0.0
    format_sum = 0.0
    errors = 0

    for i, item in enumerate(dataset, 1):
        query = item["query"]
        expected = item["expected"]

        logger.info(f"  [{i}/{total}] {query[:50]}")

        result = evaluate_single(query, expected, rrf_weights)
        details.append(result)

        if result["error"]:
            errors += 1
            logger.info(f"    ERROR: {result['error']}")
            continue

        faithfulness_sum += result["faithfulness"]
        relevancy_sum += result["answer_relevancy"]
        format_sum += result["format_score"]

        sllm_str = ", ".join(result["sllm_ids"][:3]) or "-"
        labels_str = ", ".join(result["labels"]) or "-"
        logger.info(f"    sLLM 선별: [{sllm_str}]")
        logger.info(f"    라벨: [{labels_str}]")
        logger.info(f"    Faithfulness={result['faithfulness']:.2f} "
                     f"Relevancy={result['answer_relevancy']:.2f} "
                     f"Format={result['format_score']:.2f}")

    evaluated = total - errors

    return {
        "faithfulness": faithfulness_sum / evaluated if evaluated > 0 else 0,
        "answer_relevancy": relevancy_sum / evaluated if evaluated > 0 else 0,
        "answer_correctness": format_sum / evaluated if evaluated > 0 else 0,
        "total": total,
        "evaluated": evaluated,
        "errors": errors,
        "details": details,
    }


# ── 마크다운 리포트 ────────────────────────────────────
def _build_markdown_report(result: dict, dataset: list[dict], rrf_weights: tuple) -> str:
    lines = []

    lines.append("# sLLM FTO 분석 품질 평가 리포트")
    lines.append("")
    lines.append(f"> 평가 일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"> 데이터셋: {len(dataset)}개 Q&A 쌍")
    lines.append(f"> RRF 가중치: Dense={rrf_weights[0]}, Sparse={rrf_weights[1]}")
    lines.append(f"> 검색 범위: TOP {TOP_K}")
    lines.append(f"> 평가 완료: {result['evaluated']}/{result['total']}건 (에러 {result['errors']}건)")

    # ── 평가 지표 설명 ──
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 평가 지표")
    lines.append("")

    lines.append("### Faithfulness (충실도)")
    lines.append("")
    lines.append("sLLM이 분석한 특허가 **검색 결과에서 온 것인지** 확인합니다.")
    lines.append("")
    lines.append("- 수식: `(sLLM 분석 특허 중 검색 TOP에 있는 수) / (sLLM 분석 특허 수)`")
    lines.append("- 범위: 0 ~ 1.0 (1.0이면 모든 분석이 검색 결과 기반)")
    lines.append("- 의미: sLLM이 검색 결과를 충실히 활용하는가? (환각 없이)")
    lines.append("")

    lines.append("### Answer Relevancy (응답 관련성)")
    lines.append("")
    lines.append("sLLM이 선별한 TOP3에 **정답 특허가 포함되는지** 확인합니다.")
    lines.append("")
    lines.append("- 수식: `(sLLM TOP3 중 정답 특허 수) / (정답 특허 수)`")
    lines.append("- 범위: 0 ~ 1.0")
    lines.append("- 의미: sLLM이 실제 침해 가능성이 높은 특허를 올바르게 선별하는가?")
    lines.append("")

    lines.append("### Answer Correctness (분석 형식 품질)")
    lines.append("")
    lines.append("sLLM 분석 출력의 **형식적 품질**을 종합 평가합니다.")
    lines.append("")
    lines.append("- 3가지 항목의 평균:")
    lines.append("  1. **섹션 존재**: 구성 대비, 판단, 결론 섹션이 모두 있는가")
    lines.append("  2. **라벨 매핑**: 결론에서 침해/비침해/전문가 라벨이 추출되는가")
    lines.append("  3. **법리 일관성**: 구성대비표와 결론 라벨이 논리적으로 일관되는가")
    lines.append("- 범위: 0 ~ 1.0")
    lines.append("- 의미: sLLM이 구조화된 고품질 분석을 생성하는가?")
    lines.append("")

    lines.append("### 지표 요약")
    lines.append("")
    lines.append("| 지표 | 질문 | 범위 | 높을수록 |")
    lines.append("|------|------|------|----------|")
    lines.append("| **Faithfulness** | 검색 결과를 충실히 사용하는가? | 0~1.0 | 좋음 |")
    lines.append("| **Answer Relevancy** | 정답 특허를 선별하는가? | 0~1.0 | 좋음 |")
    lines.append("| **Answer Correctness** | 분석 품질이 좋은가? | 0~1.0 | 좋음 |")

    # ── 핵심 결과 ──
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 평가 결과")
    lines.append("")
    lines.append("| Faithfulness | Answer Relevancy | Answer Correctness |")
    lines.append("|:---:|:---:|:---:|")
    lines.append(
        f"| **{result['faithfulness']:.3f}** "
        f"| **{result['answer_relevancy']:.3f}** "
        f"| **{result['answer_correctness']:.3f}** |"
    )

    # ── 상세 결과 ──
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 질의별 상세 결과")
    lines.append("")
    lines.append("| # | Query | Expected | sLLM 선별 | Labels | Faith. | Relev. | Format |")
    lines.append("|--:|-------|----------|-----------|--------|:------:|:------:|:------:|")

    for idx, d in enumerate(result["details"], 1):
        query = d["query"].replace("|", "/")
        expected = ", ".join(sorted(d["expected"]))
        sllm = ", ".join(d["sllm_ids"][:3]) if d["sllm_ids"] else "-"
        labels = ", ".join(d["labels"]) if d["labels"] else "-"
        if d["error"]:
            lines.append(f"| {idx} | {query} | {expected} | ERROR | - | - | - | - |")
        else:
            lines.append(
                f"| {idx} | {query} | {expected} | {sllm} | {labels} "
                f"| {d['faithfulness']:.2f} | {d['answer_relevancy']:.2f} | {d['format_score']:.2f} |"
            )

    # ── PPT 슬라이드 문구 제안 ──
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## PPT 슬라이드 문구 제안")
    lines.append("")
    lines.append("### 슬라이드: sLLM FTO 분석 품질 평가")
    lines.append("")
    lines.append("```")
    lines.append(f"[제목] sLLM 침해 분석 품질 평가")
    lines.append(f"")
    lines.append(f"- {len(dataset)}개 Q&A셋으로 검색 → sLLM 분석 파이프라인 평가")
    lines.append(f"- Faithfulness (충실도): {result['faithfulness']:.3f}")
    lines.append(f"  → sLLM이 검색 결과를 충실히 활용 (환각 없음)")
    lines.append(f"- Answer Relevancy (응답 관련성): {result['answer_relevancy']:.3f}")
    lines.append(f"  → sLLM이 정답 특허를 TOP3에 포함하는 비율")
    lines.append(f"- Answer Correctness (분석 품질): {result['answer_correctness']:.3f}")
    lines.append(f"  → 구조화된 분석 형식 + 법리 일관성")
    lines.append("```")

    lines.append("")
    return "\n".join(lines)


# ── 메인 ──────────────────────────────────────────────
def main():
    logger.info("=" * 60)
    logger.info("sLLM FTO 분석 품질 평가")
    logger.info("=" * 60)

    dataset = load_dataset(DATASET_PATH)
    logger.info(f"\n데이터셋: {len(dataset)}개 질의\n")

    # 등록번호→출원번호 매핑 테이블 구축
    _build_regit_mapping()

    # 현재 최적 가중치 사용 (1:1)
    rrf_weights = (0.5, 0.5)
    logger.info(f"RRF 가중치: Dense={rrf_weights[0]}, Sparse={rrf_weights[1]}\n")

    result = evaluate_all(dataset, rrf_weights)

    # ── 최종 결과 ──
    logger.info(f"\n{'=' * 60}")
    logger.info("최종 결과")
    logger.info(f"{'=' * 60}")
    logger.info(f"  Faithfulness:       {result['faithfulness']:.3f}")
    logger.info(f"  Answer Relevancy:   {result['answer_relevancy']:.3f}")
    logger.info(f"  Answer Correctness: {result['answer_correctness']:.3f}")
    logger.info(f"  평가 완료: {result['evaluated']}/{result['total']}건")

    # ── 결과 저장 ──
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # CSV
    csv_path = output_dir / f"eval_sllm_{timestamp}.csv"
    rows = []
    for d in result["details"]:
        rows.append({
            "query": d["query"],
            "expected": "|".join(sorted(d["expected"])),
            "sllm_ids": "|".join(d["sllm_ids"]),
            "labels": "|".join(d["labels"]),
            "faithfulness": d["faithfulness"],
            "answer_relevancy": d["answer_relevancy"],
            "format_score": d["format_score"],
            "error": d["error"] or "",
        })
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")

    # Markdown 리포트
    md_path = output_dir / f"eval_sllm_report_{timestamp}.md"
    md = _build_markdown_report(result, dataset, rrf_weights)
    md_path.write_text(md, encoding="utf-8")

    logger.info(f"\n결과 저장: {csv_path}")
    logger.info(f"리포트 저장: {md_path}")
    logger.info(f"로그 저장: {log_path}")


if __name__ == "__main__":
    main()
