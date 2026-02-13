# FTO Backend

> 특허 침해 여부 사전 검증 서비스 - FastAPI 백엔드

## 기술 스택

| 분류 | 기술 |
|------|------|
| Framework | FastAPI |
| Database | MySQL 8.0 |
| ORM | SQLAlchemy 2.0 |
| Authentication | JWT (python-jose) |
| Password Hashing | bcrypt (passlib) |

---

## 디렉토리 구조

```
backend/
├── app/
│   ├── main.py              # FastAPI 앱 진입점
│   ├── config.py            # 환경설정 (DB, JWT, CORS)
│   ├── database.py          # DB 연결 및 세션 관리
│   │
│   ├── routers/             # API 라우터
│   │   ├── auth.py          # 인증 (회원가입/로그인)
│   │   ├── chat.py          # 채팅 메시지
│   │   ├── analysis.py      # 특허 분석
│   │   └── search.py        # 특허 검색
│   │
│   ├── models/              # SQLAlchemy 모델
│   │   ├── user.py          # 사용자
│   │   ├── chat.py          # 채팅/메시지
│   │   ├── patent.py        # 특허/청구항
│   │   └── analysis.py      # 분석 결과
│   │
│   ├── schemas/             # Pydantic 스키마
│   │   ├── user.py
│   │   ├── chat.py
│   │   └── analysis.py
│   │
│   ├── services/            # 비즈니스 로직
│   │   ├── auth_service.py      # 인증 처리
│   │   ├── chat_service.py      # 채팅 처리
│   │   ├── search_service.py    # 특허 검색
│   │   ├── text_analyzer.py     # 텍스트 분석 (sLLM)
│   │   └── image_analyzer.py    # 이미지 분석 (디자인)
│   │
│   ├── core/                # 핵심 유틸리티
│   │   ├── security.py      # JWT 생성/검증
│   │   └── dependencies.py  # 의존성 주입
│   │
│   └── utils/
│       └── response_formatter.py  # 응답 포맷터
│
├── requirements.txt         # Python 의존성
├── Dockerfile              # Docker 이미지 빌드
└── .env                    # 환경변수 (gitignore)
```

---

## API 엔드포인트

### 인증 (`/api/auth`)

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | `/signup` | 회원가입 |
| POST | `/login` | 로그인 (JWT 토큰 반환) |
| POST | `/check-email` | 이메일 중복 확인 |
| POST | `/forgot-password` | 비밀번호 찾기 |
| POST | `/reset-password` | 비밀번호 재설정 |
| GET | `/me` | 현재 로그인 사용자 정보 |

### 채팅 (`/api/chat`)

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/` | 채팅 목록 조회 |
| POST | `/` | 새 채팅 생성 |
| GET | `/{chat_id}` | 채팅 상세 조회 |
| DELETE | `/{chat_id}` | 채팅 삭제 |
| POST | `/{chat_id}/messages` | 메시지 추가 |
| POST | `/message` | 프론트엔드용 채팅 API |

### 분석 (`/api/analysis`)

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | `/text` | 텍스트 기반 FTO 분석 |
| POST | `/image` | 이미지 기반 디자인 분석 |
| GET | `/{analysis_id}` | 분석 결과 조회 |

### 검색 (`/api/search`)

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/keywords?q=` | 키워드 기반 특허 검색 |
| GET | `/fulltext?q=` | 전문 검색 (MySQL FULLTEXT) |
| GET | `/patent/{id}/estoppel` | 금반언 청구항 조회 |
| POST | `/hybrid` | 하이브리드 검색 (RDB + RAG) |

---

## 데이터베이스 스키마

### 사용자 관련

```
users
├── id (PK)
├── email (unique)
├── hashed_password
├── name
└── created_at
```

### 특허 관련 (3,271건 import 완료)

```
patents                    # 특허 기본 정보
├── id (PK)
├── application_num        # 출원번호
├── register_num           # 등록번호
├── title                  # 발명명
├── abstract               # 초록
├── applicant              # 출원인
└── register_status        # 등록상태

patent_ipc                 # IPC 분류코드 (1:N)
├── patent_id (FK)
└── ipc_code

claims                     # 청구항 (158,584건)
├── patent_id (FK)
├── claim_number
├── claim_text
├── claim_type             # independent/dependent
├── version_type           # first(출원)/last(등록)
└── change_type            # 신규/수정/삭제

claim_elements             # 키워드 검색용 요소 (763,719건)
├── claim_id (FK)
├── element_type           # 성분/방법/구조
├── element_name
└── synonyms               # 동의어 배열
```

### 금반언 (Estoppel) 지원

- `claims.version_type`: 'first' (출원 시) / 'last' (등록 시)
- `claims.change_type`: '삭제'인 경우 금반언 적용 대상
- 출원 시 있었으나 등록 시 삭제된 청구항은 침해 판단에서 제외

---

## 환경 설정

### 로컬 개발 (.env)

```env
DATABASE_URL=mysql+pymysql://root:newpassword123@localhost:3306/fto
SECRET_KEY=your-secret-key
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

### Docker 환경

docker-compose.yml에서 자동 설정:
```
DATABASE_URL=mysql+pymysql://fto:fto1234@mysql:3306/fto
```

---

## 실행 방법

### 로컬 실행

```bash
# 가상환경 활성화
cd backend
source ../.venv/bin/activate  # Mac/Linux
# ..\.venv\Scripts\activate   # Windows

# 의존성 설치
pip install -r requirements.txt

# 서버 실행
uvicorn app.main:app --reload
```

### Docker 실행

```bash
cd SKN20-FINAL-2TEAM
docker compose up --build
```

---

## API 문서

서버 실행 후 접속:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

## 주요 기능 설명

### 1. 하이브리드 검색

```
사용자 입력
    │
    ├── RDB 검색 (claim_elements 키워드 매칭)
    │
    └── RAG 검색 (ChromaDB 벡터 검색) ← 팀원 연동 대기
    │
    └── 결과 병합 → 금반언 필터 → sLLM 분석
```

### 2. 인증 플로우

```
회원가입 → 비밀번호 해싱 (bcrypt) → DB 저장
    ↓
로그인 → 비밀번호 검증 → JWT 토큰 발급
    ↓
API 요청 → Authorization: Bearer {token} → 사용자 인증
```

### 3. 분석 플로우

```
텍스트 입력 → 키워드 추출 → 특허 검색 → sLLM 분석 → 결과 저장
```

---

## 연동 상태

| 기능 | 상태 | 비고 |
|------|------|------|
| 회원가입/로그인 | ✅ 완료 | JWT 인증 |
| 이메일 중복 확인 | ✅ 완료 | |
| 특허 RDB 검색 | ✅ 완료 | 키워드/전문 검색 |
| 금반언 조회 | ✅ 완료 | |
| 텍스트 분석 | ⏸️ Mock | sLLM 연동 필요 |
| 이미지 분석 | ⏸️ Mock | 디자인팀 연동 필요 |
| RAG 검색 | ⏸️ 대기 | RAG팀 연동 필요 |

---

## 팀원 연동 가이드

### RAG 팀

`/api/search/hybrid` 엔드포인트에서 `rag_results` 파라미터로 ChromaDB 검색 결과 전달:

```python
# 요청 예시
POST /api/search/hybrid
{
    "q": "헤스페리딘 화장료",
    "rag_results": [
        {"patent_id": 123, "score": 0.95, "claim_text": "..."},
        ...
    ]
}
```

### 디자인 팀

1. `app/models/patent.py`에 `DesignEmbedding` 모델 추가
2. `app/services/image_analyzer.py`의 TODO 부분 구현

### sLLM 팀

`app/services/text_analyzer.py`의 `_analyze_with_sllm()` 메서드에서 실제 모델 호출 구현

---

## 문의

- 백엔드 담당: [이름]
- GitHub: https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN20-FINAL-2TEAM
