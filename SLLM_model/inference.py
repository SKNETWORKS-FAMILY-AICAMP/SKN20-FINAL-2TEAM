"""
FTO sLLM 추론 모듈
vLLM 서버를 사용하여 특허 침해 분석
"""

import os
from typing import Dict, Any, Optional
from openai import OpenAI


VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1")
MODEL_NAME = "/workspace/qwen2.5-14b-fto-merged"


class FTOAnalyzer:
    """FTO 침해 분석기"""

    def __init__(self, model_size: str = "14b", hf_token: Optional[str] = None):
        self.client = OpenAI(
            base_url=VLLM_BASE_URL,
            api_key="dummy"  # vLLM은 API 키 불필요
        )

    def analyze(
        self,
        user_product: str,
        claim_text: str,
        components: str,
        patent_id: str = ""
    ) -> Dict[str, Any]:
        prompt = self._build_prompt(user_product, claim_text, components)

        try:
            response = self.client.completions.create(
                model=MODEL_NAME,
                prompt=prompt,
                max_tokens=1024,
                temperature=0.1,
            )
            result_text = response.choices[0].text
            return self._parse_response(result_text, patent_id)

        except Exception as e:
            return {
                "patent_id": patent_id,
                "label": "오류",
                "risk_level": "unknown",
                "decision_reason": f"분석 중 오류 발생: {str(e)}",
                "comparisons": []
            }

    def _build_prompt(self, user_product: str, claim_text: str, components: str) -> str:
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
        label = "애매"
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


def analyze_infringement(
    user_product: str,
    claim_text: str,
    components: str,
    patent_id: str = "",
    model_size: str = "14b"
) -> Dict[str, Any]:
    analyzer = FTOAnalyzer()
    return analyzer.analyze(user_product, claim_text, components, patent_id)
