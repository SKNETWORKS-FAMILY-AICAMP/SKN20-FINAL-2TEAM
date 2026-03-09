"""모델 추론 결과 15개 규칙 평가 + 1~5점 채점 (Strict / Fine-grained).

plan2_sllm_infer_eval2.md 기준 15개 규칙으로 추론 결과를 평가하고,
Strict(카테고리 가중치) / Fine-grained(단순 개수) 두 가지 점수를 산출한다.

사용법:
    python evals/evaluate_inference.py --input sllm_all/eval/output/infer_qwen14b_ft.xlsx --model_name qwen14b_ft
    python evals/evaluate_inference.py --input data/eval/eval_human_100.xlsx --model_name human_gold --gold

출력:
    evals/output/eval_15rules_{model_name}.xlsx
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from sklearn.metrics import classification_report


# ============================================================
# 상수
# ============================================================

LABELS = ["침해", "비침해", "애매", "침해_전문가"]

CONCLUSION_PHRASES = {
    "침해": "침해 가능성이 높은 것으로 분석됩니다.",
    "비침해": "침해 가능성이 낮은 것으로 분석됩니다.",
    "애매": "침해 여부 분석을 위해 보다 구체적인 실시 정보가 필요합니다.",
    "침해_전문가": "전문가의 추가 검토가 권고됩니다.",
}

FORBIDDEN_WORDS = ["판단됩니다", "판단합니다", "판단되므로", "리스크"]

VALID_CORRESPONDENCE = {"대응", "미대응", "미대응(균등)", "미대응(내재성)", "확인불가"}

LABEL_RULES = [
    ("전문가", "침해_전문가"),
    ("구체적인 실시 정보", "애매"),
    ("추가 정보", "애매"),
    ("가능성이 낮", "비침해"),
    ("가능성이 높", "침해"),
]

SECTION_PATTERNS = {
    "구성 대비": re.compile(r"◆\s*구성\s*대비\s*◆"),
    "판단": re.compile(r"◆\s*판단\s*◆"),
    "결론": re.compile(r"◆\s*결론\s*◆"),
}

COMPONENT_EXCLUDE_WORDS = ["선택된 독립항", "구성요소:", "청구항"]


# ============================================================
# 파싱 유틸리티 (evaluate_dataset.py에서 가져옴)
# ============================================================

def extract_label(text: str) -> str:
    """◆결론◆ 섹션에서 키워드 기반 라벨 매핑."""
    if not isinstance(text, str):
        return "매핑실패"
    match = SECTION_PATTERNS["결론"].search(text)
    conclusion = text[match.end():] if match else text
    if not conclusion:
        return "매핑실패"
    for keyword, label in LABEL_RULES:
        if keyword in conclusion:
            return label
    return "매핑실패"


def parse_sections(text: str) -> dict:
    """◆구성 대비◆, ◆판단◆, ◆결론◆ 섹션 추출."""
    result = {"comparison": "", "judgment": "", "conclusion": ""}
    if not isinstance(text, str):
        return result
    comp_match = SECTION_PATTERNS["구성 대비"].search(text)
    judg_match = SECTION_PATTERNS["판단"].search(text)
    conc_match = SECTION_PATTERNS["결론"].search(text)
    if comp_match and judg_match:
        result["comparison"] = text[comp_match.end():judg_match.start()].strip()
    if judg_match and conc_match:
        result["judgment"] = text[judg_match.end():conc_match.start()].strip()
    if conc_match:
        result["conclusion"] = text[conc_match.end():].strip()
    return result


def parse_table_rows(comparison_text: str) -> list[dict]:
    """구성대비 마크다운 테이블에서 데이터 행 파싱."""
    rows = []
    for line in comparison_text.split("\n"):
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")]
        cells = [c for c in cells if c]
        if len(cells) < 3:
            continue
        if cells[0] in ("특허 구성", "---") or re.match(r"^[-:]+$", cells[0]):
            continue
        rows.append({
            "patent": cells[0],
            "user": cells[1],
            "correspondence": cells[2],
        })
    return rows


def count_components(components_text: str) -> int:
    """구성요소 텍스트에서 순수 구성요소 수 카운팅."""
    if not isinstance(components_text, str) or not components_text.strip():
        return 0
    count = 0
    for line in components_text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        if not re.match(r"^\d+\.\s+", line):
            continue
        if any(word in line for word in COMPONENT_EXCLUDE_WORDS):
            continue
        count += 1
    return count


# ============================================================
# 15개 규칙 (각각 독립적으로 PASS/FAIL 반환)
# ============================================================

def rule_01_label_match(pred_label: str, true_label: str, **_) -> tuple[str, str]:
    """#1 핵심 정확성: 예측 라벨 == 정답 라벨."""
    if pred_label == true_label:
        return "PASS", ""
    return "FAIL", f"예측={pred_label} vs 정답={true_label}"


def rule_02_conclusion_phrase(pred_label: str, sections: dict, **_) -> tuple[str, str]:
    """#2 출력 형식: 라벨별 필수 결론 문구 포함."""
    expected = CONCLUSION_PHRASES.get(pred_label, "")
    if expected and expected in sections["conclusion"]:
        return "PASS", ""
    if not expected:
        return "PASS", ""
    return "FAIL", f"결론에 '{expected}' 없음"


def rule_03_forbidden_words(pred_output: str, **_) -> tuple[str, str]:
    """#3 출력 형식: 금지어 포함 여부."""
    if not isinstance(pred_output, str):
        return "PASS", ""
    found = [w for w in FORBIDDEN_WORDS if w in pred_output]
    if found:
        return "FAIL", f"금지어: {', '.join(found)}"
    return "PASS", ""


def rule_04_uncertain_infringement(pred_label: str, table_rows: list, **_) -> tuple[str, str]:
    """#4 법리: 확인불가 존재 + 침해 라벨."""
    has_uncertain = any(r["correspondence"] == "확인불가" for r in table_rows)
    if has_uncertain and pred_label == "침해":
        return "FAIL", "확인불가 존재 + 침해 라벨"
    return "PASS", ""


def rule_05_correspondence_values(table_rows: list, **_) -> tuple[str, str]:
    """#5 출력 형식: 대응여부 값이 허용된 5개 중 하나인지."""
    invalid = []
    for r in table_rows:
        val = r["correspondence"].strip()
        if val not in VALID_CORRESPONDENCE:
            invalid.append(val)
    if invalid:
        return "FAIL", f"허용되지 않는 값: {', '.join(set(invalid))}"
    return "PASS", ""


def rule_06_table_row_count(components: str, table_rows: list, **_) -> tuple[str, str]:
    """#6 출력 형식: 구성요소 수 vs 테이블 행수 일치."""
    comp_count = count_components(components)
    table_count = len(table_rows)
    if comp_count == 0 and table_count == 0:
        return "PASS", ""
    if comp_count != table_count:
        return "FAIL", f"구성요소 {comp_count}개 vs 테이블 {table_count}행"
    return "PASS", ""


def rule_07_table_header(pred_output: str, **_) -> tuple[str, str]:
    """#7 출력 형식: ◆구성 대비◆ 헤더 존재."""
    if not isinstance(pred_output, str):
        return "FAIL", "출력 비어있음"
    if SECTION_PATTERNS["구성 대비"].search(pred_output):
        return "PASS", ""
    return "FAIL", "◆구성 대비◆ 헤더 없음"


def rule_08_infringement_no_mismatch(pred_label: str, table_rows: list, **_) -> tuple[str, str]:
    """#8 법리: 침해 라벨 + 미대응 존재 → 모순."""
    if pred_label != "침해":
        return "PASS", ""
    mismatches = [r for r in table_rows if r["correspondence"] == "미대응"]
    if mismatches:
        return "FAIL", f"침해 + 미대응 {len(mismatches)}개"
    return "PASS", ""


def rule_09_non_infringement_all_match(pred_label: str, table_rows: list, **_) -> tuple[str, str]:
    """#9 법리: 비침해 라벨 + 전부 대응 → 모순."""
    if pred_label != "비침해":
        return "PASS", ""
    if not table_rows:
        return "PASS", ""
    if all(r["correspondence"] == "대응" for r in table_rows):
        return "FAIL", "비침해 + 전부 대응"
    return "PASS", ""


def rule_10_expert_needs_special(pred_label: str, table_rows: list, **_) -> tuple[str, str]:
    """#10 법리: 침해_전문가 라벨 + 균등/내재성 없음."""
    if pred_label != "침해_전문가":
        return "PASS", ""
    has_special = any(
        r["correspondence"] in ("미대응(균등)", "미대응(내재성)")
        for r in table_rows
    )
    if not has_special:
        return "FAIL", "침해_전문가 + 균등/내재성 없음"
    return "PASS", ""


def rule_11_infringement_has_special(pred_label: str, table_rows: list, **_) -> tuple[str, str]:
    """#11 법리: 침해 라벨 + 균등/내재성 존재 → 전문가여야."""
    if pred_label != "침해":
        return "PASS", ""
    found = [r for r in table_rows if r["correspondence"] in ("미대응(균등)", "미대응(내재성)")]
    if found:
        return "FAIL", f"침해 + 균등/내재성 {len(found)}개"
    return "PASS", ""


def rule_12_expert_has_plain_mismatch(pred_label: str, table_rows: list, **_) -> tuple[str, str]:
    """#12 법리: 침해_전문가 라벨 + 일반 미대응 → 비침해여야."""
    if pred_label != "침해_전문가":
        return "PASS", ""
    plain = [r for r in table_rows if r["correspondence"] == "미대응"]
    if plain:
        return "FAIL", f"침해_전문가 + 일반 미대응 {len(plain)}개"
    return "PASS", ""


def rule_13_non_infringement_only_special(pred_label: str, table_rows: list, **_) -> tuple[str, str]:
    """#13 법리: 비침해 라벨 + 균등/내재성만 → 전문가여야."""
    if pred_label != "비침해":
        return "PASS", ""
    has_plain = any(r["correspondence"] == "미대응" for r in table_rows)
    has_special = any(r["correspondence"] in ("미대응(균등)", "미대응(내재성)") for r in table_rows)
    if has_special and not has_plain:
        return "FAIL", "비침해 + 균등/내재성만 존재"
    return "PASS", ""


def rule_14_judgment_opening(pred_label: str, sections: dict, **_) -> tuple[str, str]:
    """#14 판단 품질: 침해 판단 첫 문장 고정 문구."""
    if pred_label != "침해":
        return "PASS", ""
    expected = "사용자 제품은 특허의 모든 구성요소를 포함하고 있습니다."
    if sections["judgment"].strip().startswith(expected):
        return "PASS", ""
    return "FAIL", "판단 첫 문장 불일치"


def rule_15_judgment_conclusion_dup(sections: dict, **_) -> tuple[str, str]:
    """#15 출력 형식: 판단에 결론 문구 중복."""
    conclusion = sections["conclusion"].strip()
    if conclusion and conclusion in sections["judgment"]:
        return "FAIL", "판단에 결론 문구 중복"
    return "PASS", ""


# 규칙 등록
RULES = {
    1: rule_01_label_match,
    2: rule_02_conclusion_phrase,
    3: rule_03_forbidden_words,
    4: rule_04_uncertain_infringement,
    5: rule_05_correspondence_values,
    6: rule_06_table_row_count,
    7: rule_07_table_header,
    8: rule_08_infringement_no_mismatch,
    9: rule_09_non_infringement_all_match,
    10: rule_10_expert_needs_special,
    11: rule_11_infringement_has_special,
    12: rule_12_expert_has_plain_mismatch,
    13: rule_13_non_infringement_only_special,
    14: rule_14_judgment_opening,
    15: rule_15_judgment_conclusion_dup,
}

RULE_NAMES = {
    1: "라벨일치",
    2: "결론문구",
    3: "금지어",
    4: "확인불가+침해",
    5: "대응여부값",
    6: "행수일치",
    7: "구성대비헤더",
    8: "침해+미대응",
    9: "비침해+전부대응",
    10: "전문가+균등없음",
    11: "침해+균등존재",
    12: "전문가+일반미대응",
    13: "비침해+균등만",
    14: "판단첫문장",
    15: "판단결론중복",
}

# 카테고리 분류
CATEGORY = {
    1: "핵심정확성",
    2: "출력형식", 3: "출력형식", 5: "출력형식", 6: "출력형식", 7: "출력형식", 15: "출력형식",
    4: "법리정확성", 8: "법리정확성", 9: "법리정확성", 10: "법리정확성",
    11: "법리정확성", 12: "법리정확성", 13: "법리정확성",
    14: "판단품질",
}

LEGAL_RULES = {4, 8, 9, 10, 11, 12, 13}
FORMAT_RULES = {2, 3, 5, 6, 7, 15}
JUDGMENT_RULES = {14}

RULE_DESCRIPTIONS = {
    1: "예측 라벨과 정답 라벨 일치 여부",
    2: "라벨별 필수 결론 문구(침해 가능성이 높은/낮은...) 포함",
    3: "금지어(판단됩니다, 리스크 등) 미포함",
    4: "확인불가 존재 시 침해 라벨 불가 (정보 부족 → 단정 금지)",
    5: "대응여부 값이 허용된 5개(대응/미대응/미대응(균등)/미대응(내재성)/확인불가) 중 하나",
    6: "입력 구성요소 수와 테이블 행수 일치",
    7: "◆구성 대비◆ 섹션 헤더 존재",
    8: "침해 라벨 + 미대응 존재 → 구성요소 완비 원칙 위반",
    9: "비침해 라벨 + 전부 대응 → 논리적 모순",
    10: "침해_전문가 라벨에는 균등론/내재성 근거 필수",
    11: "침해 라벨 + 균등/내재성 존재 → 전문가 검토 대상이어야",
    12: "침해_전문가 라벨 + 일반 미대응 → 비침해여야",
    13: "비침해 라벨 + 균등/내재성만 존재 → 전문가 검토 대상이어야",
    14: "침해 시 판단 첫 문장 고정 문구 사용",
    15: "판단 섹션에 결론 문구가 중복되지 않아야",
}


# ============================================================
# 점수 산출
# ============================================================

def calc_strict_score(results: dict[int, str]) -> int:
    """Strict Rubric: 카테고리 가중치 기반 1~5점.

    5점: 라벨 정확 + 15개 전 규칙 PASS
    4점: 라벨 정확 + 출력 형식만 1-2개 FAIL (법리 OK)
    3점: 라벨 정확 + 법리 경미 이슈
    2점: 라벨 오류 OR 심각한 법리 오류 (3개+)
    1점: 라벨 오류 + 구조 파싱 실패 + 법리 오류 복합
    """
    label_ok = results[1] == "PASS"
    legal_fails = sum(1 for r in LEGAL_RULES if results[r] == "FAIL")
    format_fails = sum(1 for r in FORMAT_RULES if results[r] == "FAIL")
    judgment_fails = sum(1 for r in JUDGMENT_RULES if results[r] == "FAIL")
    has_structure = results[7] == "PASS"  # ◆구성 대비◆ 헤더

    if not label_ok:
        # 라벨 틀림: 복합 오류면 1점, 아니면 2점
        if legal_fails >= 1 or not has_structure:
            return 1
        return 2

    # 라벨 맞음
    if legal_fails >= 3:
        return 2  # 심각한 법리 오류
    if legal_fails > 0:
        return 3  # 법리 경미 이슈
    if format_fails > 0 or judgment_fails > 0:
        return 4  # 형식/판단만 이슈
    return 5  # 전부 PASS


def calc_fine_score(results: dict[int, str]) -> int:
    """Fine-grained Rubric: 단순 PASS 개수 기반 1~5점.

    5점: 15/15 PASS
    4점: 13-14개 PASS
    3점: 11-12개 PASS
    2점: 9-10개 PASS
    1점: 8개 이하 PASS
    """
    pass_count = sum(1 for v in results.values() if v == "PASS")
    if pass_count >= 15:
        return 5
    if pass_count >= 13:
        return 4
    if pass_count >= 11:
        return 3
    if pass_count >= 9:
        return 2
    return 1


# ============================================================
# 행 단위 평가
# ============================================================

def evaluate_row(row, output_col: str = "pred_output") -> dict:
    """한 행에 대해 15개 규칙 평가 + Strict/Fine 점수."""
    pred_output = str(row.get(output_col, ""))
    true_label = str(row.get("label", ""))
    components = str(row.get("components", ""))

    # 파싱
    pred_label = extract_label(pred_output)
    sections = parse_sections(pred_output)
    table_rows = parse_table_rows(sections["comparison"])

    # 컨텍스트
    ctx = {
        "pred_label": pred_label,
        "true_label": true_label,
        "pred_output": pred_output,
        "sections": sections,
        "table_rows": table_rows,
        "components": components,
    }

    # 15개 규칙 실행
    results = {}
    reasons = {}
    for rule_num, fn in RULES.items():
        try:
            result, reason = fn(**ctx)
        except Exception as e:
            result, reason = "ERROR", str(e)[:80]
        results[rule_num] = result
        reasons[rule_num] = reason

    strict = calc_strict_score(results)
    fine = calc_fine_score(results)

    return {
        "apply_num": row.get("apply_num", ""),
        "정답라벨": true_label,
        "예측라벨": pred_label,
        **{f"R{i}_{RULE_NAMES[i]}": results[i] for i in range(1, 16)},
        **{f"R{i}_사유": reasons[i] for i in range(1, 16) if reasons[i]},
        "strict_score": strict,
        "fine_score": fine,
        "pass_count": sum(1 for v in results.values() if v == "PASS"),
    }


# ============================================================
# 요약 리포트
# ============================================================

def print_summary(detail: pd.DataFrame, model_name: str):
    """평가 결과 요약 출력."""
    total = len(detail)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    print(f"\n{'=' * 60}")
    print(f"15개 규칙 평가 리포트 — {model_name}")
    print(f"평가 일시: {now} | 총 {total}건")
    print(f"{'=' * 60}")

    # 1) 라벨 정확도
    acc = (detail["R1_라벨일치"] == "PASS").sum()
    print(f"\n[라벨 정확도] {acc}/{total} ({acc/total:.1%})")

    if "정답라벨" in detail.columns and "예측라벨" in detail.columns:
        valid = detail[detail["예측라벨"] != "매핑실패"]
        if len(valid) > 0:
            cr = classification_report(
                valid["정답라벨"], valid["예측라벨"],
                labels=LABELS, zero_division=0,
            )
            print(cr)

    # 2) 규칙별 통과율
    print("[규칙별 통과율]")
    print(f"{'#':>3} {'규칙':<20} {'카테고리':<10} {'PASS':>6} {'FAIL':>6} {'통과율':>8}")
    print("-" * 58)
    for i in range(1, 16):
        col = f"R{i}_{RULE_NAMES[i]}"
        p = (detail[col] == "PASS").sum()
        f = (detail[col] == "FAIL").sum()
        rate = p / (p + f) * 100 if (p + f) > 0 else 0
        print(f"{i:>3} {RULE_NAMES[i]:<20} {CATEGORY[i]:<10} {p:>6} {f:>6} {rate:>7.1f}%")

    # 3) 카테고리별 통과율
    print(f"\n[카테고리별 통과율]")
    for cat_name, rule_ids in [
        ("핵심정확성", {1}),
        ("법리정확성", LEGAL_RULES),
        ("출력형식", FORMAT_RULES),
        ("판단품질", JUDGMENT_RULES),
    ]:
        total_checks = 0
        total_pass = 0
        for rid in rule_ids:
            col = f"R{rid}_{RULE_NAMES[rid]}"
            total_checks += len(detail)
            total_pass += (detail[col] == "PASS").sum()
        rate = total_pass / total_checks * 100 if total_checks > 0 else 0
        print(f"  {cat_name:<12} {total_pass}/{total_checks} ({rate:.1f}%)")

    # 4) Strict / Fine 점수
    print(f"\n[점수 통계]")
    print(f"  Strict    평균: {detail['strict_score'].mean():.2f}  중앙: {detail['strict_score'].median():.1f}")
    print(f"  Fine      평균: {detail['fine_score'].mean():.2f}  중앙: {detail['fine_score'].median():.1f}")

    # 5) Strict 점수 분포
    print(f"\n[Strict 점수 분포]")
    for score in range(5, 0, -1):
        cnt = (detail["strict_score"] == score).sum()
        bar = "█" * (cnt * 40 // total) if total > 0 else ""
        print(f"  {score}점: {cnt:>5}건 ({cnt/total:.1%}) {bar}")

    # 6) Fine 점수 분포
    print(f"\n[Fine-grained 점수 분포]")
    for score in range(5, 0, -1):
        cnt = (detail["fine_score"] == score).sum()
        bar = "█" * (cnt * 40 // total) if total > 0 else ""
        print(f"  {score}점: {cnt:>5}건 ({cnt/total:.1%}) {bar}")

    print(f"\n{'=' * 60}")


def save_markdown_report(detail: pd.DataFrame, model_name: str, out_path: Path):
    """평가 결과를 마크다운 파일로 저장."""
    total = len(detail)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    acc = (detail["R1_라벨일치"] == "PASS").sum()

    lines = []
    lines.append(f"# 15개 규칙 평가 리포트 — {model_name}\n")
    lines.append(f"- 평가 일시: {now}")
    lines.append(f"- 총 건수: {total}건")
    lines.append(f"- 라벨 정확도: {acc}/{total} ({acc/total:.1%})\n")

    # 규칙별 통과율
    lines.append("## 규칙별 통과율\n")
    lines.append("| # | 규칙 | 카테고리 | PASS | FAIL | 통과율 |")
    lines.append("|--:|------|----------|-----:|-----:|-------:|")
    for i in range(1, 16):
        col = f"R{i}_{RULE_NAMES[i]}"
        p = (detail[col] == "PASS").sum()
        f = (detail[col] == "FAIL").sum()
        rate = p / (p + f) * 100 if (p + f) > 0 else 0
        lines.append(f"| {i} | {RULE_NAMES[i]} | {CATEGORY[i]} | {p} | {f} | {rate:.1f}% |")

    # 카테고리별 통과율
    lines.append("\n## 카테고리별 통과율\n")
    lines.append("| 카테고리 | PASS/전체 | 통과율 |")
    lines.append("|----------|----------:|-------:|")
    for cat_name, rule_ids in [
        ("핵심정확성", {1}),
        ("법리정확성", LEGAL_RULES),
        ("출력형식", FORMAT_RULES),
        ("판단품질", JUDGMENT_RULES),
    ]:
        total_checks = 0
        total_pass = 0
        for rid in rule_ids:
            col = f"R{rid}_{RULE_NAMES[rid]}"
            total_checks += len(detail)
            total_pass += (detail[col] == "PASS").sum()
        rate = total_pass / total_checks * 100 if total_checks > 0 else 0
        lines.append(f"| {cat_name} | {total_pass}/{total_checks} | {rate:.1f}% |")

    # 점수 통계
    lines.append("\n## 점수 통계\n")
    lines.append("| 루브릭 | 평균 | 중앙값 |")
    lines.append("|--------|-----:|-------:|")
    lines.append(f"| Strict | {detail['strict_score'].mean():.2f} | {detail['strict_score'].median():.1f} |")
    lines.append(f"| Fine-grained | {detail['fine_score'].mean():.2f} | {detail['fine_score'].median():.1f} |")

    # Strict 점수 분포
    lines.append("\n## Strict 점수 분포\n")
    lines.append("| 점수 | 건수 | 비율 |")
    lines.append("|-----:|-----:|-----:|")
    for score in range(5, 0, -1):
        cnt = (detail["strict_score"] == score).sum()
        lines.append(f"| {score}점 | {cnt}건 | {cnt/total:.1%} |")

    # Fine-grained 점수 분포
    lines.append("\n## Fine-grained 점수 분포\n")
    lines.append("| 점수 | 건수 | 비율 |")
    lines.append("|-----:|-----:|-----:|")
    for score in range(5, 0, -1):
        cnt = (detail["fine_score"] == score).sum()
        lines.append(f"| {score}점 | {cnt}건 | {cnt/total:.1%} |")

    # 법리 정확성 상세
    lines.append("\n## 법리 정확성 상세 (규칙 #4, #8~#13)\n")
    lines.append("법리 규칙은 특허 침해 분석의 논리적 일관성을 검증합니다.\n")
    lines.append("| # | 규칙 | 설명 | PASS | FAIL | 통과율 |")
    lines.append("|--:|------|------|-----:|-----:|-------:|")
    for i in sorted(LEGAL_RULES):
        col = f"R{i}_{RULE_NAMES[i]}"
        p = (detail[col] == "PASS").sum()
        f = (detail[col] == "FAIL").sum()
        rate = p / (p + f) * 100 if (p + f) > 0 else 0
        lines.append(f"| {i} | {RULE_NAMES[i]} | {RULE_DESCRIPTIONS[i]} | {p} | {f} | {rate:.1f}% |")

    # 전체 15개 규칙 설명
    lines.append("\n## 부록: 15개 평가 규칙 설명\n")
    lines.append("| # | 규칙 | 카테고리 | 설명 |")
    lines.append("|--:|------|----------|------|")
    for i in range(1, 16):
        lines.append(f"| {i} | {RULE_NAMES[i]} | {CATEGORY[i]} | {RULE_DESCRIPTIONS[i]} |")

    md_path = out_path.with_suffix(".md")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"MD 리포트: {md_path}")


# ============================================================
# 메인
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="15개 규칙 추론 평가 + 1~5점 채점")
    parser.add_argument("--input", required=True, help="추론 결과 xlsx (pred_output 또는 output_form 컬럼)")
    parser.add_argument("--model_name", required=True, help="모델 이름")
    parser.add_argument("--gold", action="store_true",
                        help="Gold standard 모드: output_form을 평가 대상으로 사용 (사람 검증용)")
    parser.add_argument("--output_dir", default=None, help="출력 디렉토리 (기본: evals/output/)")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"파일을 찾을 수 없습니다: {input_path}")
        sys.exit(1)

    df = pd.read_excel(input_path)
    print(f"입력: {input_path.name} ({len(df)}건)")

    # 평가 대상 컬럼 결정
    if args.gold:
        output_col = "output_form"
        if output_col not in df.columns:
            print(f"'{output_col}' 컬럼이 없습니다.")
            sys.exit(1)
    else:
        output_col = "pred_output"
        if output_col not in df.columns:
            # output_form이 있으면 fallback
            if "output_form" in df.columns:
                output_col = "output_form"
                print(f"pred_output 없음 → output_form 사용")
            else:
                print("pred_output 또는 output_form 컬럼이 필요합니다.")
                sys.exit(1)

    # 평가 실행
    rows = []
    for _, row in df.iterrows():
        rows.append(evaluate_row(row, output_col=output_col))

    detail = pd.DataFrame(rows)

    # 저장
    if args.output_dir:
        out_dir = Path(args.output_dir)
    else:
        out_dir = Path(__file__).resolve().parent / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    out_path = out_dir / f"eval_15rules_{args.model_name}.xlsx"
    detail.to_excel(out_path, index=False)
    print(f"저장: {out_path}")

    # 요약
    print_summary(detail, args.model_name)
    save_markdown_report(detail, args.model_name, out_path)


if __name__ == "__main__":
    main()
