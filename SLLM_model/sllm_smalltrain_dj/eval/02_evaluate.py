"""Step 2: 단일 모델 자동 평가.

추론 결과 파일(infer_*.xlsx)을 받아 4가지 항목을 평가한다.
  1) 결론 라벨 정확도 (classification_report)
  2) 섹션 구조 완성도 (◆구성 대비◆, ◆판단◆, ◆결론◆)
  3) 구성요소 행 수 일치율
  4) 법리 일관성 (라벨 vs 대응분석표 논리 정합성)

사용법:
    python 02_evaluate.py --input output/infer_gemma.xlsx --model_name gemma
    python 02_evaluate.py --input output/infer_qwen.xlsx --model_name qwen

출력:
    output/eval_detail_gemma.xlsx
    output/eval_detail_qwen.xlsx
"""

import argparse
import sys
from pathlib import Path

import pandas as pd
from sklearn.metrics import classification_report

sys.path.insert(0, str(Path(__file__).parent))
from common import (
    LABELS, extract_label, check_sections, check_forbidden,
    count_table_rows, check_logic_consistency,
)


def evaluate(df: pd.DataFrame) -> pd.DataFrame:
    """평가 수행 → 상세 결과 DataFrame 반환."""
    rows = []
    for _, r in df.iterrows():
        pred = r["pred_output"]
        true_out = r["output_form"]

        pred_label = extract_label(pred)
        sec = check_sections(pred)
        true_rows = count_table_rows(true_out)
        pred_rows = count_table_rows(pred)
        logic = check_logic_consistency(pred_label, pred)

        rows.append({
            "apply_num": r["apply_num"],
            "정답라벨": r["label"],
            "예측라벨": pred_label,
            "일치여부": "O" if r["label"] == pred_label else "X",
            "섹션완성": "O" if all(sec.values()) else "X",
            "테이블파싱": "O" if pred_rows > 0 else "X",
            "정답행수": true_rows,
            "예측행수": pred_rows,
            "행수일치": "O" if (true_rows == pred_rows and true_rows > 0) else ("X" if true_rows > 0 else "-"),
            "법리일관성": logic,
        })

    return pd.DataFrame(rows)


def print_summary(detail: pd.DataFrame, df: pd.DataFrame):
    """평가 결과 요약 출력."""
    total = len(detail)

    # 1) 라벨 정확도
    acc = (detail["일치여부"] == "O").sum() / total
    fail = (detail["예측라벨"] == "매핑실패").sum()
    print(f"\n[라벨 정확도] {acc:.1%} (매핑실패: {fail}건)")
    print(classification_report(
        detail["정답라벨"], detail["예측라벨"],
        labels=LABELS, zero_division=0,
    ))

    # 2) 구조
    sec_ok = (detail["섹션완성"] == "O").sum()
    tbl_ok = (detail["테이블파싱"] == "O").sum()
    print(f"[구조] 섹션완성: {sec_ok}/{total} ({sec_ok/total:.1%}), 테이블파싱: {tbl_ok}/{total} ({tbl_ok/total:.1%})")

    # 3) 행 수 일치
    valid = detail[detail["행수일치"] != "-"]
    if len(valid) > 0:
        match = (valid["행수일치"] == "O").sum()
        print(f"[행수일치] {match}/{len(valid)} ({match/len(valid):.1%})")

    # 4) 법리 일관성
    checkable = detail[detail["법리일관성"] != "-"]
    if len(checkable) > 0:
        logic_ok = (checkable["법리일관성"] == "O").sum()
        logic_fail = len(checkable) - logic_ok
        print(f"[법리일관성] {logic_ok}/{len(checkable)} ({logic_ok/len(checkable):.1%})")
        if logic_fail > 0:
            fails = checkable[checkable["법리일관성"] != "O"]["법리일관성"]
            for reason, cnt in fails.value_counts().items():
                print(f"  {reason}: {cnt}건")

    # 참고: 금지문구
    fb_cnt = sum(1 for _, r in df.iterrows() if check_forbidden(r["pred_output"]))
    if fb_cnt > 0:
        print(f"\n[참고] 금지문구 위반: {fb_cnt}건")


def main():
    parser = argparse.ArgumentParser(description="Step 2: 단일 모델 평가")
    parser.add_argument("--input", required=True, help="추론 결과 파일 (infer_*.xlsx)")
    parser.add_argument("--model_name", required=True, help="모델 이름 (gemma / qwen)")
    parser.add_argument("--output_dir", default="./output")
    args = parser.parse_args()

    print(f"=== 모델 평가: {args.model_name} ===")

    df = pd.read_excel(args.input)
    if "pred_output" not in df.columns:
        print("[X] pred_output 컬럼 없음. 01_infer.py를 먼저 실행하세요.")
        sys.exit(1)

    print(f"  입력: {args.input} ({len(df)}건)")

    detail = evaluate(df)
    print_summary(detail, df)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"eval_detail_{args.model_name}.xlsx"
    detail.to_excel(out_path, index=False)
    print(f"\n  저장: {out_path}")


if __name__ == "__main__":
    main()
