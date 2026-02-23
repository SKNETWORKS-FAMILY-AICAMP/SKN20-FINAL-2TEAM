# 디자인 유사성 분석 챗봇 - API 명세서

## 개요

| 항목 | 내용 |
|------|------|
| 서비스명 | 디자인 유사성 분석 챗봇 |
| Base URL | `http://localhost:8000` |
| API 문서 (Swagger) | `http://localhost:8000/docs` |
| 프로토콜 | HTTP |
| 응답 형식 | JSON |
| 실행 방법 | `python api.py` |

---

## 엔드포인트 목록

| Method | Endpoint | 설명 | 인증 |
|--------|----------|------|------|
| POST | `/chat/image` | 이미지 업로드 → 유사 디자인 10개 반환 (1단계) | 없음 |
| POST | `/chat/select` | 디자인 선택 → 상세비교 + FTO 리포트 (2단계) | 없음 |
| POST | `/chat/text` | 텍스트 질문 → LLM + Tools 답변 | 없음 |
| GET | `/health` | 서버 상태 확인 | 없음 |

---

## 이미지 분석 흐름

```
[클라이언트]                          [서버]
     │                                  │
     ├── POST /chat/image ──────────►   │  VLM 분석 → 벡터DB 검색
     │   (이미지 업로드)                 │  → interrupt에서 멈춤
     │                                  │
     ◄── 유사 디자인 10개 ──────────────┤  thread_id 포함
     │   + thread_id                    │
     │                                  │
     │   (사용자가 1개 선택)             │
     │                                  │
     ├── POST /chat/select ─────────►   │  interrupt 재개
     │   (thread_id + 선택번호)          │  → 상세비교 → 리포트 생성
     │                                  │
     ◄── 상세비교 + FTO 리포트 ─────────┤
     │                                  │
```

---

## 1. POST /chat/image

이미지를 업로드하면 유사 디자인 최대 10개를 검색하여 반환합니다.

### Request

| 항목 | 값 |
|------|------|
| Content-Type | `multipart/form-data` |

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `image` | File | O | 사용자가 업로드한 이미지 (JPG, PNG) |
| `user_query` | string | X | 사용자 질문 (기본값: "이 제품과 유사한 디자인을 분석해줘") |

### Response (200 OK)

```json
{
  "success": true,
  "thread_id": "550e8400-e29b-41d4-a716-446655440000",
  "input_analysis": "📦 물품: 용기\n\n🔍 형상 분석\n- 전체 실루엣: ...\n- 몸체 형태: ...",
  "similar_designs": [
    {
      "index": 1,
      "application_number": "3020240009248",
      "article_name": "분무 용기",
      "admst_stat": "등록",
      "distance": 0.0521,
      "image_base64": "/9j/4AAQSkZJRg..."
    },
    {
      "index": 2,
      "application_number": "3020100053835",
      "article_name": "스포이드를 가진 화장품 용기",
      "admst_stat": "등록",
      "distance": 0.0555,
      "image_base64": "/9j/4AAQSkZJRg..."
    }
  ],
  "message": "상세 비교할 디자인 번호를 선택하세요 (POST /chat/select)"
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `success` | boolean | 성공 여부 |
| `thread_id` | string | 세션 ID (2단계에서 필수) |
| `input_analysis` | string | 입력 디자인 형상 분석 결과 (이모지 포함 포맷팅된 텍스트) |
| `similar_designs` | array | 유사 디자인 목록 |
| `similar_designs[].index` | int | 디자인 번호 (1~10) |
| `similar_designs[].application_number` | string | 출원번호 |
| `similar_designs[].article_name` | string | 상품명 |
| `similar_designs[].admst_stat` | string | 등록 상태 |
| `similar_designs[].distance` | float | 유사도 거리 (낮을수록 유사) |
| `similar_designs[].image_base64` | string\|null | 디자인 이미지 (base64 인코딩, JPEG) |
| `message` | string | 안내 메시지 |

### Error Response

| 상태 코드 | 설명 |
|-----------|------|
| 400 | 유효하지 않은 이미지 파일 |
| 500 | 서버 내부 오류 (분석 실패) |

```json
{
  "detail": "유효하지 않은 이미지입니다."
}
```

---

## 2. POST /chat/select

1단계에서 받은 `thread_id`와 선택한 디자인 번호를 전달하면, 상세 비교 분석 및 FTO 리포트를 생성합니다.

### Request

| 항목 | 값 |
|------|------|
| Content-Type | `multipart/form-data` |

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `thread_id` | string | O | 1단계에서 받은 세션 ID |
| `selected_index` | int | O | 선택한 디자인 번호 (1~10) |

### Response (200 OK)

```json
{
  "success": true,
  "detailed_comparison": "{\"비교_디자인_분석\": {...}, \"유사한_점\": [...], \"비유사한_점\": [...]}",
  "final_report": "[디자인 비교 분석 리포트]\n\n1. 입력 디자인 요약\n   - 물품: 용기\n   ..."
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `success` | boolean | 성공 여부 |
| `detailed_comparison` | string | VLM 상세 비교 결과 (JSON 문자열: 유사한_점, 비유사한_점) — 내부 분석용, 프론트엔드 미표시 |
| `final_report` | string | FTO 리포트 (마크다운 형식 텍스트) — 프론트엔드 표시 대상 |

### Error Response

| 상태 코드 | 설명 |
|-----------|------|
| 500 | 잘못된 thread_id 또는 분석 실패 |

---

## 3. POST /chat/text

텍스트 질문을 보내면 LLM이 답변합니다. 
필요시 웹 검색(Tavily) 또는 디자인 DB 검색(ChromaDB) Tool을 자동 호출합니다.

### Request

| 항목 | 값 |
|------|------|
| Content-Type | `multipart/form-data` |

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `text_query` | string | O | 사용자 질문 |
| `thread_id` | string | X | 이전 대화 세션 ID (없으면 새 대화 시작, 있으면 대화 이어받기) |
| `image_thread_id` | string | X | 이미지 분석 완료 후 후속 질문 시 전달 (분석 결과를 컨텍스트로 주입, 1회만 유효) |

### 질문 유형별 Tool 호출 예시

| 질문 예시 | LLM 판단 | 호출 Tool |
|-----------|----------|-----------|
| "디자인 특허란?" | 직접 답변 | 없음 |
| "펌프형 용기 디자인 찾아줘" | DB 검색 필요 | `search_design_db` |
| "2024년 디자인 특허 통계" | 최신 정보 필요 | `web_search` |

### Response (200 OK)

```json
{
  "success": true,
  "thread_id": "새로운-또는-기존-세션-id",
  "turn": 1,
  "answer": "디자인 특허 출원 절차는 일반적으로 다음과 같은 단계로 이루어집니다...",
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
| `success` | boolean | 성공 여부 |
| `thread_id` | string | 세션 ID — **다음 요청에 포함하면 대화가 이어짐** |
| `turn` | int | 현재 대화 턴 수 |
| `answer` | string | LLM 답변 텍스트 |
| `search_images` | array | `search_design_db` 호출 시 관련 디자인 이미지 목록 (없으면 빈 배열) |
| `search_images[].application_number` | string | 출원번호 |
| `search_images[].last_disposition_date` | string | 최종 처분일 |
| `search_images[].image_base64` | string | 디자인 이미지 (base64 JPEG) |

### Error Response

| 상태 코드 | 설명 |
|-----------|------|
| 500 | 답변 생성 실패 |

---

## 4. GET /health

서버 상태를 확인합니다.

### Response (200 OK)

```json
{
  "status": "healthy",
  "service": "디자인 챗봇"
}
```


---

## cURL 예시

### 이미지 분석 (1단계)
```bash
curl -X POST http://localhost:8000/chat/image \
  -F "image=@my_design.jpg" \
  -F "user_query=유사한 디자인 분석해줘"
```

### 디자인 선택 (2단계)
```bash
curl -X POST http://localhost:8000/chat/select \
  -F "thread_id=550e8400-e29b-41d4-a716-446655440000" \
  -F "selected_index=3"
```

### 텍스트 질문
```bash
curl -X POST http://localhost:8000/chat/text \
  -F "text_query=펌프형 용기 디자인 찾아줘"
```

### 헬스체크
```bash
curl http://localhost:8000/health
```

---

## 참고사항

- `image_base64` 필드는 이미지를 base64로 인코딩한 문자열입니다. 프론트엔드에서 `<img src="data:image/jpeg;base64,{값}">` 형태로 표시할 수 있습니다.
- `thread_id`는 1단계와 2단계를 연결하는 세션 키입니다. 1단계 응답의 `thread_id`를 반드시 2단계 요청에 포함해야 합니다.
- `distance` 값은 CLIP 임베딩 간 유클리디안 거리이며, 값이 낮을수록 유사도가 높습니다.
- 텍스트 질문 시 LLM이 자동으로 적절한 Tool(웹 검색 / DB 검색 / 직접 답변)을 선택합니다.
