"""공통 상수 및 유틸리티."""

import re

LABELS = ["침해", "비침해", "애매", "침해_전문가"]

# 라벨 매핑 규칙 (우선순위 순서대로 체크)
# ◆결론◆ 섹션에서만 매칭하여 오탐 방지
LABEL_RULES = [
    ("전문가", "침해_전문가"),         # 1순위: "전문가" 포함
    ("구체적인 실시 정보", "애매"),     # 2순위: OR 조건
    ("추가 정보", "애매"),
    ("가능성이 낮", "비침해"),          # 3순위
    ("가능성이 높", "침해"),            # 4순위
]

FORBIDDEN_WORDS = ["판단됩니다", "판단합니다", "판단되므로", "리스크"]

SECTION_PATTERNS = {
    "구성 대비": re.compile(r"◆\s*구성\s*대비\s*◆"),
    "판단": re.compile(r"◆\s*판단\s*◆"),
    "결론": re.compile(r"◆\s*결론\s*◆"),
}


def _extract_conclusion(text: str) -> str:
    """◆결론◆ 섹션만 추출. 없으면 전체 텍스트 반환."""
    if not isinstance(text, str):
        return ""
    match = SECTION_PATTERNS["결론"].search(text)
    if match:
        return text[match.end():]
    return text


def extract_label(text: str) -> str:
    """모델 출력의 ◆결론◆ 섹션에서 키워드 기반 라벨 매핑.

    우선순위: 전문가 → 애매 → 비침해 → 침해
    """
    conclusion = _extract_conclusion(text)
    if not conclusion:
        return "매핑실패"
    for keyword, label in LABEL_RULES:
        if keyword in conclusion:
            return label
    return "매핑실패"


def check_sections(text: str) -> dict[str, bool]:
    """◆구성 대비◆, ◆판단◆, ◆결론◆ 존재 여부."""
    if not isinstance(text, str):
        return {s: False for s in SECTION_PATTERNS}
    return {name: bool(pat.search(text)) for name, pat in SECTION_PATTERNS.items()}


def count_table_rows(text: str) -> int:
    """마크다운 테이블 데이터 행 수 (헤더/구분선 제외)."""
    if not isinstance(text, str):
        return 0
    count = 0
    found_sep = False
    for line in text.split("\n"):
        s = line.strip()
        if not s.startswith("|"):
            if found_sep:
                break
            continue
        if re.match(r"^\|[\s\-:|]+\|$", s):
            found_sep = True
            continue
        if found_sep:
            count += 1
    return count


def check_forbidden(text: str) -> list[str]:
    """금지 문구 포함 여부."""
    if not isinstance(text, str):
        return []
    return [w for w in FORBIDDEN_WORDS if w in text]


# ============================================================
# 법리 일관성 체크 (규칙 9, 10, 11)
# ============================================================

def parse_correspondences(text: str) -> list[str]:
    """구성대비표에서 대응여부 값 추출.

    테이블 3번째 컬럼(대응여부)을 파싱한다.
    예: ["대응", "대응", "미대응", "미대응(균등)"]
    """
    if not isinstance(text, str):
        return []

    values = []
    found_sep = False
    for line in text.split("\n"):
        s = line.strip()
        if not s.startswith("|"):
            if found_sep:
                break
            continue
        if re.match(r"^\|[\s\-:|]+\|$", s):
            found_sep = True
            continue
        if found_sep:
            cells = [c.strip() for c in s.split("|")]
            cells = [c for c in cells if c]
            if len(cells) >= 3:
                values.append(cells[2])
    return values


def check_logic_consistency(pred_label: str, pred_output: str) -> str:
    """법리 일관성 체크. 라벨과 대응분석표의 논리적 정합성 검증.

    규칙 9:  침해 → "미대응"이 없어야 함
    규칙 10: 비침해 → 전부 "대응"이면 안 됨
    규칙 11: 침해_전문가 → "미대응(균등)" 또는 "미대응(내재성)"이 있어야 함

    Returns:
        "O"  = 일관성 있음
        "X:규칙번호:사유" = 불일치
        "-"  = 체크 불가 (애매/매핑실패 또는 테이블 파싱 불가)
    """
    if pred_label in ("애매", "매핑실패"):
        return "-"

    corrs = parse_correspondences(pred_output)
    if not corrs:
        return "-"

    # 규칙 9: 침해인데 미대응 존재
    if pred_label == "침해":
        has_mismatch = any("미대응" in c for c in corrs)
        if has_mismatch:
            return "X:R9:침해+미대응"

    # 규칙 10: 비침해인데 전부 대응
    if pred_label == "비침해":
        all_match = all(c.strip() == "대응" for c in corrs)
        if all_match:
            return "X:R10:비침해+전부대응"

    # 규칙 11: 침해_전문가인데 균등/내재성 없음
    if pred_label == "침해_전문가":
        has_special = any("균등" in c or "내재성" in c for c in corrs)
        if not has_special:
            return "X:R11:전문가+균등내재성없음"

    return "O"
