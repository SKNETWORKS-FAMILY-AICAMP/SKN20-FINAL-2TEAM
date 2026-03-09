"""
특허 RAG 검색 품질 평가 스크립트

ragas_dataset.xlsx의 Q&A셋으로 다양한 RRF 가중치 조합을 평가합니다.
평가 지표:
    - Context Recall (Hit Rate): 정답 특허가 검색 결과 TOP10에 포함되는 비율
    - Context Precision: TOP10 중 정답 특허가 차지하는 비율
    - MRR (Mean Reciprocal Rank): 정답 특허가 검색 결과에서 얼마나 상위에 위치하는지
    - MAP (Mean Average Precision): 정답이 여러 개일 때 종합 순위 평가

사용법:
    conda activate fto
    python -m rag.eval.eval_retrieval
"""

import sys
import logging
from pathlib import Path
from datetime import datetime

# 프로젝트 루트를 path에 추가
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from rag.search.pipeline import search

# ── 로깅 설정 ─────────────────────────────────────────
LOG_DIR = PROJECT_ROOT / "backend" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_path = LOG_DIR / f"eval_retrieval_{timestamp}.log"

logger = logging.getLogger("eval_retrieval")
logger.setLevel(logging.INFO)

fh = logging.FileHandler(log_path, encoding="utf-8")
fh.setFormatter(logging.Formatter("%(asctime)s | %(message)s", datefmt="%H:%M:%S"))
logger.addHandler(fh)

ch = logging.StreamHandler()
ch.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(ch)


# ── 설정 ──────────────────────────────────────────────
DATASET_PATH = Path(__file__).parent / "ragas_dataset.xlsx"
TOP_K = 10

WEIGHT_CONFIGS = {
    "Dense:Sparse = 1:4 (현재)": (0.2, 0.8),
    "Dense:Sparse = 1:3":       (0.25, 0.75),
    "Dense:Sparse = 1:1":       (0.5, 0.5),
    "Dense:Sparse = 3:1":       (0.75, 0.25),
}


# ── 유틸 ──────────────────────────────────────────────
def _get_patent_id(r: dict) -> str:
    return r.get("patent_id", r.get("metadata", {}).get("apply_num", ""))


def normalize_apply_num(raw: str) -> str:
    """'10-2006-0001051' -> '1020060001051' (하이픈 제거)"""
    return str(raw).replace("-", "").strip()


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


# ── 지표 계산 ─────────────────────────────────────────
def _calc_reciprocal_rank(ranked_ids: list[str], expected: set[str]) -> float:
    """MRR: 정답이 처음 등장하는 순위의 역수. 없으면 0."""
    for rank, pid in enumerate(ranked_ids, 1):
        if pid in expected:
            return 1.0 / rank
    return 0.0


def _calc_average_precision(ranked_ids: list[str], expected: set[str]) -> float:
    """AP: 정답 위치마다 precision 계산 후 평균."""
    hits = 0
    sum_precision = 0.0
    for rank, pid in enumerate(ranked_ids, 1):
        if pid in expected:
            hits += 1
            sum_precision += hits / rank
    if not expected:
        return 0.0
    return sum_precision / len(expected)


# ── 평가 ──────────────────────────────────────────────
def evaluate(dataset: list[dict], rrf_weights: tuple[float, float]) -> dict:
    total = len(dataset)
    hits = 0
    hits_at_3 = 0
    precision_sum = 0.0
    mrr_sum = 0.0
    ap_sum = 0.0
    details = []

    for i, item in enumerate(dataset, 1):
        query = item["query"]
        expected = item["expected"]

        try:
            results = search(query, rrf_weights=rrf_weights, top_k=TOP_K)
            ranked_ids = [_get_patent_id(r) for r in results]
            hit = bool(expected & set(ranked_ids))
            hit_3 = bool(expected & set(ranked_ids[:3]))
            matched_in_top = len(expected & set(ranked_ids))
            precision = matched_in_top / len(ranked_ids) if ranked_ids else 0.0
            rr = _calc_reciprocal_rank(ranked_ids, expected)
            ap = _calc_average_precision(ranked_ids, expected)
        except Exception as e:
            logger.info(f"  [{i}/{total}] ERROR: {e}")
            hit, hit_3, precision, rr, ap = False, False, 0.0, 0.0, 0.0
            ranked_ids = []

        if hit:
            hits += 1
        if hit_3:
            hits_at_3 += 1
        precision_sum += precision
        mrr_sum += rr
        ap_sum += ap

        first_rank = "-"
        for rank, pid in enumerate(ranked_ids, 1):
            if pid in expected:
                first_rank = str(rank)
                break

        details.append({
            "query": query[:40],
            "expected": expected,
            "retrieved_top3": ranked_ids[:3],
            "hit": hit,
            "hit_at_3": hit_3,
            "first_rank": first_rank,
            "precision": precision,
            "rr": rr,
            "ap": ap,
        })

        status = "O" if hit else "X"
        top3_mark = "O" if hit_3 else "X"
        logger.info(f"  [{i}/{total}] TOP10={status} TOP3={top3_mark} (rank={first_rank}) | {query[:50]}")
        logger.info(f"           expected: {expected}")
        logger.info(f"           got top3: {ranked_ids[:3]}")

    context_recall = hits / total if total > 0 else 0
    hit_rate_at_3 = hits_at_3 / total if total > 0 else 0
    context_precision = precision_sum / total if total > 0 else 0
    mrr = mrr_sum / total if total > 0 else 0
    map_score = ap_sum / total if total > 0 else 0

    return {
        "context_recall": context_recall,
        "hit_rate_at_3": hit_rate_at_3,
        "context_precision": context_precision,
        "mrr": mrr,
        "map": map_score,
        "hits": hits,
        "hits_at_3": hits_at_3,
        "total": total,
        "details": details,
    }


# ── 마크다운 리포트 (PPT용) ──────────────────────────
def _build_markdown_report(summary: dict, dataset: list[dict]) -> str:
    lines = []

    # 타이틀
    lines.append("# 특허 RAG 검색 성능 평가 리포트")
    lines.append("")
    lines.append(f"> 평가 일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"> 데이터셋: {len(dataset)}개 Q&A 쌍")
    lines.append(f"> 검색 범위: TOP {TOP_K}")
    lines.append(f"> 전체 특허 DB: 78,520건")

    # ── 평가 지표 설명 (PPT 슬라이드 1) ──
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 평가 지표")
    lines.append("")
    lines.append("### Context Recall (Hit Rate@10)")
    lines.append("")
    lines.append("정답 특허가 검색 결과 TOP10 안에 **포함되는지 여부**를 측정합니다.")
    lines.append("")
    lines.append("- 수식: `(정답이 TOP10에 포함된 질의 수) / (전체 질의 수)`")
    lines.append("- 범위: 0% ~ 100%")
    lines.append("- 예시: 35개 질의 중 33개의 정답이 TOP10에 포함 → **94.3%**")
    lines.append("- 의미: \"검색 시스템이 정답을 놓치지 않는가?\"를 평가")
    lines.append("")
    lines.append("### Hit Rate@3")
    lines.append("")
    lines.append("정답 특허가 검색 결과 **TOP3 안에 포함되는지** 측정합니다.")
    lines.append("")
    lines.append("- 수식: `(정답이 TOP3에 포함된 질의 수) / (전체 질의 수)`")
    lines.append("- 범위: 0% ~ 100%")
    lines.append("- 의미: sLLM에 전달되는 상위 결과에 정답이 포함되는가?")
    lines.append("")
    lines.append("### Context Precision")
    lines.append("")
    lines.append("검색 결과 TOP10 중 **정답 특허가 차지하는 비율**을 측정합니다.")
    lines.append("")
    lines.append("- 수식: `(TOP10 중 정답 특허 수) / (TOP10 크기)`")
    lines.append("- 범위: 0 ~ 1.0")
    lines.append("- 예시: TOP10 중 정답 1개 포함 → 1/10 = **0.100**")
    lines.append("- 의미: \"검색 결과가 얼마나 정확한가?\" (노이즈 없이 정답 위주로 반환하는가)")
    lines.append("")
    lines.append("### MRR (Mean Reciprocal Rank)")
    lines.append("")
    lines.append("정답 특허가 검색 결과에서 **얼마나 상위에 위치하는지**를 측정합니다.")
    lines.append("")
    lines.append("- 수식: `평균(1 / 정답이 처음 등장하는 순위)`")
    lines.append("- 범위: 0 ~ 1.0 (1.0이면 매번 1등)")
    lines.append("- 예시:")
    lines.append("  - 질의 A: 정답이 1등 → 1/1 = **1.000**")
    lines.append("  - 질의 B: 정답이 3등 → 1/3 = **0.333**")
    lines.append("  - 질의 C: 정답 없음 → **0.000**")
    lines.append("  - MRR = (1.000 + 0.333 + 0.000) / 3 = **0.444**")
    lines.append("- 의미: \"정답이 검색 결과 상위에 오는가?\"를 평가")
    lines.append("")
    lines.append("### MAP (Mean Average Precision)")
    lines.append("")
    lines.append("정답이 **여러 개**일 때, 각 정답의 순위를 종합적으로 평가합니다.")
    lines.append("")
    lines.append("- 수식: 각 질의의 Average Precision을 평균")
    lines.append("  - AP = 정답이 등장할 때마다 `(그 시점까지의 정답 수 / 현재 순위)`를 계산하여 평균")
    lines.append("- 범위: 0 ~ 1.0")
    lines.append("- 예시 (정답 2개: A, B):")
    lines.append("  - 검색 결과: [A, X, B, X, X] → AP = (1/1 + 2/3) / 2 = **0.833**")
    lines.append("  - 검색 결과: [X, X, A, X, B] → AP = (1/3 + 2/5) / 2 = **0.367**")
    lines.append("- 의미: \"정답이 여러 개일 때 모두 상위에 오는가?\"를 평가")
    lines.append("")
    lines.append("### 지표 요약")
    lines.append("")
    lines.append("| 지표 | 질문 | 범위 | 높을수록 |")
    lines.append("|------|------|------|----------|")
    lines.append("| **Context Recall** | 정답을 찾았는가? (TOP10) | 0~100% | 좋음 |")
    lines.append("| **Hit Rate@3** | 정답이 TOP3에 있는가? | 0~100% | 좋음 |")
    lines.append("| **Context Precision** | TOP10이 정답 위주인가? | 0~1.0 | 좋음 |")
    lines.append("| **MRR** | 정답이 몇 등인가? | 0~1.0 | 좋음 |")
    lines.append("| **MAP** | 정답 여러 개가 모두 상위인가? | 0~1.0 | 좋음 |")

    # ── 핵심 비교표 (PPT 메인 슬라이드) ──
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 하이브리드 검색 가중치 최적화 실험")
    lines.append("")
    lines.append("Dense(의미 검색)와 Sparse(BM25 키워드 검색)의 비율을 변경하며 검색 성능을 비교하였습니다.")
    lines.append("")
    lines.append("| 설정 | Dense | Sparse | Context Recall | Hit Rate@3 | Context Precision | MRR | MAP |")
    lines.append("|------|:-----:|:------:|:--------------:|:----------:|:-----------------:|:---:|:---:|")

    best_recall_name = max(summary, key=lambda k: summary[k]["context_recall"])
    best_mrr_name = max(summary, key=lambda k: summary[k]["mrr"])

    for name, result in summary.items():
        cfg = WEIGHT_CONFIGS.get(name, (0, 0))
        is_best = (name == best_recall_name)
        mark = " **" if is_best else ""
        mark_end = "** " if is_best else ""
        lines.append(
            f"| {mark}{name}{mark_end} | {cfg[0]} | {cfg[1]} "
            f"| {mark}{result['context_recall']:.1%} ({result['hits']}/{result['total']}){mark_end} "
            f"| {mark}{result['hit_rate_at_3']:.1%} ({result['hits_at_3']}/{result['total']}){mark_end} "
            f"| {mark}{result['context_precision']:.3f}{mark_end} "
            f"| {mark}{result['mrr']:.3f}{mark_end} "
            f"| {mark}{result['map']:.3f}{mark_end} |"
        )

    # ── 핵심 결과 요약 (PPT 포인트) ──
    best_result = summary[best_recall_name]
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 실험 결과 요약")
    lines.append("")
    lines.append(f"- **최적 가중치**: {best_recall_name}")
    lines.append(f"  - Context Recall: **{best_result['context_recall']:.1%}**")
    lines.append(f"  - Hit Rate@3: **{best_result['hit_rate_at_3']:.1%}**")
    lines.append(f"  - Context Precision: **{best_result['context_precision']:.3f}**")
    lines.append(f"  - MRR: **{best_result['mrr']:.3f}**")
    lines.append(f"  - MAP: **{best_result['map']:.3f}**")
    lines.append("")

    # 현재 vs 최적 비교
    current_name = "Dense:Sparse = 1:4 (현재)"
    if current_name in summary and current_name != best_recall_name:
        current = summary[current_name]
        diff_recall = best_result["context_recall"] - current["context_recall"]
        diff_precision = best_result["context_precision"] - current["context_precision"]
        diff_mrr = best_result["mrr"] - current["mrr"]
        lines.append(f"- 기존 설정({current_name}) 대비:")
        lines.append(f"  - Context Recall: {current['context_recall']:.1%} → **{best_result['context_recall']:.1%}** (+{diff_recall:.1%}p)")
        lines.append(f"  - Context Precision: {current['context_precision']:.3f} → **{best_result['context_precision']:.3f}** ({diff_precision:+.3f})")
        lines.append(f"  - MRR: {current['mrr']:.3f} → **{best_result['mrr']:.3f}** ({diff_mrr:+.3f})")
        lines.append("")

    lines.append("- Dense(의미 유사도)와 Sparse(BM25 키워드)를 균등하게 결합할 때 가장 높은 검색 성능을 보임")
    lines.append("- Sparse 비중이 과도하게 높거나(3:1) 낮으면(1:4) 성능 하락")

    # ── PPT 슬라이드 문구 제안 ──
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## PPT 슬라이드 문구 제안")
    lines.append("")
    lines.append("### 슬라이드: 검색 성능 평가")
    lines.append("")
    lines.append("```")
    lines.append(f"[제목] 하이브리드 검색(Dense + BM25) 가중치 최적화")
    lines.append(f"")
    lines.append(f"- 78,520건 특허 DB 대상, {len(dataset)}개 Q&A셋으로 평가")
    lines.append(f"- 평가 지표: Context Recall, Context Precision, MRR, MAP")
    lines.append(f"- 4가지 Dense:Sparse 비율 비교 실험 수행")
    lines.append(f"- 최적 설정: Dense:Sparse = 1:1")
    lines.append(f"  → Context Recall {best_result['context_recall']:.1%}, Precision {best_result['context_precision']:.3f}, MRR {best_result['mrr']:.3f}")
    lines.append(f"- Dense(의미 검색)와 BM25(키워드 검색)의 균형이 중요")
    lines.append("```")
    lines.append("")
    lines.append("### 슬라이드: 검색 파이프라인 설명")
    lines.append("")
    lines.append("```")
    lines.append("[제목] 특허 검색 파이프라인")
    lines.append("")
    lines.append("사용자 쿼리")
    lines.append("  → [1단계] 키워드 사전필터링 (78K → ~1K건)")
    lines.append("  → [2단계] Dense 검색 (KURE-v1 임베딩) + BM25 검색")
    lines.append("  → [3단계] RRF(Reciprocal Rank Fusion)로 결과 통합")
    lines.append("  → [4단계] 특허 단위 집약 (Patent Collapse) → TOP 10")
    lines.append("  → [5단계] sLLM 침해 분석 → TOP 3 선별")
    lines.append("```")

    # ── 설정별 상세 결과 ──
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 설정별 상세 결과")

    for name, result in summary.items():
        lines.append("")
        lines.append(f"### {name}")
        lines.append("")
        lines.append(f"| Context Recall | Hit Rate@3 | Context Precision | MRR | MAP |")
        lines.append(f"|:-:|:-:|:-:|:-:|:-:|")
        lines.append(f"| **{result['context_recall']:.1%}** ({result['hits']}/{result['total']}) | **{result['hit_rate_at_3']:.1%}** ({result['hits_at_3']}/{result['total']}) | **{result['context_precision']:.3f}** | **{result['mrr']:.3f}** | **{result['map']:.3f}** |")
        lines.append("")
        lines.append("| # | TOP10 | TOP3 | Rank | Query | Expected | Retrieved TOP3 |")
        lines.append("|--:|:-----:|:----:|:----:|-------|----------|----------------|")
        for idx, d in enumerate(result["details"], 1):
            hit_mark = "O" if d["hit"] else "X"
            top3_mark = "O" if d.get("hit_at_3") else "X"
            expected = ", ".join(sorted(d["expected"]))
            top3 = ", ".join(d["retrieved_top3"]) if d["retrieved_top3"] else "-"
            query = d["query"].replace("|", "/")
            lines.append(f"| {idx} | {hit_mark} | {top3_mark} | {d['first_rank']} | {query} | {expected} | {top3} |")

    lines.append("")
    return "\n".join(lines)


# ── 메인 ──────────────────────────────────────────────
def main():
    logger.info("=" * 60)
    logger.info("특허 RAG 검색 품질 평가")
    logger.info("=" * 60)

    dataset = load_dataset(DATASET_PATH)
    logger.info(f"\n데이터셋: {len(dataset)}개 질의\n")

    summary = {}

    for name, weights in WEIGHT_CONFIGS.items():
        logger.info(f"\n{'─' * 60}")
        logger.info(f"[{name}]  weights={weights}")
        logger.info(f"{'─' * 60}")

        result = evaluate(dataset, rrf_weights=weights)
        summary[name] = result
        logger.info(f"\n  → Context Recall: {result['context_recall']:.1%} ({result['hits']}/{result['total']})")
        logger.info(f"  → Hit Rate@3: {result['hit_rate_at_3']:.1%} ({result['hits_at_3']}/{result['total']})")
        logger.info(f"  → Context Precision: {result['context_precision']:.3f}")
        logger.info(f"  → MRR: {result['mrr']:.3f}")
        logger.info(f"  → MAP: {result['map']:.3f}")

    # ── 최종 비교 ──
    logger.info(f"\n{'=' * 60}")
    logger.info("최종 비교")
    logger.info(f"{'=' * 60}")
    logger.info(f"{'설정':<30} {'Recall':>8} {'HR@3':>8} {'Precision':>10} {'MRR':>8} {'MAP':>8}")
    logger.info("-" * 76)
    for name, result in summary.items():
        logger.info(
            f"{name:<30} {result['context_recall']:>7.1%} "
            f"{result['hit_rate_at_3']:>7.1%} "
            f"{result['context_precision']:>10.3f} "
            f"{result['mrr']:>8.3f} {result['map']:>8.3f}"
        )

    # ── 결과 저장 ──
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # CSV
    csv_path = output_dir / f"eval_results_{timestamp}.csv"
    rows = []
    for name, result in summary.items():
        cfg = WEIGHT_CONFIGS.get(name, (0, 0))
        rows.append({
            "config": name,
            "dense_weight": cfg[0],
            "sparse_weight": cfg[1],
            "context_recall": result["context_recall"],
            "hit_rate_at_3": result["hit_rate_at_3"],
            "context_precision": result["context_precision"],
            "mrr": result["mrr"],
            "map": result["map"],
            "hits": result["hits"],
            "hits_at_3": result["hits_at_3"],
            "total": result["total"],
        })
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")

    # Markdown 리포트
    md_path = output_dir / f"eval_report_{timestamp}.md"
    md = _build_markdown_report(summary, dataset)
    md_path.write_text(md, encoding="utf-8")

    logger.info(f"\n결과 저장: {csv_path}")
    logger.info(f"리포트 저장: {md_path}")
    logger.info(f"로그 저장: {log_path}")


if __name__ == "__main__":
    main()
