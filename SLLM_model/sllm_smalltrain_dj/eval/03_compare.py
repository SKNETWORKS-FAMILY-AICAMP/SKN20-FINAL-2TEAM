"""Step 3: 두 모델 비교 리포트 생성.

02_evaluate.py의 결과 파일(eval_detail_*.xlsx) 두 개를 받아
나란히 비교하는 마크다운 리포트를 생성한다.

사용법:
    python 03_compare.py \
        --model_a output/eval_detail_gemma.xlsx \
        --model_b output/eval_detail_qwen.xlsx

출력:
    output/eval_summary.md
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from sklearn.metrics import classification_report

sys.path.insert(0, str(Path(__file__).parent))
from common import LABELS


def build_report(da: pd.DataFrame, db: pd.DataFrame, na: str, nb: str) -> str:
    """두 모델 비교 마크다운 리포트."""
    total = len(da)
    lines = []

    lines.append("# sLLM 모델 비교 평가 리포트\n")
    lines.append(f"- 평가 일시: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"- 테스트: {total}건")
    lines.append(f"- 모델: {na} vs {nb}\n")

    # --- 1. 전체 정확도 ---
    acc_a = (da["일치여부"] == "O").sum() / total
    acc_b = (db["일치여부"] == "O").sum() / total
    fail_a = (da["예측라벨"] == "매핑실패").sum()
    fail_b = (db["예측라벨"] == "매핑실패").sum()

    lines.append("## 1. 전체 정확도\n")
    lines.append(f"| 항목 | {na} | {nb} |")
    lines.append("|------|---------|---------|")
    lines.append(f"| 정확도 | {acc_a:.1%} | {acc_b:.1%} |")
    lines.append(f"| 매핑실패 | {fail_a}건 | {fail_b}건 |\n")

    # --- 2. 라벨별 성능 ---
    rep_a = classification_report(da["정답라벨"], da["예측라벨"], labels=LABELS, output_dict=True, zero_division=0)
    rep_b = classification_report(db["정답라벨"], db["예측라벨"], labels=LABELS, output_dict=True, zero_division=0)

    lines.append("## 2. 라벨별 성능\n")
    lines.append(f"| 라벨 | {na} F1 | {nb} F1 | {na} P | {nb} P | {na} R | {nb} R |")
    lines.append("|------|--------|--------|-------|-------|-------|-------|")
    for lb in LABELS:
        a, b = rep_a.get(lb, {}), rep_b.get(lb, {})
        lines.append(
            f"| {lb} "
            f"| {a.get('f1-score',0):.3f} | {b.get('f1-score',0):.3f} "
            f"| {a.get('precision',0):.3f} | {b.get('precision',0):.3f} "
            f"| {a.get('recall',0):.3f} | {b.get('recall',0):.3f} |"
        )
    ma, mb = rep_a.get("macro avg", {}), rep_b.get("macro avg", {})
    lines.append(
        f"| **macro** "
        f"| **{ma.get('f1-score',0):.3f}** | **{mb.get('f1-score',0):.3f}** "
        f"| **{ma.get('precision',0):.3f}** | **{mb.get('precision',0):.3f}** "
        f"| **{ma.get('recall',0):.3f}** | **{mb.get('recall',0):.3f}** |"
    )
    lines.append("")

    # --- 3. 구조 출력 성공률 ---
    sec_a = (da["섹션완성"] == "O").sum()
    sec_b = (db["섹션완성"] == "O").sum()
    tbl_a = (da["테이블파싱"] == "O").sum()
    tbl_b = (db["테이블파싱"] == "O").sum()

    lines.append("## 3. 구조 출력 성공률\n")
    lines.append(f"| 항목 | {na} | {nb} |")
    lines.append("|------|---------|---------|")
    lines.append(f"| 섹션 완성 | {sec_a}/{total} ({sec_a/total:.1%}) | {sec_b}/{total} ({sec_b/total:.1%}) |")
    lines.append(f"| 테이블 파싱 | {tbl_a}/{total} ({tbl_a/total:.1%}) | {tbl_b}/{total} ({tbl_b/total:.1%}) |\n")

    # --- 4. 법리 일관성 ---
    def _logic_stats(d):
        checkable = d[d["법리일관성"] != "-"]
        if len(checkable) == 0:
            return 0, 0
        ok = (checkable["법리일관성"] == "O").sum()
        return ok, len(checkable)

    lok_a, ltot_a = _logic_stats(da)
    lok_b, ltot_b = _logic_stats(db)

    lines.append("## 4. 법리 일관성\n")
    lines.append("라벨과 대응분석표의 논리적 정합성 (침해+미대응=X, 비침해+전부대응=X, 전문가+균등내재성없음=X)\n")
    lines.append(f"| 항목 | {na} | {nb} |")
    lines.append("|------|---------|---------|")
    if ltot_a > 0:
        lines.append(f"| 일관성 | {lok_a}/{ltot_a} ({lok_a/ltot_a:.1%}) | {lok_b}/{ltot_b} ({lok_b/ltot_b:.1%}) |\n")
    else:
        lines.append("| 일관성 | N/A | N/A |\n")

    # --- 5. 구성요소 행 수 일치율 ---
    va = da[da["행수일치"] != "-"]
    vb = db[db["행수일치"] != "-"]
    ma_r = (va["행수일치"] == "O").sum() if len(va) > 0 else 0
    mb_r = (vb["행수일치"] == "O").sum() if len(vb) > 0 else 0

    lines.append("## 5. 구성요소 행 수 일치율\n")
    lines.append(f"| 항목 | {na} | {nb} |")
    lines.append("|------|---------|---------|")
    if len(va) > 0:
        lines.append(f"| 일치율 | {ma_r}/{len(va)} ({ma_r/len(va):.1%}) | {mb_r}/{len(vb)} ({mb_r/len(vb):.1%}) |\n")
    else:
        lines.append("| 일치율 | N/A | N/A |\n")

    # --- 6. 종합 ---
    lines.append("## 6. 종합\n")
    lines.append(f"| 평가 항목 | {na} | {nb} |")
    lines.append("|-----------|---------|---------|")
    lines.append(f"| 라벨 정확도 | {acc_a:.1%} | {acc_b:.1%} |")
    lines.append(f"| 구조 성공률 | {sec_a/total:.1%} | {sec_b/total:.1%} |")
    if ltot_a > 0:
        lines.append(f"| 법리 일관성 | {lok_a/ltot_a:.1%} | {lok_b/ltot_b:.1%} |")
    if len(va) > 0:
        lines.append(f"| 행수 일치율 | {ma_r/len(va):.1%} | {mb_r/len(vb):.1%} |")
    lines.append(f"| 매핑실패 | {fail_a}건 | {fail_b}건 |")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Step 3: 두 모델 비교")
    parser.add_argument("--model_a", required=True, help="모델 A 평가 상세 (eval_detail_*.xlsx)")
    parser.add_argument("--model_b", required=True, help="모델 B 평가 상세 (eval_detail_*.xlsx)")
    parser.add_argument("--model_a_name", default="gemma")
    parser.add_argument("--model_b_name", default="qwen")
    parser.add_argument("--output_dir", default="./output")
    args = parser.parse_args()

    print(f"=== 모델 비교: {args.model_a_name} vs {args.model_b_name} ===\n")

    da = pd.read_excel(args.model_a)
    db = pd.read_excel(args.model_b)
    print(f"  {args.model_a_name}: {len(da)}건")
    print(f"  {args.model_b_name}: {len(db)}건")

    report = build_report(da, db, args.model_a_name, args.model_b_name)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "eval_summary.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(report)
    print(f"\n  저장: {report_path}")


if __name__ == "__main__":
    main()
