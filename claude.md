# FTO 프로젝트 - Claude 가이드

> **Claude에게**: 대화 시작 시 이 파일을 먼저 읽고 프로젝트 상황을 파악한 후 진행하세요.

## 프로젝트 목적

**상품 출시 전 특허 침해 여부 사전 검증 서비스 (FTO: Freedom To Operate)**
- 사용자가 출시하려는 제품이 기존 특허를 침해하는지 AI로 사전 판단

---

## 디렉토리 구조

```
SKN20-FINAL-2TEAM/
├── bini/                    # 핵심 sLLM 학습 모듈
│   ├── training/            # 학습/평가/추론 스크립트
│   ├── data/                # 학습 데이터
│   ├── outputs/             # 학습된 모델 (gemma3-1b-it-lora)
│   └── docs/                # 문서 (ERD, 학습 리포트)
│
├── backend/                 # FastAPI 백엔드 (MySQL 연결)
│   ├── app/
│   │   ├── routers/         # API 라우터 (auth, chat, analysis, search)
│   │   ├── services/        # 비즈니스 로직 (search_service.py)
│   │   └── models/          # SQLAlchemy 모델
│   ├── Dockerfile           # Docker 이미지 빌드
│   └── README.md            # 백엔드 상세 문서
│
├── rag/                     # RAG 검색 모듈 (단순화됨)
│   ├── config.py            # 설정
│   ├── search.py            # 검색 (Dense + Sparse + 필터링)
│   ├── indexer.py           # 인덱싱 (MySQL → ChromaDB + BM25)
│   ├── _backup/             # 기존 복잡한 RAG 코드 백업
│   └── index/               # 인덱스 저장소
│       ├── chroma_db/       # 벡터 DB
│       └── bm25.pkl         # BM25 인덱스
│
├── FRONTEND/                # 정적 HTML/JS 프론트엔드
│
├── scripts/                 # 유틸리티 스크립트
│   ├── import_patents.py    # 특허 JSON → MySQL import
│   └── reprocess_elements.py # claim_elements 재처리 (kiwipiepy)
│
├── docker-compose.yml       # Docker 전체 구성
├── fto_dump.sql            # MySQL 데이터 dump
└── jsons_backup.zip         # 원본 특허 JSON 백업 (3,271개)
```

---

## 검색 파이프라인

```
사용자 Query
    ↓
[RAG 검색] rag/search.py
    ├── Dense 검색 (KURE-v1 + ChromaDB)
    ├── Sparse 검색 (BM25 + kiwipiepy)
    └── RRF 점수 합산
    ↓
[MySQL 필터링]
    ├── 등록 상태 확인 (REGISTERED_ONLY)
    ├── 금반언 표시 (ESTOPPEL_ENABLED)
    └── 청구항 정보 보강
    ↓
[sLLM 분석] → 침해 여부 판단
```

---

## RAG 사용법

```python
# 검색
from rag import search
results = search("헤스페리딘이 포함된 화장료", top_k=10)

# 간단한 검색 (MySQL 필터 없이)
from rag import search_simple
results = search_simple("헤스페리딘 화장료")

# 인덱스 재빌드 (GPU 환경에서 실행 권장)
python -m rag.indexer
```

---

## MySQL 데이터베이스

### 연결 정보

| 환경 | Host | Port | Database | User | Password |
|------|------|------|----------|------|----------|
| 로컬 | localhost | 3306 | fto | root | newpassword123 |
| Docker | fto-db | 3306 | fto | root | root1234 |

### 테이블 구조

| 테이블 | 건수 | 용도 |
|--------|------|------|
| `patents` | 3,271 | 특허 기본 정보 |
| `patent_ipc` | 17,273 | IPC 분류코드 (1:N) |
| `claims` | 158,584 | 청구항 (first/last 버전, 금반언 지원) |
| `claim_elements` | 635,201 | 키워드 검색용 요소 (kiwipiepy 형태소 분석) |

### claim_elements 요소 타입

| 타입 | 건수 | 예시 |
|------|------|------|
| 기타 | 535,391 | 조성, 선택, 치료 |
| 성분 | 88,564 | 화합물, 항체, 단백질, 추출물 |
| 방법 | 11,246 | 제조, 처리, 반응 |

---

## 현재 상태 (2026-02-13 업데이트)

### 완료

| 항목 | 상태 |
|------|------|
| MySQL 설정 및 데이터 import | ✅ 완료 |
| 특허 RDB 검색 (키워드/전문) | ✅ 완료 |
| 금반언 지원 | ✅ 완료 |
| 회원가입/로그인 (JWT) | ✅ 완료 |
| Docker 설정 | ✅ 완료 |
| 프론트엔드-백엔드 API 연동 | ✅ 완료 |
| claim_elements 형태소 분석 재처리 (kiwipiepy) | ✅ 완료 |
| RAG 구조 단순화 (search.py, indexer.py 통합) | ✅ 완료 |

### 진행 필요 (TODO)

| 항목 | 설명 | 우선순위 |
|------|------|----------|
| **RAG 인덱스 재빌드** | GPU 환경에서 `python -m rag.indexer` 실행 | 🔴 높음 |
| **RAG 검색 테스트** | 인덱스 재빌드 후 검색 테스트 | 🔴 높음 |
| **백엔드-RAG 연동** | search_service.py에서 rag.search() 호출 | 🟡 중간 |
| sLLM 연동 | text_analyzer.py에서 모델 호출 | 🟡 중간 |
| 디자인 분석 | 이미지 기반 검색 | 🟢 낮음 |

---

## RAG 인덱스 재빌드 방법 (GPU 환경)

```bash
# 1. 의존성 설치
pip install sentence-transformers chromadb rank_bm25 kiwipiepy sqlalchemy pymysql

# 2. MySQL 연결 확인
# rag/config.py의 DATABASE_URL 확인

# 3. 인덱스 빌드
cd SKN20-FINAL-2TEAM
python -m rag.indexer

# 예상 결과:
# - MySQL에서 등록된 특허 독립항 로드 (~6,600개)
# - ChromaDB 벡터 인덱스 생성
# - BM25 스파스 인덱스 생성
```

---

## 백엔드 API

### 인증 (`/api/auth`)
| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | `/signup` | 회원가입 |
| POST | `/login` | 로그인 (JWT) |
| POST | `/check-email` | 이메일 중복 확인 |
| GET | `/me` | 현재 사용자 정보 |

### 검색 (`/api/search`)
| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/keywords?q=` | 키워드 기반 특허 검색 |
| GET | `/fulltext?q=` | 전문 검색 |
| POST | `/hybrid` | 하이브리드 검색 (RDB + RAG) |

### 분석 (`/api/analysis`)
| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | `/text` | 텍스트 기반 FTO 분석 |
| POST | `/image` | 이미지 기반 디자인 분석 |

---

## 환경 설정

### backend/.env (로컬)
```
DATABASE_URL=mysql+pymysql://root:newpassword123@localhost:3306/fto
SECRET_KEY=your-secret-key
```

### rag/config.py
```python
DATABASE_URL = "mysql+pymysql://root:newpassword123@localhost:3306/fto"
EMBED_MODEL = "nlpai-lab/KURE-v1"
```

---

## 팀 정보

- 프로젝트: SKN20-FINAL-2TEAM (FTO)
- GitHub: SKNETWORKS-FAMILY-AICAMP/SKN20-FINAL-2TEAM
