# 디자인 분석 서비스 통합 가이드

> 작성일: 2026-02-25
> 목적: `design/src/` 디자인 챗봇을 메인 FRONTEND + Backend에 통합한 내용 정리
> 대상: 디자인 담당 팀원

---

## 1. 전체 구조 (변경 후)

```
[브라우저]
   │
   │  http://localhost:8000
   │
   ▼
[Backend - FastAPI :8000]
   ├── /api/analysis/design/image   ← 이미지 분석 (프록시)
   ├── /api/analysis/design/select  ← 디자인 선택 (프록시)
   ├── /api/analysis/design/text    ← 텍스트 질문 (프록시)
   ├── /design-chat.html            ← 정적 파일 서빙
   └── /api/auth, /api/chat ...     ← 기존 API
          │
          │  httpx (내부 프록시)
          ▼
[Design Service - FastAPI :8001]   ← design/src/api.py
   ├── /chat/image    ← VLM 분석 + CLIP 검색
   ├── /chat/select   ← 상세 비교 + 리포트
   └── /chat/text     ← 텍스트 질문
```

**핵심: 서버 2개 필요**
- Backend (포트 8000): 인증, DB, FRONTEND 서빙, 프록시
- Design Service (포트 8001): CLIP, ChromaDB, VLM (OpenAI)

---

## 2. 변경된 파일 목록

### 새로 생성

| 파일 | 설명 |
|------|------|
| `FRONTEND/design-chat.html` | 디자인 분석 전용 챗봇 페이지 (신규) |

### Backend 수정

| 파일 | 변경 내용 |
|------|-----------|
| `backend/app/config.py` | `DESIGN_SERVICE_URL`, `DESIGN_SERVICE_TIMEOUT` 추가 |
| `backend/app/main.py` | FRONTEND 정적 파일 서빙 추가 (StaticFiles, FileResponse) |
| `backend/app/routers/analysis.py` | 디자인 프록시 엔드포인트 3개 추가 |
| `backend/app/services/image_analyzer.py` | `DesignAnalysisService` 클래스 추가 |

### FRONTEND 수정

| 파일 | 변경 내용 |
|------|-----------|
| `FRONTEND/header.html` | 네비게이션 "디자인" 링크 → `design-chat.html`로 변경 |
| `FRONTEND/analysis.html` | 유형 전환 "디자인" 버튼 → `design-chat.html`로 이동 |
| `FRONTEND/analysis-chat.js` | 디자인 API 호출 로직 추가 (simulateWorkflow 등) |
| `FRONTEND/design-results.js` | mock 데이터 → 실제 API 데이터로 변경, 링크 색상 수정 |
| `FRONTEND/select-analysis-type.html` | 디자인 선택 시 `design-chat.html`로 라우팅 |

### Design Service 수정

| 파일 | 변경 내용 |
|------|-----------|
| `design/src/api.py` | 포트 8000 → **8001**로 변경 (Backend와 충돌 방지) |

---

## 3. 각 파일 상세 변경 내용

### 3-1. `backend/app/config.py`

추가된 설정:
```python
# 디자인 분석 서비스 (design/src/api.py → port 8001로 실행)
DESIGN_SERVICE_URL: str = "http://localhost:8001"
DESIGN_SERVICE_TIMEOUT: int = 120  # VLM 분석이 오래 걸릴 수 있음
```

### 3-2. `backend/app/main.py`

추가된 내용:
```python
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "FRONTEND"

@app.get("/")
async def root():
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "BINI API 서버가 실행 중입니다."}

# 맨 아래
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
```

### 3-3. `backend/app/routers/analysis.py`

추가된 엔드포인트 3개:

```
POST /api/analysis/design/image
  - 파라미터: image (파일), user_query (텍스트)
  - 동작: design service의 /chat/image로 프록시
  - 응답: { success, thread_id, input_analysis, similar_designs }

POST /api/analysis/design/select
  - 파라미터: thread_id, selected_index
  - 동작: design service의 /chat/select로 프록시
  - 응답: { success, final_report }

POST /api/analysis/design/text
  - 파라미터: text_query, thread_id(옵션), image_thread_id(옵션)
  - 동작: design service의 /chat/text로 프록시
  - 응답: { success, answer, search_images }
```

### 3-4. `backend/app/services/image_analyzer.py`

추가된 클래스:
```python
class DesignAnalysisService:
    @staticmethod
    async def analyze_image(file_content, filename, content_type, user_query) -> dict
    @staticmethod
    async def select_design(thread_id, selected_index) -> dict
    @staticmethod
    async def text_query(text_query, thread_id, image_thread_id) -> dict
```

### 3-5. `design/src/api.py`

```python
# 변경 전
uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

# 변경 후
uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")
```

### 3-6. `FRONTEND/design-chat.html` (신규)

디자인 분석 전용 챗봇 페이지:
- Tailwind CSS + 주황색 테마 (`#FF6B35`) - 기존 사이트와 동일
- Pretendard 폰트, Font Awesome 아이콘
- `header.html` 공통 헤더 자동 로드
- 사이드바 (토글 가능) + 분석 기록
- 챗봇 인터페이스: 이미지 업로드 → 유사 디자인 표시 → 선택 → FTO 리포트
- 컨텍스트 배너 (분석 후 추가 질문 가능)

### 3-7. `FRONTEND/header.html`

```html
<!-- 변경 전 -->
<a href="analysis.html?type=design" ...>디자인</a>

<!-- 변경 후 -->
<a href="design-chat.html" ...>디자인</a>
```
데스크톱 드롭다운 + 모바일 메뉴 둘 다 변경됨.

### 3-8. `FRONTEND/select-analysis-type.html`

```javascript
// 변경 전
window.location.href = `analysis.html?type=${type}`;

// 변경 후
if (type === 'design') {
    window.location.href = 'design-chat.html';
} else {
    window.location.href = `analysis.html?type=${type}`;
}
```

---

## 4. 실행 방법

### 터미널 1: Backend 실행

```bash
cd C:\00project\SKN20-FINAL-2TEAM\backend
python -m uvicorn app.main:app --reload --port 8000
```

### 터미널 2: Design Service 실행

```bash
cd C:\00project\SKN20-FINAL-2TEAM\design\src
python api.py
# → 포트 8001에서 실행됨
```

### 브라우저에서 접속

```
http://localhost:8000                  ← 메인 페이지
http://localhost:8000/design-chat.html ← 디자인 챗봇
http://localhost:8000/analysis.html?type=patent ← 특허 분석
```

> Go Live (VS Code) 안 써도 됨! Backend가 FRONTEND 파일을 직접 서빙함.

---

## 5. 필요한 환경 변수

프로젝트 루트의 `.env` 파일:
```
OPENAI_API_KEY=sk-...
```

`design/src/` 에서 실행할 때 `.env`를 찾지 못할 수 있음.
→ `design/src/design_chatbot.py`의 `load_dotenv()`가 루트 `.env`를 못 찾으면,
→ `.env`를 `design/src/`에도 복사하거나 경로를 명시해야 함.

---

## 6. 디자인 분석 플로우 (사용자 관점)

```
1. http://localhost:8000/design-chat.html 접속
2. 이미지 첨부 (클립 버튼 또는 "이미지 업로드" 버튼)
3. "분석해줘" 입력 후 전송
4. ⏳ VLM 분석 + CLIP 검색 (10~30초)
5. 유사 디자인 카드 목록 표시 (이미지, 출원번호, 유사도)
6. "상세 비교" 버튼 클릭
7. ⏳ VLM 상세 비교 + 리포트 생성
8. FTO 리포트 표시
9. (선택) 추가 질문 가능 (컨텍스트 유지)
```

---

## 7. 주의사항

- **포트 충돌**: Backend=8000, Design Service=8001. 둘 다 실행해야 디자인 분석이 동작함
- **CORS**: Backend에서 FRONTEND을 직접 서빙하므로 CORS 문제 없음
- **ChromaDB**: Design Service가 ChromaDB 벡터 DB를 사용함. EC2 배포 시 `/data/chroma/images/` 경로에 데이터 필요
- **모델**: VLM 분석에 OpenAI API (gpt-4o 등) 사용. API 키 필수
- **타임아웃**: VLM 분석이 오래 걸릴 수 있어서 프록시 타임아웃 120초로 설정됨

---

## 8. EC2 배포 시 추가 작업

```bash
# docker-compose.yml에 design service 추가 필요
# 또는 별도 프로세스로 실행:
cd design/src && python api.py &

# Backend의 DESIGN_SERVICE_URL을 EC2 내부 주소로 변경
# config.py: DESIGN_SERVICE_URL = "http://localhost:8001"
# (같은 서버면 localhost, 다른 서버면 내부 IP)
```

---

## 9. git pull 후 확인 체크리스트

팀원이 `git pull` 받은 후:

- [ ] `backend/app/config.py` - DESIGN_SERVICE_URL 확인
- [ ] `design/src/api.py` - 포트가 8001인지 확인
- [ ] `.env` 파일 - OPENAI_API_KEY 설정 확인
- [ ] 터미널 2개로 Backend + Design Service 실행
- [ ] `http://localhost:8000/design-chat.html` 접속 테스트
- [ ] 이미지 업로드 → 분석 결과 나오는지 확인
