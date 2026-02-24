# FTO 프로젝트 - Claude 가이드

> **Claude에게**: 대화 시작 시 이 파일을 먼저 읽고 프로젝트 상황을 파악한 후 진행하세요.

## 프로젝트 목적

**상품 출시 전 특허/디자인 침해 여부 사전 검증 서비스 (FTO: Freedom To Operate)**
- 사용자가 출시하려는 제품이 기존 특허/디자인을 침해하는지 AI로 사전 판단
- 팀명: 긍마 / SKN20-FINAL-2TEAM
- 개발기간: 2026.01.09 ~ 2026.03.11

---

## 서비스 플로우

### 1. 특허 침해 분석 (텍스트)

```
사용자 쿼리 입력
    ↓
[Pre-filter] claim_keywords 테이블에서 쿼리 요소 매칭 → ~1000개 patent_id
    ↓
[RAG] BM25 + Dense (ChromaDB) → 상위 5개 청구항
    ↓
[sLLM] claim_components에서 구성요소 가져와서 침해 여부 판단
    ↓
결과: 침해 / 비침해 / 애매 / 침해_전문가
```

### 2. 이미지 특허 침해 분석

```
이미지 업로드
    ↓
[이미지 RAG] BM25 + Dense (ChromaDB) → 유사 이미지 검색
    ↓
design_patents 테이블에서 image_url 조회
    ↓
결과 이미지 표시
```

---

## 디렉토리 구조

```
SKN20-FINAL-2TEAM/
├── SLLM_model/                 # sLLM 학습 모듈
│   ├── training/               # 학습 스크립트
│   │   ├── train_qwen_v2.py    # 1.5B 학습
│   │   ├── train_qwen3b.py     # 3B 학습
│   │   ├── train_qwen14b.py    # 14B 학습
│   │   └── upload_hf.py        # HuggingFace 업로드
│   ├── data/sllm_qwen_data/    # 학습 데이터 (17,377건 / 4,317건)
│   ├── outputs/                # 학습된 모델 저장소
│   └── sllm_smalltrain_dj/eval/ # 추론 및 평가 스크립트
│
├── backend/                    # FastAPI 백엔드
│   ├── app/
│   │   ├── routers/            # auth, chat, analysis, search
│   │   ├── services/           # 비즈니스 로직
│   │   └── models/             # SQLAlchemy 모델
│   └── Dockerfile
│
├── rag/                        # RAG 검색 모듈 (Dense+Sparse+RRF)
├── FRONTEND/                   # Nginx 정적 HTML/JS 프론트엔드
├── design/                     # 디자인 유사도 분석 (CLIP + VLM)
├── sql/                        # DB 스키마 및 마이그레이션
│   └── fto_schema.sql          # RDS 테이블 정의
└── docker-compose.yml          # EC2 배포용 (RDS 연결)
```

---

## 데이터 저장소 구조

### MySQL (AWS RDS) - 메타데이터 + Pre-filter

| 테이블 | 건수 | 용도 | 담당 |
|--------|------|------|------|
| `patents` | - | 특허 기본 정보 | - |
| `claims` | - | 청구항 텍스트 (BM25용) | - |
| `claim_keywords` | ~1000만 | Pre-filter용 키워드 | 팀원1 |
| `claim_components` | ~26만 | sLLM용 구성요소 | 팀원1 |
| `design_patents` | - | 디자인 특허 + 이미지 URL | 팀원3 |
| `users`, `chats`, `messages` | - | 서비스 데이터 | - |
| `analyses`, `*_matches` | - | 분석 결과 | - |

### ChromaDB (EC2) - 벡터 검색

| 디렉토리 | 용도 | 담당 |
|----------|------|------|
| `/data/chroma/claims/` | 청구항 Dense 검색 | 팀원2 |
| `/data/chroma/images/` | 이미지 Dense 검색 | 팀원3 |

---

## 팀원별 데이터 현황

| 팀원 | 데이터 | 저장소 | 상태 |
|------|--------|--------|------|
| 본인 | 스키마, 통합 | RDS | ✅ 스키마 생성 완료 |
| 팀원1 | claim_keywords (~1000만), claim_components (~26만) | RDS | 🔄 업로드 중 |
| 팀원2 | 청구항 벡터 (ChromaDB) | EC2 | ⏳ 대기 |
| 팀원3 | 이미지 벡터 (ChromaDB) + design_patents | EC2 + RDS | ⏳ 대기 |

---

## AWS 인프라 (2026-02-24 구성)

| 항목 | 값 |
|------|-----|
| EC2 퍼블릭 IP | `52.78.233.64` |
| EC2 인스턴스 ID | `i-025ca49992ebcd3cc` |
| EC2 OS | Ubuntu 24.04 LTS (t2.micro) |
| RDS 엔드포인트 | `fto-db.c34w48m8sov6.ap-northeast-2.rds.amazonaws.com` |
| RDS 엔진 | MySQL 8.4 (db.t3.micro) |
| RDS DB명 | `fto` |
| RDS 유저 | `admin` |
| 리전 | ap-northeast-2 (서울) |
| SSH 키 | `fto-key.pem` |

### EC2 접속
```bash
ssh -i ~/Downloads/fto-key.pem ubuntu@52.78.233.64
```

### RDS 접속 (EC2에서)
```bash
mysql -h fto-db.c34w48m8sov6.ap-northeast-2.rds.amazonaws.com -u admin -p fto
```

---

## sLLM 모델 학습 현황

### 목표: 파인튜닝된 작은 모델 > 파인튜닝 안 된 큰 모델 입증

| 모델 | 파인튜닝 | 정확도 | 구조성공률 | 법리일관성 | 행수일치율 | HuggingFace |
|------|----------|--------|-----------|-----------|-----------|-------------|
| Qwen 1.5B | ✅ | 86.2% | 97.3% | 99.6% | 97.5% | itsbini/qwen2.5-1.5b-fto |
| Qwen 3B | ❌ 베이스 | 30.1% | 85.2% | 91.3% | 29.3% | - |
| Qwen 3B | ✅ | 89.5% | 98.9% | 99.6% | 99.3% | itsbini/qwen2.5-3b-fto |
| Qwen 7B | ❌ 베이스 | 31.8% | 98.0% | 48.1% | 70.8% | - |
| Qwen 14B | ✅ | **94.3%** | 99.7% | 99.6% | 100.0% | itsbini/qwen2.5-14b-fto |

### 입증 완료
- ✅ 학습된 1.5B (86.2%) > 학습 안 한 3B (30.1%)
- ✅ 학습된 3B (89.5%) > 학습 안 한 7B (31.8%)

---

## 백엔드 API

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | `/api/auth/signup` | 회원가입 |
| POST | `/api/auth/login` | 로그인 (JWT) |
| POST | `/api/analysis/text` | 텍스트 FTO 분석 |
| POST | `/api/analysis/image` | 이미지 디자인 분석 |
| GET | `/api/search/keywords` | 키워드 검색 |
| POST | `/api/search/hybrid` | 하이브리드 검색 |

---

## TODO (남은 작업)

### 🔴 높음
- [x] **RDS 스키마 생성** (`sql/fto_schema.sql`)
- [x] **claim_keywords 업로드** (~1000만건)
- [ ] **claim_components 업로드** (~26만건) - 팀원1에게 CSV 받기
- [ ] **ChromaDB 파일 EC2 전송** - 팀원2, 팀원3
- [ ] **EC2 배포 실행**
  ```bash
  cd SKN20-FINAL-2TEAM && git pull origin main
  sudo docker-compose up --build -d
  ```

### 🟡 중간
- [ ] **백엔드-sLLM 연동** (`text_analyzer.py`에 모델 호출)
- [ ] **백엔드-RAG 연동** (`search_service.py`에서 RAG 파이프라인)
- [ ] **백엔드 .env 파일 분리** (비밀번호 노출 방지)
- [ ] **CORS 설정** (EC2 IP 추가)

### 🟢 낮음
- [ ] **14B 베이스 추론** (7B FT vs 14B 베이스 비교)
- [ ] **테스트 계획 및 결과 보고서**
- [ ] **LLM 활용 소프트웨어 산출물**

---

## 팀원 데이터 취합 가이드

### 팀원1: claim_components CSV 업로드
```bash
# 1. CSV를 EC2로 전송
scp -i ~/Downloads/fto-key.pem claim_components.csv ubuntu@52.78.233.64:~/

# 2. EC2에서 RDS로 로드
ssh -i ~/Downloads/fto-key.pem ubuntu@52.78.233.64
mysql -h fto-db.c34w48m8sov6.ap-northeast-2.rds.amazonaws.com -u admin -p --local-infile=1 fto

# MySQL에서:
LOAD DATA LOCAL INFILE '/home/ubuntu/claim_components.csv'
INTO TABLE claim_components
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 ROWS
(patent_id, chunk_id, components, note);
```

### 팀원2, 팀원3: ChromaDB 파일 전송
```bash
# ChromaDB 디렉토리 압축
tar -czvf chroma_claims.tar.gz ./chroma_db/

# EC2로 전송
scp -i ~/Downloads/fto-key.pem chroma_claims.tar.gz ubuntu@52.78.233.64:~/

# EC2에서 압축 해제
ssh -i ~/Downloads/fto-key.pem ubuntu@52.78.233.64
mkdir -p /data/chroma/claims
tar -xzvf chroma_claims.tar.gz -C /data/chroma/claims/
```

---

## 팀 정보

- GitHub: https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN20-FINAL-2TEAM
- RunPod 작업 경로: `/root/SKN20-FINAL-2TEAM`
