# CLAUDE.md — Design Chatbot sLLM 마이그레이션 가이드

## 개요

기존 `design_chatbot.py`에서 사용하던 OpenAI GPT-4o를 팀이 직접 학습시킨 sLLM으로 교체한다.
- **모델**: `itsbini/qwen2.5-14b-fto` (HuggingFace)
- **서빙**: vLLM OpenAI-compatible server
- **목적**: 비용 절감 + 자체 호스팅

---

## 1. vLLM 서버 실행

```bash
vllm serve "itsbini/qwen2.5-14b-fto" \
  --host 0.0.0.0 \
  --port 8000 \
  --dtype auto \
  --max-model-len 8192
```

서버가 뜨면 `http://localhost:8000/v1` 엔드포인트로 OpenAI API 형식 요청이 가능하다.

> **확인 방법**
> ```bash
> curl http://localhost:8000/v1/models
> ```

---

## 2. 코드 변경 사항 (`design_chatbot.py`)

### 2-1. LLM 초기화 교체

**Before (GPT-4o)**
```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4o", temperature=0)
```

**After (vLLM served sLLM)**
```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="itsbini/qwen2.5-14b-fto",
    openai_api_base="http://localhost:8000/v1",
    openai_api_key="EMPTY",          # vLLM은 key 불필요, 빈 문자열 아무거나 넣으면 됨
    temperature=0,
)
```

`langchain_openai.ChatOpenAI`는 `openai_api_base`만 바꿔주면 vLLM의 OpenAI-compatible endpoint를 그대로 사용할 수 있다. 나머지 체인 코드(`| llm | output_parser` 패턴)는 수정 불필요.

### 2-2. Tool Calling (`llm_with_tools`) 주의사항

```python
llm_with_tools = llm.bind_tools(tools)
```

Qwen2.5는 tool calling을 지원하지만, vLLM 서빙 시 `--enable-auto-tool-choice` 플래그가 필요할 수 있다.

```bash
vllm serve "itsbini/qwen2.5-14b-fto" \
  --host 0.0.0.0 \
  --port 8000 \
  --dtype auto \
  --max-model-len 8192 \
  --enable-auto-tool-choice \
  --tool-call-parser hermes   # Qwen2.5는 hermes parser 사용
```

tool calling이 제대로 작동하지 않는다면 `general_question_node`의 `response.tool_calls` 분기를 테스트해볼 것.

### 2-3. VLM 노드 주의사항 (이미지 입력)

`analyze_image_node`와 `detailed_compare_node`는 base64 이미지를 LLM에 직접 넘긴다.
`itsbini/qwen2.5-14b-fto`가 **비전 기능을 지원하는지 확인** 필요.

- 지원한다면 → 코드 변경 없이 그대로 동작
- 지원하지 않는다면 → VLM 노드(`analyze_image_node`, `detailed_compare_node`)에만 별도 비전 모델(예: GPT-4o-mini 또는 별도 VLM 서버)을 사용하는 **dual-LLM 구조**로 분리해야 함

```python
# dual-LLM 구조 예시
llm_text = ChatOpenAI(
    model="itsbini/qwen2.5-14b-fto",
    openai_api_base="http://localhost:8000/v1",
    openai_api_key="EMPTY",
    temperature=0,
)

llm_vision = ChatOpenAI(model="gpt-4o-mini", temperature=0)  # 비전 전용

# analyze_image_node, detailed_compare_node → llm_vision 사용
# general_question_node, generate_report_node → llm_text 사용
```

---

## 3. 환경변수 (`.env`)

```env
# 기존
OPENAI_API_KEY=sk-...

# 추가 (vLLM 엔드포인트)
VLLM_API_BASE=http://localhost:8000/v1

# TAVILY (웹 검색 tool, 기존 유지)
TAVILY_API_KEY=tvly-...
```

코드에서 환경변수로 관리하고 싶다면:
```python
import os
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="itsbini/qwen2.5-14b-fto",
    openai_api_base=os.getenv("VLLM_API_BASE", "http://localhost:8000/v1"),
    openai_api_key="EMPTY",
    temperature=0,
)
```

---

## 4. 변경 요약 체크리스트

| 항목 | 상태 | 비고 |
|---|---|---|
| `llm` 초기화 교체 | ☐ | `openai_api_base` 변경 |
| vLLM 서버 실행 | ☐ | `--enable-auto-tool-choice --tool-call-parser hermes` 포함 |
| tool calling 동작 확인 | ☐ | `general_question_node` 테스트 |
| 비전 기능 지원 여부 확인 | ☐ | VLM 노드 분리 여부 결정 |
| `.env` 업데이트 | ☐ | `VLLM_API_BASE` 추가 |
| 프롬프트 튜닝 | ☐ | 모델 변경 시 프롬프트 응답 품질 재검증 |

---

## 5. 빠른 테스트

서버 실행 후 아래로 동작 확인:

```python
# 텍스트 경로 테스트
from design_chatbot import run_chatbot
result = run_chatbot(text_query="디자인 특허란 무엇인가요?")
print(result['general_answer'])

# DB 검색 tool 테스트
result = run_chatbot(text_query="둥근 펌프 용기 디자인 찾아줘")
print(result['general_answer'])
```
