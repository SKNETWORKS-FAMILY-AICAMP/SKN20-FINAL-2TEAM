"""
FTO sLLM 추론 모듈
HuggingFace Inference API를 사용하여 특허 침해 분석
"""

import os
from typing import Dict, Any, Optional
from huggingface_hub import InferenceClient


# HuggingFace 모델 ID
MODELS = {
    "1.5b": "itsbini/qwen2.5-1.5b-fto",
    "3b": "itsbini/qwen2.5-3b-fto",
    "14b": "itsbini/qwen2.5-14b-fto",  # 가장 성능 좋음
}

DEFAULT_MODEL = "14b"


class FTOAnalyzer:
    """FTO 침해 분석기"""

    def __init__(self, model_size: str = DEFAULT_MODEL, hf_token: Optional[str] = None):
        """
        Args:
            model_size: 모델 크기 ("1.5b", "3b", "14b")
            hf_token: HuggingFace API 토큰 (없으면 환경변수에서 읽음)
        """
        self.model_id = MODELS.get(model_size, MODELS[DEFAULT_MODEL])
        self.hf_token = hf_token or os.getenv("HF_TOKEN")
        self.client = InferenceClient(token=self.hf_token)

    def analyze(
        self,
        user_product: str,
        claim_text: str,
        components: str,
        patent_id: str = ""
    ) -> Dict[str, Any]:
        """
        특허 침해 분석 수행

        Args:
            user_product: 사용자 제품 설명
            claim_text: 특허 청구항 텍스트
            components: 청구항 구성요소
            patent_id: 특허 ID

        Returns:
            분석 결과 딕셔너리
        """
        prompt = self._build_prompt(user_product, claim_text, components)

        try:
            response = self.client.text_generation(
                prompt,
                model=self.model_id,
                max_new_tokens=1024,
                temperature=0.1,
                do_sample=True,
            )

            result = self._parse_response(response, patent_id)
            return result

        except Exception as e:
            return {
                "patent_id": patent_id,
                "label": "오류",
                "risk_level": "unknown",
                "decision_reason": f"분석 중 오류 발생: {str(e)}",
                "comparisons": []
            }

    def _build_prompt(self, user_product: str, claim_text: str, components: str) -> str:
        """분석용 프롬프트 생성"""
        prompt = f"""당신은 특허 침해 분석 전문가입니다. 사용자 제품이 특허 청구항을 침해하는지 분석해주세요.

## 사용자 제품
{user_product}

## 특허 청구항
{claim_text}

## 청구항 구성요소
{components}

## 분석 지침
1. 각 구성요소별로 사용자 제품과 대응 여부를 분석하세요.
2. 모든 구성요소가 대응되면 "침해", 일부만 대응되면 "애매", 대응되지 않으면 "비침해"로 판단하세요.
3. 전문가 검토가 필요한 경우 "침해_전문가"로 판단하세요.

## 응답 형식
◆구성 대비◆
| 번호 | 특허 구성요소 | 사용자 제품 대응 | 대응 여부 |
|-----|-------------|----------------|----------|
| 1 | ... | ... | O/X/△ |

◆판단◆
[상세 판단 근거]

◆결론◆
[침해/비침해/애매/침해_전문가]
"""
        return prompt

    def _parse_response(self, response: str, patent_id: str) -> Dict[str, Any]:
        """응답 파싱"""
        # 결론 추출
        label = "애매"  # 기본값
        if "◆결론◆" in response:
            conclusion = response.split("◆결론◆")[-1].strip()
            if "비침해" in conclusion:
                label = "비침해"
            elif "침해_전문가" in conclusion:
                label = "침해_전문가"
            elif "침해" in conclusion:
                label = "침해"
            elif "애매" in conclusion:
                label = "애매"

        # 리스크 레벨 매핑
        risk_map = {
            "침해": "high",
            "침해_전문가": "high",
            "애매": "medium",
            "비침해": "low"
        }

        return {
            "patent_id": patent_id,
            "label": label,
            "risk_level": risk_map.get(label, "medium"),
            "decision_reason": response,
            "raw_response": response
        }


# 간편 함수
def analyze_infringement(
    user_product: str,
    claim_text: str,
    components: str,
    patent_id: str = "",
    model_size: str = DEFAULT_MODEL
) -> Dict[str, Any]:
    """
    특허 침해 분석 (간편 함수)

    Example:
        result = analyze_infringement(
            user_product="아목시실린 성분의 항생제",
            claim_text="청구항 1. 아목시실린을 포함하는 약학적 조성물",
            components="1. 아목시실린\n2. 약학적 조성물",
            patent_id="1020050108737"
        )
        print(result["label"])  # "침해" 또는 "비침해" 등
    """
    analyzer = FTOAnalyzer(model_size=model_size)
    return analyzer.analyze(user_product, claim_text, components, patent_id)
