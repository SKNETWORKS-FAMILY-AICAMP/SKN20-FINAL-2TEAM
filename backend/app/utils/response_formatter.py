from typing import Dict, Any, List, Optional


def format_response(data: Dict[str, Any]) -> str:
    """
    sLLM JSON 출력 → 사용자 표시용 테이블 형식 변환

    입력 예시:
    {
        "regit_num": "1029170800000",
        "comparisons": [
            {"patent_element": "성분A", "user_product_element": "성분A", "match": "대응"},
            {"patent_element": "제품유형", "user_product_element": "앰플", "match": "대응"}
        ],
        "risk_level": "높음",
        "decision_reason": "사용자의 제품 구성은..."
    }

    출력 예시:
    특허번호 1029170800000의 특허 구성과 사용자가 실시하고자 하는 제품의 구성을 비교한 결과는 다음과 같습니다.

    [구성 대비]
    | 특허 구성 | 사용자 제품 구성 | 대응 여부 |
    |-----------|------------------|-----------|
    | 성분A | 성분A | 대응 |
    | 제품유형 | 앰플 | 대응 |

    [판단]
    사용자의 제품 구성은...
    """
    if not data:
        return "분석 결과가 없습니다."

    regit_num = data.get("regit_num", "알 수 없음")
    comparisons = data.get("comparisons", [])
    decision_reason = data.get("decision_reason", "")
    risk_level = data.get("risk_level", "")

    lines = []

    # 헤더
    lines.append(f"특허번호 {regit_num}의 특허 구성과 사용자가 실시하고자 하는 제품의 구성을 비교한 결과는 다음과 같습니다.")
    lines.append("")

    # 구성 대비 테이블
    if comparisons:
        lines.append("[구성 대비]")
        lines.append("| 특허 구성 | 사용자 제품 구성 | 대응 여부 |")
        lines.append("|-----------|------------------|-----------|")

        for comp in comparisons:
            pe = comp.get("patent_element", "-")
            upe = comp.get("user_product_element") or "확인 불가"
            match = comp.get("match", "판단불가")
            lines.append(f"| {pe} | {upe} | {match} |")

        lines.append("")

    # 위험도
    if risk_level:
        risk_text = _get_risk_text(risk_level)
        lines.append(f"[위험도] {risk_text}")
        lines.append("")

    # 판단
    if decision_reason:
        lines.append("[판단]")
        # 특허번호 치환
        formatted_reason = decision_reason.replace("해당 특허를", f"해당 특허 {regit_num}를")
        lines.append(formatted_reason)

    return "\n".join(lines)


def _get_risk_text(risk_level: str) -> str:
    """위험도 텍스트 변환"""
    risk_map = {
        "high": "높음 ⚠️",
        "medium": "중간 ⚡",
        "low": "낮음 ✅",
        "높음": "높음 ⚠️",
        "중간": "중간 ⚡",
        "낮음": "낮음 ✅",
        "애매": "중간 ⚡"
    }
    return risk_map.get(risk_level.lower() if isinstance(risk_level, str) else risk_level, risk_level)


def format_image_response(data: Dict[str, Any]) -> str:
    """
    이미지 분석 결과 → 사용자 표시용 형식 변환
    """
    if not data:
        return "분석 결과가 없습니다."

    risk_level = data.get("risk_level", "low")
    similar_count = data.get("similar_count", 0)
    response = data.get("response", "")
    similar_patents = data.get("similar_patents", [])

    lines = []

    # 기본 응답
    lines.append(response)
    lines.append("")

    # 유사 특허 목록
    if similar_patents:
        lines.append("[유사 디자인 특허]")
        lines.append("| 등록번호 | 명칭 | 유사도 |")
        lines.append("|----------|------|--------|")

        for patent in similar_patents:
            regit_num = patent.get("regit_num", "-")
            title = patent.get("title", "-")
            score = patent.get("similarity_score", 0)
            lines.append(f"| {regit_num} | {title} | {score:.2%} |")

    return "\n".join(lines)
