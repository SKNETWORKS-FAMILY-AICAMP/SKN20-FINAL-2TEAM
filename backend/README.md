# FTOGuard Backend

> 특허/디자인 FTO 분석 서비스 - FastAPI 백엔드

## 기술 스택

| 분류 | 기술 |
|------|------|
| Framework | FastAPI |
| Database | MySQL 8.4 (AWS RDS) |
| ORM | SQLAlchemy 2.0 |
| Authentication | JWT (python-jose) |
| Storage | AWS S3 (디자인 이미지) |
| AI/ML | RunPod Serverless (Qwen2.5-14B, Qwen2.5-VL-7B) |

---

## 디렉토리 구조

```
backend/
├── app/
│   ├── main.py              # FastAPI 앱 진입점
│   ├── config.py            # 환경설정 (DB, JWT, S3)
│   ├── database.py          # DB 연결 및 세션 관리
│   │
│   ├── routers/             # API 라우터
│   │   ├── auth.py          # 인증 (회원가입/로그인)
│   │   ├── chat.py          # 특허 FTO 채팅
│   │   ├── design.py        # 디자인 분석 (S3 + 멀티턴)
│   │   ├── project.py       # 프로젝트 관리
│   │   ├── analysis.py      # 분석 결과
│   │   └── search.py        # 특허 검색
│   │
│   ├── models/              # SQLAlchemy 모델
│   │   ├── user.py          # 사용자
│   │   ├── chat.py          # 채팅/메시지
│   │   ├── patent.py        # 특허 메타데이터
│   │   ├── analysis.py      # 분석 결과
│   │   ├── project.py       # 프로젝트
│   │   └── design_session.py # 디자인 세션 (S3/멀티턴)
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
│   │   ├── s3_service.py        # S3 이미지 업로드/삭제
│   │   ├── text_analyzer.py     # 텍스트 분석
│   │   └── image_analyzer.py    # 이미지 분석
│   │
│   └── utils/
│       └── runpod_keepalive.py  # RunPod 워밍업
│
├── requirements.txt         # Python 의존성
└── .env                     # 환경변수 (gitignore)
```

---

## API 엔드포인트

### 인증 (`/api/auth`)

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | `/signup` | 회원가입 |
| POST | `/login` | 로그인 (JWT 토큰 반환) |
| POST | `/check-email` | 이메일 중복 확인 |
| GET | `/me` | 현재 로그인 사용자 정보 |

### 특허 FTO 채팅 (`/api/chat`)

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | `/message` | FTO 분석 요청 (RAG + LLM) |
| GET | `/` | 채팅 목록 조회 |
| GET | `/{chat_id}` | 채팅 상세 조회 |

### 디자인 분석 (`/api/analysis/design`)

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/status` | 디자인 모듈 상태 확인 |
| POST | `/image` | 이미지 업로드 → S3 저장 → 유사 디자인 검색 |
| POST | `/select` | 디자인 선택 → FTO 리포트 생성 |
| POST | `/text` | 텍스트 질문 (멀티턴 대화) |
| GET | `/session/{thread_id}` | 세션 히스토리 조회 |

### 프로젝트 (`/api/projects`)

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/` | 프로젝트 목록 |
| POST | `/` | 프로젝트 생성 |
| GET | `/{id}` | 프로젝트 상세 |
| DELETE | `/{id}` | 프로젝트 삭제 |

---

## 데이터베이스 (AWS RDS)

### 연결 정보

```
Host: fto-db.c34w48m8sov6.ap-northeast-2.rds.amazonaws.com
Port: 3306
Database: fto
```

### 주요 테이블

```
patents (4만건)              ← 특허 메타데이터
├── apply_num (PK)           ← 출원번호
├── invention_title          ← 발명명
├── claim_pub                ← 공개 청구항
├── claim_regit              ← 등록 청구항
└── chunk_ids                ← ChromaDB 청크 ID

claim_keywords (1000만건)    ← Pre-filter용 키워드
├── patent_id
├── chunk_id
└── keyword

claim_components (26만건)    ← sLLM용 구성요소
├── patent_id
├── chunk_id
└── components

design_sessions              ← 디자인 분석 세션
├── thread_id
├── status
├── input_analysis
└── final_report

design_session_images        ← S3 이미지 URL
├── session_id
├── s3_key
└── s3_url

design_session_messages      ← 멀티턴 대화 히스토리
├── session_id
├── role
└── content
```

---

## 환경 설정 (.env)

```env
# RDS MySQL
DATABASE_URL=mysql+pymysql://admin:xxx@fto-db...rds.amazonaws.com:3306/fto

# JWT
SECRET_KEY=your-secret-key
ACCESS_TOKEN_EXPIRE_MINUTES=30

# RunPod Serverless
RUNPOD_API_KEY=xxx
RUNPOD_PATENT_BASE_URL=https://api.runpod.ai/v2/xxx/openai/v1
RUNPOD_DESIGN_BASE_URL=https://api.runpod.ai/v2/xxx/openai/v1

# AWS S3
AWS_ACCESS_KEY_ID=xxx
AWS_SECRET_ACCESS_KEY=xxx
S3_BUCKET_NAME=ftoguard-design-images
```

---

## 실행 방법

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

API 문서: http://localhost:8080/docs

---

## 연동 상태

| 기능 | 상태 |
|------|------|
| 회원가입/로그인 | ✅ 완료 |
| 특허 FTO 분석 (RAG + LLM) | ✅ 완료 |
| 디자인 이미지 분석 | ✅ 완료 |
| S3 이미지 저장 | ✅ 완료 |
| 멀티턴 대화 | ✅ 완료 |
| 프로젝트 관리 | ✅ 완료 |
