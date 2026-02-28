# FTOGuard 배포 가이드

> 작성일: 2026-02-28
> 목표: Docker + AWS EC2 + RunPod Serverless 배포

---

## 왜 Docker인가? (EC2 직접 설치 vs Docker)

### 지금 상태 (EC2 직접 설치)

```
EC2에 pip install chromadb 해서 직접 실행중
→ 인덱스 오류 발생 (HNSW 인덱스 깨짐)
→ patent_chunks 컬렉션 검색 안 됨
→ 고치려면 EC2에 SSH 접속해서 디버깅해야 함
```

### Docker로 하면

```
chromadb/chroma 공식 이미지 사용
→ 데이터는 volume으로 분리 (폴더 마운트)
→ 문제 생기면 컨테이너 삭제 후 재생성 (데이터 유지)
→ 어디서든 동일하게 동작
```

### 비교

| 상황 | EC2 직접 설치 | Docker |
|------|-------------|--------|
| 설치 | pip install + 버전 충돌 해결 | `docker compose up` 한 줄 |
| 인덱스 깨지면 | SSH 접속 → 디버깅 → 재설치 | `docker compose restart` |
| 서버 옮길 때 | 처음부터 다시 세팅 | 폴더 복사 + `docker compose up` |
| 다른 팀원 PC에서 테스트 | 환경 맞추기 어려움 | Docker만 있으면 동일하게 실행 |
| 버전 관리 | pip 버전 꼬일 수 있음 | 이미지 태그로 고정 |
| 서버 재시작 | 수동으로 다시 실행 | `restart: always`로 자동 재시작 |

### ChromaDB Docker는 2개 따로 만든다

```
chromadb-patent  (컨테이너 1)  →  :8001  →  특허 벡터 (3.1GB)
chromadb-design  (컨테이너 2)  →  :8002  →  디자인 벡터 (75MB)
```

| | 하나에 합치기 | 따로 만들기 |
|---|---|---|
| 하나 죽으면 | 둘 다 죽음 | 나머지는 정상 |
| 데이터 교체 | 전체 재시작 | 해당 컨테이너만 재시작 |
| 디버깅 | 뭐가 문제인지 파악 어려움 | 로그 분리돼서 바로 파악 |

docker-compose.yml에서 서비스 2개로 정의하면 `docker compose up` 한 줄로 둘 다 뜬다. 관리는 따로, 실행은 같이.

### 핵심: Docker = 데이터와 프로그램 분리

```
[직접 설치]
ChromaDB 프로그램 + 데이터가 뒤섞임
→ 하나 잘못 건드리면 전체 깨짐 (지금 상태)

[Docker]
컨테이너: ChromaDB 프로그램 (언제든 삭제/재생성 가능)
    │
  volume 마운트
    │
폴더: 데이터 (컨테이너 삭제해도 안 사라짐)
→ 프로그램 문제면 컨테이너만 다시 만들면 끝
→ 데이터 문제면 폴더만 교체하면 끝
```

---

## 현재 인프라 현황

| 서비스 | 상태 | 비고 |
|--------|------|------|
| AWS RDS MySQL | 운영중 | patents 78,716건, claim_components 263,396건 |
| AWS EC2 t2.micro | 운영중 | ChromaDB 서빙 (인덱스 오류 발생중) |
| RunPod | 엔드포인트 있음 | Qwen 모델 서빙용 |

---

## 최종 아키텍처

```
┌────────────────────────────────────────────────────────┐
│  EC2 r6i.large (16GB RAM)    Docker Compose            │
│                                                        │
│  ┌──────────────┐  ┌───────────────┐  ┌─────────────┐ │
│  │  backend     │  │ chromadb      │  │ chromadb    │ │
│  │  FastAPI     │  │ -patent       │  │ -design     │ │
│  │  +RAG+KURE   │  │ :8001         │  │ :8002       │ │
│  │  +Frontend   │  │               │  │             │ │
│  │  :8080       │  │  📦 volume    │  │  📦 volume  │ │
│  └──────┬───────┘  └───────────────┘  └─────────────┘ │
└─────────┼──────────────────────────────────────────────┘
          │
    ┌─────▼──────┐     ┌──────────────────┐
    │  AWS RDS   │     │ RunPod Serverless │
    │  MySQL 8.4 │     │ 🤖 Qwen2.5-14B   │
    │            │     │ 🤖 Qwen2.5-VL-7B │
    └────────────┘     └──────────────────┘
```

### 왜 16GB RAM이 필요한가?

```
EC2 r6i.large (16GB RAM)
├── chromadb-patent  → 가벼움 (~200MB RAM)
├── chromadb-design  → 가벼움 (~100MB RAM)
└── backend (:8080)  → 무거움 ⚠️
    ├── FastAPI         → 가벼움
    ├── Frontend        → 가벼움
    ├── BM25 검색       → pkl 파일 로딩 (~500MB RAM)
    └── KURE-v1 모델    → 이게 문제 (~8~12GB RAM)
```

KURE 임베딩 모델이 RAM을 많이 먹는다. 사용자가 검색할 때 쿼리를 벡터로 변환하려면 이 모델이 메모리에 상주해야 한다.

```
사용자: "히알루론산 미백 화장품"
         │
    KURE-v1 모델 (RAM 8~12GB 상주)
         │
    [0.12, -0.45, 0.78, ...] 1024차원 벡터
         │
    ChromaDB에서 유사 특허 검색
```

> 16GB 필요한 이유 = KURE 모델만이 아니라 전체 RAG 스택 합산 때문.

### 메모리 상세 계산 (F32 기준)

```
├── KURE-v1                      ~3 GB   (0.6B params × F32)
├── CLIP ViT-B/32                ~600 MB (디자인 이미지 임베딩용)
├── BM25 인덱스                  ~500 MB (pkl → RAM 팽창)
├── LangGraph + 디자인 챗봇      ~300 MB
├── FastAPI + RAG 코드           ~200 MB
├── Python 런타임 + OS           ~500 MB
├── ChromaDB 컨테이너 2개        ~300 MB
                                ─────────
                    정상 상태:   ~5.4 GB
                    피크 시:     ~7~8 GB (동시요청, GC, 로그 등)
```

### EC2 인스턴스별 판단

| 인스턴스 | RAM | 판단 | 11일 비용 |
|----------|-----|------|----------|
| t3.medium (4GB) | 4 GB | ❌ 부족 | ~25,000원 |
| t3.large (8GB) | 8 GB | ⚠️ 가능은 함 (여유 적음) | ~40,000원 |
| r6i.large (16GB) | 16 GB | ✅ 안전 | ~57,000원 |

> t3는 burst CPU라서 RAG처럼 지속적으로 CPU 쓰는 작업에 적합하지 않음. r6i 권장.

---

## 폴더 → 배포 분류

```
SKN20-FINAL-2TEAM/
│
├── backend/                    ✅ Docker 이미지에 들어감 (코드)
│   ├── app/                    ✅
│   ├── requirements.txt        ✅
│   └── Dockerfile              🔄 새로 작성 필요
│
├── rag/
│   ├── __init__.py             ✅ Docker 이미지에 들어감 (코드)
│   ├── backend_adapter.py      ✅
│   ├── config.py               ✅ (환경변수 수정 필요)
│   ├── generate.py             ✅
│   ├── download_models.py      ✅
│   ├── requirements.txt        ✅
│   ├── search/                 ✅
│   ├── test/                   ❌ 배포 불필요
│   └── index/
│       ├── chroma_db/          📦 Docker volume (재구축 필요)
│       ├── bm25_index/         📦 Docker volume (173MB)
│       ├── tokenizer.py        ✅ Docker 이미지에 들어감
│       ├── parent_store/       ❌ 삭제 (RDS에 있음)
│       ├── claim_keywords.sqlite ❌ 삭제 (RDS에 올릴 예정)
│       └── chroma_db_js/       ❌ 삭제 (백업용)
│
├── design/
│   ├── src/                    ✅ Docker 이미지에 들어감 (코드)
│   ├── requirements.txt        ✅
│   └── chroma_db/              📦 Docker volume (75MB)
│
├── FRONTEND/                   ✅ Docker 이미지에 들어감 (정적파일)
│
├── SLLM_model/                 ❌ 배포 불필요
├── sql/                        ❌ 배포 불필요 (참고용)
├── .env                        ❌ Docker에 안 넣음 (환경변수로 주입)
├── docker-compose.yml          🔄 새로 작성 필요
├── Dockerfile                  🔄 새로 작성 필요
├── merge_upload.py             ❌ 배포 불필요
└── CLAUDE.md                   ❌ 배포 불필요

범례: ✅ 코드(Docker 이미지) / 📦 데이터(Docker volume) / ❌ 불필요 / 🔄 새로 만듦
```

---

## RDS 현황 (2026-02-28 확인)

| 테이블 | 건수 | 상태 |
|--------|------|------|
| patents | 78,716건 | 정상 |
| claim_components | 263,396건 | 정상 |
| claim_keywords | **없음** | **RDS에 올려야 함** |
| users | 11건 | 정상 |
| chats | 11건 | 정상 |
| messages | 28건 | 정상 |
| analyses | 7건 | 정상 |
| design_patents | 0건 | 빈 테이블 |
| image_matches | 0건 | 빈 테이블 |
| analysis_images | 0건 | 빈 테이블 |
| analysis_keywords | 0건 | 빈 테이블 |
| claim_matches | 0건 | 빈 테이블 |

> parents.sqlite (1.3GB) = RDS patents 테이블과 78,716건 전수 비교 100% 일치 확인됨

---

## 단계별 진행

### Step 1: ChromaDB 데이터 재구축

```
담당: RAG 담당
상태: 현재 chroma_db에 쓰레기 컬렉션 2개 포함
      patent_chunks (사용) + patent_claims (빈것) + patent_chunks_rebuild (실패)
할 일:
  - 깨끗한 chroma_db/ 생성 (patent_chunks 컬렉션만)
  - KURE-v1 임베딩, 1024차원, cosine
결과물: 깨끗한 chroma_db/ 폴더
```

### Step 2: claim_keywords RDS 업로드

```
담당: DB 담당
할 일:
  1. RDS에 claim_keywords 테이블 생성
     CREATE TABLE claim_keywords (
       id BIGINT AUTO_INCREMENT PRIMARY KEY,
       patent_id VARCHAR(50),
       chunk_id VARCHAR(100),
       keyword VARCHAR(255),
       KEY idx_patent_id (patent_id),
       KEY idx_chunk_id (chunk_id),
       KEY idx_keyword (keyword)
     );
  2. 데이터 INSERT (약 1000만건)
  3. 확인: SELECT COUNT(*) FROM claim_keywords
결과물: RDS claim_keywords 테이블 (약 1000만건)
```

### Step 3: RunPod Serverless 모델 배포

```
담당: 모델 담당
할 일:
  - Endpoint A: itsbini/qwen2.5-14b-fto-merged (특허 FTO)
    GPU: A100 80GB 또는 A40 48GB
  - Endpoint B: Qwen/Qwen2.5-VL-7B-Instruct (디자인 VLM)
    GPU: RTX 4090 24GB 또는 A40 48GB
  - 둘 다 Network Volume 연결 (cold start 단축)
결과물: RunPod Endpoint URL 2개
확인: curl로 OpenAI-compatible API 호출 테스트
```

### Step 4: 로컬 테스트

```
담당: 백엔드 담당
할 일:
  1. .env 수정
     VLLM_BASE_URL=https://api.runpod.ai/v2/{ENDPOINT_ID}/openai/v1
     MYSQL_HOST=fto-db.c34w48m8sov6.ap-northeast-2.rds.amazonaws.com
     CHROMA_HOST=localhost
     CHROMA_PORT=8001

  2. 로컬에서 ChromaDB Docker 실행
     docker compose -f docker-compose.chromadb.yml up -d

  3. 로컬에서 백엔드 실행
     uvicorn backend.app.main:app --port 8080

  4. 브라우저 테스트
     http://localhost:8080
확인: 특허 검색 + 디자인 분석 모두 동작
```

### Step 5: Docker 이미지 빌드

```
담당: 백엔드 담당
할 일:
  1. Dockerfile 작성 (backend + rag + design + frontend 통합)
  2. docker-compose.yml 작성 (backend + chromadb x2)
  3. docker compose up -d 로 전체 테스트
확인: Docker 환경에서 전체 동작
```

### Step 6: EC2 배포

```
담당: 인프라 담당
할 일:
  1. EC2 r6i.large 생성 (16GB RAM, 서울 리전)
  2. Docker, Docker Compose 설치
  3. 보안그룹: 8080 포트 열기
  4. 데이터 업로드 (scp 또는 S3):
     - chroma_db/ (특허, 3.1GB)
     - chroma_db/ (디자인, 75MB)
     - bm25_index/ (173MB)
  5. git clone + docker compose up -d
확인: http://EC2_PUBLIC_IP:8080 접속
```

### Step 7: 기존 인프라 정리

```
- EC2 t2.micro (기존 ChromaDB) → 중지
- RunPod Pod (기존 상시 가동) → 중지
```

---

## Docker 파일 구성

### EC2 배포 폴더 구조

```
/home/ec2-user/fto-deploy/
├── docker-compose.yml          서비스 정의
├── Dockerfile                  백엔드 이미지
├── .env                        환경변수
├── backend/                    코드 (git)
├── rag/                        코드 (git, index/ 제외)
├── design/src/                 코드 (git)
├── FRONTEND/                   정적파일 (git)
└── data/                       데이터 (git 미포함, 수동 업로드)
    ├── chroma-patent/          특허 ChromaDB (3.1GB)
    ├── chroma-design/          디자인 ChromaDB (75MB)
    └── bm25_index/             BM25 인덱스 (173MB)
```

### docker-compose.yml

```yaml
version: '3.8'

services:
  backend:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8080:8080"
    environment:
      - DATABASE_URL=mysql+pymysql://${MYSQL_USER}:${MYSQL_PASSWORD}@${MYSQL_HOST}:3306/${MYSQL_DATABASE}
      - MYSQL_HOST=${MYSQL_HOST}
      - MYSQL_PORT=3306
      - MYSQL_USER=${MYSQL_USER}
      - MYSQL_PASSWORD=${MYSQL_PASSWORD}
      - MYSQL_DATABASE=${MYSQL_DATABASE}
      - CHROMA_HOST=chromadb-patent
      - CHROMA_PORT=8000
      - CHROMA_IMAGE_HOST=chromadb-design
      - CHROMA_IMAGE_PORT=8000
      - VLLM_BASE_URL=${VLLM_BASE_URL}
      - RUNPOD_API_KEY=${RUNPOD_API_KEY}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - DEV_BYPASS_AUTH=true
    volumes:
      - ./data/bm25_index:/app/rag/index/bm25_index
    depends_on:
      - chromadb-patent
      - chromadb-design
    restart: always

  chromadb-patent:
    image: chromadb/chroma:latest
    volumes:
      - ./data/chroma-patent:/chroma/chroma
    restart: always

  chromadb-design:
    image: chromadb/chroma:latest
    volumes:
      - ./data/chroma-design:/chroma/chroma
    restart: always
```

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc g++ default-libmysqlclient-dev pkg-config git \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /tmp/backend-req.txt
COPY rag/requirements.txt /tmp/rag-req.txt
COPY design/requirements.txt /tmp/design-req.txt
RUN pip install --no-cache-dir \
    -r /tmp/backend-req.txt \
    -r /tmp/rag-req.txt \
    -r /tmp/design-req.txt

COPY backend/ /app/backend/
COPY rag/ /app/rag/
COPY design/ /app/design/
COPY FRONTEND/ /app/FRONTEND/

EXPOSE 8080
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

### .env (EC2용)

```env
MYSQL_HOST=fto-db.c34w48m8sov6.ap-northeast-2.rds.amazonaws.com
MYSQL_PORT=3306
MYSQL_USER=admin
MYSQL_PASSWORD=rmdak2020
MYSQL_DATABASE=fto
VLLM_BASE_URL=https://api.runpod.ai/v2/{ENDPOINT_ID}/openai/v1
RUNPOD_API_KEY={RunPod API 키}
OPENAI_API_KEY={OpenAI API 키}
DEV_BYPASS_AUTH=true
SECRET_KEY=demo-secret-key-2026
```

---

## 비용 (11일, 3월 11일까지)

| 항목 | 예상 비용 |
|------|----------|
| EC2 r6i.large (11일) | ~57,000원 |
| RDS MySQL (11일) | ~7,000원 |
| 기타 AWS | ~5,000원 |
| **AWS 합계** | **~70,000원** (30만원 예산) |
| RunPod Serverless (11일) | ~$30~50 ($100 예산) |

---

## 접속 정보

| 서비스 | 주소 |
|--------|------|
| RDS MySQL | fto-db.c34w48m8sov6.ap-northeast-2.rds.amazonaws.com:3306 |
| EC2 현재 (ChromaDB) | 52.78.233.64 (포트 8001, 8002) |
| EC2 신규 (Docker) | 생성 후 기입 |
| RunPod Endpoint A (14B) | 생성 후 기입 |
| RunPod Endpoint B (7B) | 생성 후 기입 |

---

## FAQ: KURE 임베딩 모델을 RunPod Serverless에 올리면?

할 수는 있지만 추천하지 않는다.

```
[EC2에서 KURE 실행 (추천)]
사용자 → EC2 backend → KURE (같은 서버, 즉시) → ChromaDB
                        소요: ~0.1초

[KURE 서버리스]
사용자 → EC2 backend → RunPod KURE (네트워크 왕복) → EC2 → ChromaDB
                        소요: ~1~3초 + cold start 위험
```

| | EC2에서 KURE (추천) | RunPod Serverless KURE |
|---|---|---|
| 검색 속도 | ~0.1초 | ~1~3초 (네트워크 왕복) |
| cold start | 없음 | 모델 로딩 10~30초 |
| EC2 비용 (11일) | r6i.large ~57,000원 | t3.medium ~25,000원 |
| RunPod 비용 | 없음 | 추가 발생 |
| 구조 복잡도 | 단순 | 엔드포인트 하나 더 관리 |

> 32,000원 아끼려고 검색마다 1~3초 느려지고 cold start 리스크까지 생긴다.
> r6i.large 쓸 수 있으면 EC2에서 돌리는 게 훨씬 낫다.