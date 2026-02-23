# 디자인 유사성 분석 챗봇

이미지 또는 텍스트로 디자인 특허 유사성을 검색하고 FTO 리포트를 생성하는 AI 챗봇 서비스입니다.

---

## 목차

- [프로젝트 구조](#프로젝트-구조)
- [챗봇 동작 흐름](#챗봇-동작-흐름)
- [환경 설정](#환경-설정)
- [서버 실행](#서버-실행)
- [API 명세](#api-명세)
- [프론트엔드 연동 가이드](#프론트엔드-연동-가이드)

---

## 프로젝트 구조

```
design/
├── src/
│   ├── api.py               # FastAPI 서버 (엔드포인트 정의)
│   ├── design_chatbot.py    # LangGraph 그래프 (핵심 로직)
│   ├── utils.py             # CLIP 임베딩, 이미지 검색 유틸
│   ├── prompts.py           # VLM 프롬프트 (이미지 분석/비교/리포트)
│   ├── API_명세서.md         # 상세 API 명세
│   └── temp_uploads/        # 업로드 이미지 임시 저장 폴더
├── chroma_db/               # ChromaDB 벡터 인덱스
└── data/
    └── images/              # 디자인 특허 이미지
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

## 환경 설정

### 패키지 설치

```bash
pip install fastapi uvicorn python-multipart pillow requests
pip install langchain langchain-openai langchain-community langgraph
pip install chromadb rank-bm25 python-dotenv
pip install tavily-python
```

### 환경 변수 (.env)

`design/src/` 폴더에 `.env` 파일을 생성하세요.

```env
OPENAI_API_KEY=your-openai-api-key
TAVILY_API_KEY=your-tavily-api-key
```

### ChromaDB 준비

서버 실행 전 `design/chroma_db/`에 벡터 인덱스가 빌드되어 있어야 합니다.

---

## 서버 실행

```bash
cd design/src
python api.py
```

| 항목 | 값 |
|------|------|
| 서버 주소 | `http://localhost:8000` |
| Swagger 문서 | `http://localhost:8000/docs` |
| 헬스체크 | `http://localhost:8000/health` |

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
