from __future__ import annotations
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests


SYSTEM_PROMPT = """당신은 이미지 유사도 분석, 컴퓨터 비전 임베딩, 설명 가능한 AI를 전문으로 하는 AI 어시스턴트입니다.

당신의 역할:
1. OpenCLIP 기반 이미지 임베딩으로 생성된 유사도 결과를 분석합니다.
2. 유사도 판단 근거를 사람이 이해하기 쉽게, 증거 기반으로 설명합니다.
3. 제공된 메타데이터, 유사도 점수, 문서 설명만 사용합니다.
4. 입력 데이터에 없는 정보를 절대 만들어내지 않습니다.
5. 기술 보고서에 적합한 구조화되고 전문적인 분석을 제공합니다.

창의성보다 사실에 기반한 분석을 우선합니다.
"""


def _safe_json_loads(text: str) -> Optional[Dict[str, Any]]:
    """
    LLM이 코드블록으로 감싸거나 앞뒤에 설명을 붙일 수 있어서
    최대한 JSON만 뽑아 파싱하는 방어 로직.
    """
    text = text.strip()

    # ```json ... ``` 제거
    if text.startswith("```"):
        lines = text.split("\n")
        # 첫 줄(```json)과 마지막 줄(```) 제거
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # 가장 바깥 JSON 객체만 추출 시도
    l = text.find("{")
    r = text.rfind("}")
    if l != -1 and r != -1 and r > l:
        candidate = text[l : r + 1]
    else:
        candidate = text

    try:
        return json.loads(candidate)
    except Exception:
        return None


@dataclass(frozen=True)
class LLMExplainer:
    model: str  # e.g., "qwen2.5:14b"
    base_url: str = "http://localhost:11434"
    timeout: int = 120

    def _check_connection(self) -> bool:
        """Ollama 서버 연결 확인."""
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def explain(self, user_image_id: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        유사 이미지 결과를 LLM으로 분석/설명.

        items: [
          {
            "reference_image_id": "...",
            "cosine_similarity": 0.82,
            "metadata": {...} | null,
            "document": {...} | null
          }, ...
        ]
        """
        user_prompt = f"""### 작업 설명
사용자가 이미지를 업로드했습니다.
사용자 이미지와 참조 이미지 데이터셋 간의 사전 계산된 유사도 검색 결과가 제공됩니다.

수행할 작업:
1. 사용자 이미지와 유사한 모든 참조 이미지를 식별하고 나열합니다.
2. 각 유사 이미지에 대해:
   - 이미지 식별자 표시
   - 유사도 점수 표시
   - documents.jsonl의 해당 문서 설명 요약
3. 각 이미지가 유사하다고 판단된 이유를 명확히 설명합니다:
   - 메타데이터에서 추론된 시각적 특성
   - 문서의 의미적/기능적 설명
   - 상대적 유사도 점수 (비교 분석)
4. 사용자 친화적이고 구조화된 형식으로 결과를 제시합니다.

반드시 아래 스키마의 JSON 형식으로만 출력하세요:
{{
  "summary": {{
    "user_image_id": "...",
    "num_similar": <int>,
    "notes": "..."
  }},
  "ranking": [
    {{
      "rank": <int>,
      "reference_image_id": "...",
      "cosine_similarity": <float>,
      "strength": "강함|보통|약함",
      "why_similar": ["...", "..."],
      "evidence": {{
        "metadata_fields_used": ["field1", "field2"],
        "document_fields_used": ["fieldA", "fieldB"]
      }},
      "limitations": ["..."]
    }}
  ]
}}

규칙:
- 사실을 만들어내지 마세요. 제공된 items만 사용하세요.
- 필드가 누락된 경우 limitations에 기록하세요.
- 출력은 반드시 유효한 JSON만. 마크다운이나 추가 텍스트 없이.

---

### 입력 데이터
사용자 image_id: {user_image_id}

유사도 항목 JSON:
{json.dumps(items, ensure_ascii=False)}
"""

        # 연결 확인
        if not self._check_connection():
            return {
                "summary": {
                    "user_image_id": user_image_id,
                    "num_similar": len(items),
                    "notes": "Ollama 서버 연결 실패. 'ollama serve' 실행 확인 필요.",
                },
                "error": "connection_failed",
            }

        # Ollama chat API 호출
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "options": {
                "temperature": 0.2,
                "num_ctx": 8192,
            },
        }

        try:
            resp = requests.post(url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
        except requests.exceptions.Timeout:
            return {
                "summary": {
                    "user_image_id": user_image_id,
                    "num_similar": len(items),
                    "notes": f"LLM 응답 시간 초과 ({self.timeout}초).",
                },
                "error": "timeout",
            }
        except requests.exceptions.RequestException as e:
            return {
                "summary": {
                    "user_image_id": user_image_id,
                    "num_similar": len(items),
                    "notes": f"LLM 요청 실패: {str(e)}",
                },
                "error": "request_failed",
            }

        data = resp.json()
        text = (data.get("message") or {}).get("content") or ""
        parsed = _safe_json_loads(text)

        if parsed is not None:
            return parsed

        # 파싱 실패 시 raw 반환 (디버깅 용)
        return {
            "summary": {
                "user_image_id": user_image_id,
                "num_similar": len(items),
                "notes": "LLM returned non-JSON output; see raw.",
            },
            "raw": text,
        }