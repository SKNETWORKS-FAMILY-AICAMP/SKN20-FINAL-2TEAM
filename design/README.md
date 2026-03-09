# 디자인 유사성 분석 챗봇

CLIP 임베딩 기반 **Hybrid Retrieval**과 **VLM (Qwen2.5-VL-7B-Instruct, vLLM 서빙)** 을 활용한 디자인 특허 유사도 분석 시스템

---

## 목차

- [디렉토리 구조](#디렉토리-구조)
- [설치](#설치)
- [환경변수](#환경변수-env)
- [전체 구조](#전체-구조)
- [챗봇 동작 흐름](#챗봇-동작-흐름)
- [이미지 입력 플로우](#이미지-입력-플로우)
- [텍스트 입력 플로우](#텍스트-입력-플로우)
- [API 명세](#api-명세)
- [프론트엔드 연동 가이드](#프론트엔드-연동-가이드)
- [cURL 테스트](#curl-테스트)
- [주요 파일](#주요-파일)

---

## 디렉토리 구조

```
design/
├── .env                        # 환경 변수 (API 키 등)
├── .gitignore
├── README.md
├── requirements.txt
├── chroma_db/                  # ChromaDB 벡터 DB (구글 드라이브에서 다운로드)
└── src/
    ├── design_chatbot.py       # 챗봇 메인 — LangGraph 그래프 및 노드 정의
    ├── utils.py                # 임베딩, 스케치 변환, Hybrid Retrieval 유틸 함수
    ├── prompts.py              # VLM 분석 / 비교 / 리포트 프롬프트
    ├── api.py                  # FastAPI 서버
    ├── index.html              # 챗봇 UI
    ├── sllm_서빙_가이드.md
    └── temp_uploads/           # 업로드된 임시 이미지
```

---

## 설치

Python 3.9+ 필요

```bash
pip install -r requirements.txt
```

CLIP은 PyPI가 아닌 GitHub에서 설치:

```bash
pip install git+https://github.com/openai/CLIP.git
```

---

## 환경변수 (.env)

```
OPENAI_API_KEY=<OpenAI API 키>
TAVILY_API_KEY=<Tavily API 키>
VLLM_API_BASE=<vLLM 서버 주소>/v1
VLLM_MODEL=<모델 경로>
```

---

## 전체 구조

```
[입력]
  │
  ├─ 이미지 ──▶ [VLM 분석] ──▶ [유사 디자인 검색] ──▶ [선택 대기] ──▶ [상세 비교] ──▶ [FTO 리포트]
  │
  └─ 텍스트 ──▶ [LLM + Tools]
```

---

## 챗봇 동작 흐름

### 이미지 검색 흐름 (2단계)

```
[클라이언트]                              [서버 - LangGraph]
     │                                         │
     ├── POST /chat/image ──────────────►  [라우터]
     │   (이미지 파일 전송)                     │
     │                                    [VLM 분석] GPT-4o로 형상 분석
     │                                         │
     │                                    [벡터 검색] CLIP + BM25 Hybrid
     │                                         │
     ◄── 유사 디자인 10개 + thread_id ────  ★ interrupt (사용자 선택 대기) ★
     │
     │   (사용자가 1개 선택)
     │
     ├── POST /chat/select ─────────────►  interrupt 재개
     │   (thread_id + selected_index)          │
     │                                    [상세 비교] VLM으로 2개 이미지 비교
     │                                         │
     │                                    [리포트 생성] FTO 리포트 작성
     │                                         │
     ◄── 상세 비교 결과 + FTO 리포트 ──────────┘
```

### 텍스트 질문 흐름 (멀티턴)

```
[클라이언트]                              [서버 - LangGraph]
     │                                         │
     ├── POST /chat/text ──────────────►  [라우터]
     │   (text_query)                          │
     │                                    [LLM + Tools] GPT-4o
     │                                     ├─ 직접 답변
     │                                     ├─ web_search (Tavily)
     │                                     └─ search_design_db (ChromaDB)
     │                                         │
     ◄── answer + thread_id ───────────────────┘
     │
     │   (다음 질문 시 thread_id 포함 → 대화 이어받기)
     │
     ├── POST /chat/text ──────────────►  대화 히스토리 유지하며 답변
```

---

## 이미지 입력 플로우

### 1단계 · VLM 분석

Qwen2.5-VL-7B-Instruct가 입력 이미지의 형상·구조·외관을 텍스트로 분석

---

### 2단계 · 유사 디자인 검색 (Hybrid Retrieval)

**전처리 — 쿼리 이미지 → 스케치 변환**

DB에 저장된 임베딩은 스케치 변환 이미지 기준이므로, 쿼리 이미지도 동일한 전처리 적용

```
원본 이미지
  └─▶ GaussianBlur (5×5, σ=1.0)
        └─▶ Canny Edge Detection (threshold: 80 / 200)   ← 강한 엣지만 검출, 배경 노이즈 감소
              └─▶ Dilate (2×2 kernel, 1회)
                    └─▶ findContours → 면적 500px² 미만 제거  ← 잔여 노이즈 제거
                          └─▶ 흰 배경 + 검은 윤곽선
```

**검색 — Dense + BM25 2단계**

| 단계 | 방법 | 범위 | 결과 |
|:---:|---|---|---|
| ① Dense | CLIP ViT-B/32 임베딩 → ChromaDB 코사인 유사도 | 전체 DB | 상위 50개 후보 |
| ② BM25 | Dense 1위의 `articleName` 키워드 → 텍스트 재점수 | 50개 내 재랭킹 | - |
| ③ 합산 | min-max 정규화 후 가중 합산 | Dense **0.7** + BM25 **0.3** | - |
| ④ 중복 제거 | 동일 출원번호 중 `hybrid_score` 최고 도면 유지 | - | - |
| ⑤ 반환 | `hybrid_score` 내림차순 정렬 | - | **최종 10개** |

---

### 3단계 · 사용자 선택 _(interrupt)_

- 검색 결과 10개를 `hybrid_score` 기준으로 출력
- 사용자가 상세 비교할 도면 번호 선택 → 그래프 재개

---

### 4단계 · 상세 비교

- 선택한 도면 이미지를 Qwen2.5-VL-7B-Instruct가 입력 이미지와 나란히 비교
- 유사점 / 차이점 분석 결과 생성

---

### 5단계 · FTO 리포트 생성

- VLM 분석 결과 + 상세 비교 결과 → 최종 FTO 리포트 출력

---

## 텍스트 입력 플로우

LLM이 질문을 보고 필요한 Tool을 자동 선택하여 답변

| Tool | 동작 |
|---|---|
| `web_search` | Tavily를 통한 웹 검색 (특허 뉴스, 법률 정보 등) |
| `search_design_db` | 자연어 → CLIP 임베딩 → ChromaDB 디자인 검색 |

---

## API 명세

### 엔드포인트 목록

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | `/chat/image` | 이미지 업로드 → 유사 디자인 10개 반환 (1단계) |
| POST | `/chat/select` | 디자인 선택 → 상세비교 + FTO 리포트 (2단계) |
| POST | `/chat/text` | 텍스트 질문 → LLM 답변 (멀티턴 지원) |
| GET | `/health` | 서버 상태 확인 |

---

### POST `/chat/image`

이미지를 업로드하면 유사 디자인 최대 10개를 반환합니다.

**Request** `Content-Type: multipart/form-data`

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|:----:|------|
| `image` | File | O | 업로드할 이미지 (JPG, PNG) |
| `user_query` | string | X | 사용자 질문 (기본값: "이 제품과 유사한 디자인을 분석해줘") |

**Response** `200 OK`

```json
{
  "success": true,
  "thread_id": "550e8400-e29b-41d4-a716-446655440000",
  "input_analysis": "📦 물품: 용기\n\n🔍 형상 분석\n- 전체 실루엣: ...",
  "similar_designs": [
    {
      "index": 1,
      "application_number": "3020240009248",
      "article_name": "분무 용기",
      "admst_stat": "등록",
      "distance": 0.0521,
      "image_base64": "/9j/4AAQSkZJRg..."
    }
  ],
  "message": "상세 비교할 디자인 번호를 선택하세요 (POST /chat/select)"
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `thread_id` | string | **2단계 요청에 반드시 포함** |
| `input_analysis` | string | 입력 디자인 형상 분석 결과 (이모지 포함 포맷팅된 텍스트) |
| `similar_designs[].index` | int | 디자인 번호 (1~10) |
| `similar_designs[].distance` | float | 유사도 점수 (hybrid_score, **높을수록 유사**, 0~1) |
| `similar_designs[].image_base64` | string\|null | 디자인 이미지 (base64 JPEG, ChromaDB 메타데이터의 kipris.or.kr URL에서 실시간 다운로드) |

**Error**

| 상태 코드 | 설명 |
|-----------|------|
| 400 | 유효하지 않은 이미지 |
| 500 | 서버 오류 |

---

### POST `/chat/select`

1단계에서 받은 `thread_id`와 선택한 디자인 번호로 상세 비교 및 FTO 리포트를 생성합니다.

**Request** `Content-Type: multipart/form-data`

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|:----:|------|
| `thread_id` | string | O | 1단계 응답에서 받은 세션 ID |
| `selected_index` | int | O | 선택한 디자인 번호 (1~10) |

**Response** `200 OK`

```json
{
  "success": true,
  "detailed_comparison": "{\"유사한_점\": [...], \"비유사한_점\": [...]}",
  "final_report": "## 디자인 비교 분석 리포트\n\n..."
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `detailed_comparison` | string | VLM 상세 비교 결과 (JSON 문자열) — 내부 분석용, 프론트엔드 미표시 |
| `final_report` | string | FTO 리포트 **(마크다운 형식)** — 프론트엔드 표시 대상 |

---

### POST `/chat/text`

텍스트 질문에 LLM이 답변합니다. 멀티턴 대화를 지원하며, 이미지 분석 후 후속 질문도 가능합니다.

**Request** `Content-Type: multipart/form-data`

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|:----:|------|
| `text_query` | string | O | 사용자 질문 |
| `thread_id` | string | X | 이전 대화 세션 ID (없으면 새 대화 시작) |
| `image_thread_id` | string | X | 이미지 분석 완료 후 후속 질문 시 전달 (분석 결과를 컨텍스트로 주입) |

**Response** `200 OK`

```json
{
  "success": true,
  "thread_id": "새로운-또는-기존-세션-id",
  "turn": 1,
  "answer": "디자인 특허란 물품의 외관에 관한 창작을...",
  "search_images": [
    {
      "application_number": "3020240009248",
      "last_disposition_date": "2024-03-15",
      "image_base64": "/9j/4AAQSkZJRg..."
    }
  ]
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `thread_id` | string | **다음 요청에 포함하면 대화가 이어짐** |
| `turn` | int | 현재 대화 턴 수 |
| `answer` | string | LLM 답변 |
| `search_images` | array | `search_design_db` 호출 시 관련 디자인 이미지 목록 (없으면 빈 배열) |
| `search_images[].application_number` | string | 출원번호 |
| `search_images[].last_disposition_date` | string | 최종 처분일 |
| `search_images[].image_base64` | string | 디자인 이미지 (base64 JPEG) |

**Tool 자동 선택 예시**

| 질문 | 호출 Tool |
|------|-----------|
| "디자인 특허란?" | 없음 (직접 답변) |
| "펌프형 용기 디자인 찾아줘" | `search_design_db` (ChromaDB) |
| "2024년 디자인 특허 통계" | `web_search` (Tavily) |

---

### GET `/health`

**Response** `200 OK`

```json
{
  "status": "healthy",
  "service": "디자인 챗봇 v3"
}
```

---

## 프론트엔드 연동 가이드

### 이미지 분석 UI (2단계 흐름)

```javascript
// 1단계: 이미지 업로드
const formData = new FormData();
formData.append('image', imageFile);
formData.append('user_query', '유사한 디자인 분석해줘');

const res1 = await fetch('http://localhost:8000/chat/image', {
  method: 'POST',
  body: formData,
});
const data1 = await res1.json();

// thread_id 반드시 저장
const threadId = data1.thread_id;

// 이미지 카드 렌더링
data1.similar_designs.forEach(design => {
  // image_base64를 img 태그에 직접 사용
  const imgSrc = `data:image/jpeg;base64,${design.image_base64}`;
});

// 2단계: 사용자가 카드 선택 후
const formData2 = new FormData();
formData2.append('thread_id', threadId);   // 1단계에서 받은 thread_id
formData2.append('selected_index', '3');   // 선택한 번호

const res2 = await fetch('http://localhost:8000/chat/select', {
  method: 'POST',
  body: formData2,
});
const data2 = await res2.json();

// final_report는 마크다운 형식 → 마크다운 렌더러로 표시
renderMarkdown(data2.final_report);
```

### 텍스트 채팅 UI (멀티턴)

```javascript
let chatThreadId = null;  // 대화 세션 유지용

async function sendMessage(userText) {
  const formData = new FormData();
  formData.append('text_query', userText);

  // 이전 대화가 있으면 thread_id 포함
  if (chatThreadId) {
    formData.append('thread_id', chatThreadId);
  }

  const res = await fetch('http://localhost:8000/chat/text', {
    method: 'POST',
    body: formData,
  });
  const data = await res.json();

  // 다음 요청을 위해 thread_id 저장
  chatThreadId = data.thread_id;

  return data.answer;
}
```

### 이미지 분석 후 후속 텍스트 질문

```javascript
// 이미지 분석 완료 후, 분석 결과에 대해 추가 질문할 때
const formData = new FormData();
formData.append('text_query', '이 분석 결과에 대해 더 설명해줘');
formData.append('image_thread_id', imageThreadId);  // 이미지 분석의 thread_id

const res = await fetch('http://localhost:8000/chat/text', {
  method: 'POST',
  body: formData,
});
```

---

## cURL 테스트

```bash
# 헬스체크
curl http://localhost:8000/health

# 이미지 분석 (1단계)
curl -X POST http://localhost:8000/chat/image \
  -F "image=@my_design.jpg" \
  -F "user_query=유사한 디자인 분석해줘"

# 디자인 선택 (2단계)
curl -X POST http://localhost:8000/chat/select \
  -F "thread_id=550e8400-e29b-41d4-a716-446655440000" \
  -F "selected_index=3"

# 텍스트 질문 (새 대화)
curl -X POST http://localhost:8000/chat/text \
  -F "text_query=펌프형 용기 디자인 찾아줘"

# 텍스트 질문 (대화 이어받기)
curl -X POST http://localhost:8000/chat/text \
  -F "text_query=방금 결과 중 등록된 것만 알려줘" \
  -F "thread_id=이전-thread-id"
```

---

## 주요 파일

| 파일 | 역할 |
|---|---|
| `src/design_chatbot.py` | 챗봇 메인 — LangGraph 그래프 및 노드 정의 |
| `src/utils.py` | 임베딩, 스케치 변환, Hybrid Retrieval 유틸 함수 |
| `src/prompts.py` | VLM 분석 / 비교 / 리포트 프롬프트 |
| `src/api.py` | FastAPI 서버 |
| `src/index.html` | 챗봇 UI |
