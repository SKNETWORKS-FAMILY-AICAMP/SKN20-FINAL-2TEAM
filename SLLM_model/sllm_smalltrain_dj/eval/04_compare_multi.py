"""Step 4: 여러 모델 비교 리포트 생성.

02_evaluate.py의 결과 파일(eval_detail_*.xlsx) 여러 개를 받아
한 테이블에서 비교하는 마크다운 리포트를 생성한다.

사용법:
    python 04_compare_multi.py \
        --models output/s3/eval_detail_qwen3b_ft.xlsx output/s4/eval_detail_qwen7b_ft.xlsx output/s6/eval_detail_qwen14b_ft.xlsx \
        --names qwen3b_ft qwen7b_ft qwen14b_ft \
        --output output/s6_7b_ft_vs_14b_ft/eval_summary_ft_all.md
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from loguru import logger
from sklearn.metrics import classification_report

# ─── 로깅 설정 ────────────────────────────────────────────
LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
LOG_DIR.mkdir(exist_ok=True)
logger.remove()
logger.add(sys.stderr, level="INFO")
logger.add(
    LOG_DIR / "eval_compare_multi_{time:YYYY-MM-DD_HH-mm-ss}.log",
    level="DEBUG",
    rotation="100 MB",
    encoding="utf-8",
)

sys.path.insert(0, str(Path(__file__).parent))
from common import LABELS


def build_multi_report(dfs: list, names: list) -> str:
    """여러 모델 비교 마크다운 리포트."""
    total = len(dfs[0])
    n = len(names)
    lines = []

    lines.append("# sLLM 모델 비교 평가 리포트 (다중 모델)\n")
    lines.append(f"- 평가 일시: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"- 테스트: {total}건")
    lines.append(f"- 모델: {' vs '.join(names)}\n")

    # --- 1. 전체 정확도 ---
    accs = [(df["일치여부"] == "O").sum() / total for df in dfs]
    fails = [(df["예측라벨"] == "매핑실패").sum() for df in dfs]

    lines.append("## 1. 전체 정확도\n")
    lines.append("| 항목 | " + " | ".join(names) + " |")
    lines.append("|------" + "|--------" * n + "|")
    lines.append("| 정확도 | " + " | ".join(f"{a:.1%}" for a in accs) + " |")
    lines.append("| 매핑실패 | " + " | ".join(f"{f}건" for f in fails) + " |\n")

    # --- 2. 라벨별 성능 ---
    reps = [
        classification_report(df["정답라벨"], df["예측라벨"], labels=LABELS, output_dict=True, zero_division=0)
        for df in dfs
    ]

    lines.append("## 2. 라벨별 F1\n")
    lines.append("| 라벨 | " + " | ".join(names) + " |")
    lines.append("|------" + "|--------" * n + "|")
    for lb in LABELS:
        vals = [r.get(lb, {}).get("f1-score", 0) for r in reps]
        lines.append(f"| {lb} | " + " | ".join(f"{v:.3f}" for v in vals) + " |")
    macros = [r.get("macro avg", {}).get("f1-score", 0) for r in reps]
    lines.append("| **macro** | " + " | ".join(f"**{v:.3f}**" for v in macros) + " |")
    lines.append("")

    # --- 3. 라벨별 Precision ---
    lines.append("## 3. 라벨별 Precision\n")
    lines.append("| 라벨 | " + " | ".join(names) + " |")
    lines.append("|------" + "|--------" * n + "|")
    for lb in LABELS:
        vals = [r.get(lb, {}).get("precision", 0) for r in reps]
        lines.append(f"| {lb} | " + " | ".join(f"{v:.3f}" for v in vals) + " |")
    macros_p = [r.get("macro avg", {}).get("precision", 0) for r in reps]
    lines.append("| **macro** | " + " | ".join(f"**{v:.3f}**" for v in macros_p) + " |")
    lines.append("")

    # --- 4. 라벨별 Recall ---
    lines.append("## 4. 라벨별 Recall\n")
    lines.append("| 라벨 | " + " | ".join(names) + " |")
    lines.append("|------" + "|--------" * n + "|")
    for lb in LABELS:
        vals = [r.get(lb, {}).get("recall", 0) for r in reps]
        lines.append(f"| {lb} | " + " | ".join(f"{v:.3f}" for v in vals) + " |")
    macros_r = [r.get("macro avg", {}).get("recall", 0) for r in reps]
    lines.append("| **macro** | " + " | ".join(f"**{v:.3f}**" for v in macros_r) + " |")
    lines.append("")

    # --- 5. 구조 출력 성공률 ---
    secs = [(df["섹션완성"] == "O").sum() for df in dfs]
    tbls = [(df["테이블파싱"] == "O").sum() for df in dfs]

    lines.append("## 5. 구조 출력 성공률\n")
    lines.append("| 항목 | " + " | ".join(names) + " |")
    lines.append("|------" + "|--------" * n + "|")
    lines.append("| 섹션 완성 | " + " | ".join(f"{s}/{total} ({s/total:.1%})" for s in secs) + " |")
    lines.append("| 테이블 파싱 | " + " | ".join(f"{t}/{total} ({t/total:.1%})" for t in tbls) + " |\n")

    # --- 6. 법리 일관성 ---
    def _logic_stats(d):
        checkable = d[d["법리일관성"] != "-"]
        if len(checkable) == 0:
            return 0, 0
        ok = (checkable["법리일관성"] == "O").sum()
        return ok, len(checkable)

    logic_stats = [_logic_stats(df) for df in dfs]

    lines.append("## 6. 법리 일관성\n")
    lines.append("| 항목 | " + " | ".join(names) + " |")
    lines.append("|------" + "|--------" * n + "|")
    logic_vals = []
    for ok, tot in logic_stats:
        logic_vals.append(f"{ok}/{tot} ({ok/tot:.1%})" if tot > 0 else "N/A")
    lines.append("| 일관성 | " + " | ".join(logic_vals) + " |\n")

    # --- 7. 구성요소 행 수 일치율 ---
    def _row_stats(d):
        v = d[d["행수일치"] != "-"]
        if len(v) == 0:
            return 0, 0
        return (v["행수일치"] == "O").sum(), len(v)

    row_stats = [_row_stats(df) for df in dfs]

    lines.append("## 7. 구성요소 행 수 일치율\n")
    lines.append("| 항목 | " + " | ".join(names) + " |")
    lines.append("|------" + "|--------" * n + "|")
    row_vals = []
    for ok, tot in row_stats:
        row_vals.append(f"{ok}/{tot} ({ok/tot:.1%})" if tot > 0 else "N/A")
    lines.append("| 일치율 | " + " | ".join(row_vals) + " |\n")

    # --- 8. 종합 ---
    lines.append("## 8. 종합\n")
    lines.append("| 평가 항목 | " + " | ".join(names) + " |")
    lines.append("|-----------" + "|--------" * n + "|")
    lines.append("| 라벨 정확도 | " + " | ".join(f"{a:.1%}" for a in accs) + " |")
    lines.append("| 구조 성공률 | " + " | ".join(f"{s/total:.1%}" for s in secs) + " |")
    logic_pcts = []
    for ok, tot in logic_stats:
        logic_pcts.append(f"{ok/tot:.1%}" if tot > 0 else "N/A")
    lines.append("| 법리 일관성 | " + " | ".join(logic_pcts) + " |")
    row_pcts = []
    for ok, tot in row_stats:
        row_pcts.append(f"{ok/tot:.1%}" if tot > 0 else "N/A")
    lines.append("| 행수 일치율 | " + " | ".join(row_pcts) + " |")
    lines.append("| 매핑실패 | " + " | ".join(f"{f}건" for f in fails) + " |")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Step 4: 다중 모델 비교")
    parser.add_argument("--models", nargs="+", required=True, help="eval_detail 파일 경로들")
    parser.add_argument("--names", nargs="+", required=True, help="모델 이름들")
    parser.add_argument("--output", default="./output/eval_summary_multi.md", help="출력 파일 경로")
    args = parser.parse_args()

    if len(args.models) != len(args.names):
        logger.error("--models 과 --names 개수가 일치하지 않습니다.")
        sys.exit(1)

    logger.info(f"=== 다중 모델 비교: {' vs '.join(args.names)} ===")

    dfs = []
    for path, name in zip(args.models, args.names):
        df = pd.read_excel(path)
        logger.info(f"{name}: {len(df)}건")
        dfs.append(df)

    report = build_multi_report(dfs, args.names)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)

    logger.info(f"\n{report}")
    logger.success(f"비교 완료! 저장: {out_path}")


if __name__ == "__main__":
    main()
