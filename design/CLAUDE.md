# design/ 백엔드 병합 가이드

> 디자인 챗봇 모듈을 메인 FastAPI 백엔드(`backend/`)에 병합할 때 참고.
> 핵심 파일 3개(`design_chatbot.py`, `utils.py`, `prompts.py`)는 **수정 금지**.

---

## 핵심 파일

| 파일 | 역할 | 수정 여부 |
|------|------|----------|
| `src/design_chatbot.py` | LangGraph 그래프, 노드 7개, `run_chatbot()` | **수정 금지** |
| `src/utils.py` | CLIP 임베딩, Hybrid Retrieval, 스케치 변환 | **수정 금지** |
| `src/prompts.py` | VLM 프롬프트 3개 (분석/비교/리포트) | **수정 금지** |
| `chroma_db/` | ChromaDB 벡터 DB (디자인 특허 이미지 임베딩) | 건드리지 말 것 |
| `api.py`, `index.html` | 임시 테스트용 — **무시할 것** | 삭제 가능 |

---

## 연동 포인트 1 — import 방식

`design/src/` 기준으로 실행되어야 한다.
백엔드에서 import 시 경로 주의:

```python
import sys
sys.path.insert(0, "/path/to/design/src")

from design_chatbot import graph, GraphState
from langgraph.types import Command
```

`graph = create_graph()`는 **모듈 로드 시점에 자동 실행**된다.
import 순간 ChromaDB 전체 로드 + BM25 인덱스 빌드가 발생한다 (수 초 소요).
FastAPI 앱 시작 시 1회만 import하고 재사용해야 한다. 요청마다 import하면 안 된다.

---

## 연동 포인트 2 — 이미지 입력 플로우 (2단계 필수)

이미지 입력은 LangGraph `interrupt` 때문에 반드시 **2단계**로 처리해야 한다.

```
[1단계] 이미지 경로 전달 → 유사 디자인 10개 반환 (여기서 그래프 정지)
[2단계] 사용자 선택 번호 전달 → 그래프 재개 → 상세 비교 → FTO 리포트 반환
```

```python
from design_chatbot import graph
from langgraph.types import Command

# 1단계: 이미지 분석 + 유사 디자인 검색
def step1_analyze(image_path: str, session_id: str) -> list:
    initial_state = {
        "input_type": "", "image_path": image_path,
        "text_query": "", "user_query": "이 제품과 유사한 디자인을 분석해줘",
        "base64_image": "", "input_analysis": "",
        "comparison_results": [], "selected_index": 0,
        "detailed_comparison": "", "final_report": "",
        "general_answer": "", "search_images": [], "messages": [],
    }
    config = {"configurable": {"thread_id": session_id}}
    result = graph.invoke(initial_state, config)
    return result.get("comparison_results", [])   # 최대 10개 유사 디자인

# 2단계: 선택 번호로 그래프 재개
def step2_compare(selected_index: int, session_id: str) -> str:
    config = {"configurable": {"thread_id": session_id}}
    result = graph.invoke(Command(resume=str(selected_index)), config)
    return result.get("final_report", "")
```

`session_id`는 `thread_id`로 사용된다. **사용자별로 고유해야 한다** (예: `str(uuid4())`).

---

## 연동 포인트 3 — 텍스트 입력 플로우 (1단계)

텍스트는 interrupt 없이 한 번에 완료된다.

```python
def text_query(query: str, session_id: str, history: list = None) -> dict:
    initial_state = {
        "input_type": "", "image_path": "",
        "text_query": query, "user_query": query,
        "base64_image": "", "input_analysis": "",
        "comparison_results": [], "selected_index": 0,
        "detailed_comparison": "", "final_report": "",
        "general_answer": "", "search_images": [],
        "messages": history or [],
    }
    config = {"configurable": {"thread_id": session_id}}
    result = graph.invoke(initial_state, config)
    return {
        "answer": result.get("general_answer", ""),
        "search_images": result.get("search_images", []),  # DB 검색 시 이미지 URL 목록
        "messages": result.get("messages", []),            # 멀티턴용 히스토리
    }
```

멀티턴은 `messages` 히스토리를 다음 호출 시 그대로 넘기면 된다.

---

## 연동 포인트 4 — comparison_results 구조

1단계 반환값 `comparison_results` 각 항목:

```python
{
    "index": 1,                          # 사용자에게 보여줄 선택 번호 (1~10)
    "design_id": "3020120015713-api_xml-1",
    "hybrid_score": 0.8512,              # 최종 유사도 점수 (높을수록 유사)
    "dense_score": 0.7234,
    "bm25_score": 1.2300,
    "application_number": "3020120015713",
    "article_name": "화장품 용기",
    "admst_stat": "등록",                # 등록 / 소멸 / 출원 등
    "image_path": "https://..."          # ChromaDB imagePath 필드 (URL)
}
```

`image_path`는 ChromaDB 메타데이터의 `imagePath` 필드에서 가져온 URL이다.
백엔드가 별도로 이미지를 서빙할 필요 없다. 프론트엔드에서 URL 직접 사용.

---

## 환경변수 (.env)

`design/.env` 또는 메인 백엔드 `.env`에 추가:

```env
VLLM_API_BASE=https://<pod-id>-8000.proxy.runpod.net/v1
VLLM_MODEL=/workspace/Qwen2.5-VL-7B-Instruct
TAVILY_API_KEY=<Tavily API 키>
```

`design_chatbot.py`와 `utils.py` 모두 `load_dotenv()`로 자동 로드한다.

---

## 인프라 — vLLM 서버

| 항목 | 값 |
|------|---|
| 모델 | `Qwen/Qwen2.5-VL-7B-Instruct` (베이스 모델, 파인튜닝 없음) |
| 필요 VRAM | ~18 GB (bfloat16) |
| 권장 GPU | RTX 3090 / RTX 4090 (24 GB) |
| 기본 포트 | 8000 |

특허 FTO 백엔드의 vLLM(Qwen2.5-14B)도 포트 8000을 쓴다.
**두 모델을 같은 서버에서 동시에 띄울 경우 포트가 겹친다.**
디자인 vLLM은 포트 8001로 분리하고 `VLLM_API_BASE` 포트를 맞춰야 한다.

vLLM 실행 명령어 (`sllm_서빙_가이드.md` 참고):
```bash
HF_HOME=/workspace/hf_cache TMPDIR=/workspace nohup python -m vllm.entrypoints.openai.api_server \
  --model /workspace/Qwen2.5-VL-7B-Instruct \
  --host 0.0.0.0 --port 8001 \
  --dtype bfloat16 --max-model-len 8192 \
  --gpu-memory-utilization 0.85 \
  --enable-auto-tool-choice --tool-call-parser hermes \
  > /workspace/vllm_design.log 2>&1 &
```

---

## 주의사항

### 1. MemorySaver — 서버 재시작 시 세션 초기화
`graph`는 `MemorySaver`(인메모리) 기반이다.
서버 재시작 시 진행 중이던 이미지 분석 세션이 모두 사라진다.
이미지 분석 도중 서버가 재시작되면 1단계부터 다시 시작해야 한다.
영속성이 필요하면 `SqliteSaver`로 교체를 검토.

### 2. graph는 싱글톤 — 재생성 금지
`create_graph()`를 요청마다 호출하면 ChromaDB 전체 + BM25를 매번 다시 로드한다.
`design_chatbot.py` 모듈 하단의 `graph = create_graph()`가 앱 시작 시 1회 실행되므로,
import만 하면 된다. **절대 직접 `create_graph()`를 다시 호출하지 말 것.**

### 3. CLIP 모델 첫 실행 시 자동 다운로드
`utils.py` import 시 CLIP ViT-B/32 모델이 자동 다운로드된다 (~340MB).
처음 실행 시 시간이 걸린다. 이후에는 캐시에서 로드.

### 4. ChromaDB 경로
`CHROMA_DB = design/chroma_db/` (design_chatbot.py 기준 자동 계산).
배포 환경에서 `design/` 폴더 위치가 달라지면
`design_chatbot.py` 28~30번째 줄 `BASE_DIR`, `CHROMA_DB`를 수정해야 한다.

### 5. imagePath가 빈 문자열인 경우
ChromaDB 메타데이터에 `imagePath`가 없는 도큐먼트는 `image_path: ""`로 반환된다.
프론트엔드에서 빈 문자열 처리 필요. `detailed_compare_node`는 빈 경우 자동으로
`"비교 대상 이미지를 찾을 수 없습니다."` 메시지를 반환한다.

### 6. 수정하면 안 되는 것
- `prompts.py`의 `IMAGE_ANALYSIS_PROMPT`, `IMAGE_COMPARISON_PROMPT`, `REPORT_PROMPT`
  — 프롬프트 구조가 VLM 입력 포맷과 맞춰져 있어 수정 시 응답 품질 저하
- `utils.py`의 `hybrid_retrieve()` 가중치 (`DENSE_WEIGHT=0.7`, BM25=0.3)
  — 실험적으로 튜닝된 값

---

## 의존성

```bash
pip install -r design/requirements.txt
```

CLIP은 PyPI가 아닌 GitHub에서 설치:
```bash
pip install git+https://github.com/openai/CLIP.git
```
