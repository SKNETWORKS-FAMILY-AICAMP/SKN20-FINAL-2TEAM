# FTO 프로젝트 - Claude 가이드

> **Claude에게**: 대화 시작 시 이 파일을 먼저 읽고 프로젝트 상황을 파악한 후 진행하세요.

## 프로젝트 목적

**상품 출시 전 특허 침해 여부 사전 검증 서비스 (FTO: Freedom To Operate)**
- 사용자가 출시하려는 제품이 기존 특허를 침해하는지 AI로 사전 판단

---

## 디렉토리 구조

```
SKN20-FINAL-2TEAM/
├── SLLM_model/                 # sLLM 학습 모듈 (구 bini/)
│   ├── training/               # 학습 스크립트
│   │   └── train_compare.py    # Gemma3 1B vs Qwen2.5 1.5B 비교 학습
│   ├── data/                   # 기존 학습 데이터 (35개, 레거시)
│   ├── outputs/                # 학습된 모델 저장소
│   │   ├── gemma3-1b-v2/       # Gemma3 1B (2869개 데이터 학습)
│   │   └── qwen2.5-1.5b-lora/  # Qwen2.5 1.5B
│   └── docs/                   # 문서
│
├── backend/                    # FastAPI 백엔드 (MySQL 연결)
│   ├── app/
│   │   ├── routers/            # API 라우터 (auth, chat, analysis, search)
│   │   ├── services/           # 비즈니스 로직 (search_service.py)
│   │   └── models/             # SQLAlchemy 모델
│   ├── Dockerfile
│   └── README.md
│
├── rag/                        # RAG 검색 모듈
│   ├── config.py               # 설정
│   ├── search.py               # 검색 (Dense + Sparse + 필터링)
│   ├── indexer.py              # 인덱싱 (MySQL → ChromaDB + BM25)
│   └── index/                  # 인덱스 저장소
│
├── FRONTEND/                   # 정적 HTML/JS 프론트엔드
│
├── scripts/                    # 유틸리티 스크립트
│
├── docker-compose.yml
├── fto_dump.sql
└── jsons_backup.zip
```

### 외부 데이터 (별도 repo)
```
/workspace/patent-data/GEMINI/sllm_1st_test/
├── data/
│   ├── sllm_train_2869.xlsx    # 학습 데이터 (2,869건)
│   └── sllm_test_718.xlsx      # 테스트 데이터 (718건)
└── eval/
    ├── 01_infer.py             # 모델 추론
    ├── 02_evaluate.py          # 개별 평가
    ├── 03_compare.py           # 모델 비교
    └── common.py               # 공통 유틸 (라벨 매핑, 법리 체크)
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

## sLLM 비교 학습

### 모델 비교

| 항목 | Gemma3 1B | Qwen2.5 1.5B |
|------|-----------|---------------|
| 모델 ID | `google/gemma-3-1b-it` | `Qwen/Qwen2.5-1.5B-Instruct` |
| 파라미터 | 1B | 1.5B |
| HF 토큰 필요 | **필요** (gated repo) | 불필요 |

### 학습 데이터 (2,869건 학습 / 718건 테스트)

| 라벨 | 학습 | 테스트 |
|------|------|--------|
| 침해 | 760 | 190 |
| 비침해 | 760 | 190 |
| 애매 | 589 | 148 |
| 침해_전문가 | 760 | 190 |

### 학습 실행 방법

```bash
# 0. HuggingFace 로그인 (Gemma3 접근용, 최초 1회)
pip install transformers>=4.48.0 datasets accelerate peft trl bitsandbytes pyyaml python-dotenv pandas openpyxl
huggingface-cli login --token <YOUR_HF_TOKEN>

# 1. 프로젝트 루트로 이동
cd /workspace/SKN20-FINAL-2TEAM

# 2. Gemma3 1B 학습
python -m SLLM_model.training.train_compare --model gemma

# 3. Qwen2.5 1.5B 학습
python -m SLLM_model.training.train_compare --model qwen

# 4. 둘 다 순차 학습 (gemma → qwen)
python -m SLLM_model.training.train_compare --model both

# 옵션: 에폭/배치/학습률 조정
python -m SLLM_model.training.train_compare --model both --epochs 5 --batch_size 4 --lr 3e-5
```

### 학습 설정 (기본값)

| 항목 | 값 |
|------|-----|
| 방법 | QLoRA (4-bit NF4) |
| LoRA r / alpha | 16 / 32 |
| max_seq_length | 4096 |
| batch_size | 2 |
| gradient_accumulation | 4 (effective batch = 8) |
| learning_rate | 2e-5 |
| epochs | 3 |
| optimizer | paged_adamw_8bit |
| precision | bf16 |

### 학습 완료 후 평가

```bash
cd /workspace/patent-data/GEMINI/sllm_1st_test/eval

# Gemma 추론
python 01_infer.py \
    --model_path /workspace/SKN20-FINAL-2TEAM/SLLM_model/outputs/gemma3-1b-v2 \
    --model_name gemma \
    --test_data ../data/sllm_test_718.xlsx

# Qwen 추론
python 01_infer.py \
    --model_path /workspace/SKN20-FINAL-2TEAM/SLLM_model/outputs/qwen2.5-1.5b-lora \
    --model_name qwen \
    --test_data ../data/sllm_test_718.xlsx

# 개별 평가
python 02_evaluate.py --input output/infer_gemma.xlsx --model_name gemma
python 02_evaluate.py --input output/infer_qwen.xlsx --model_name qwen

# 두 모델 비교
python 03_compare.py \
    --model_a output/eval_detail_gemma.xlsx \
    --model_b output/eval_detail_qwen.xlsx
```

### 평가 지표

| # | 항목 | 설명 |
|---|------|------|
| 1 | 라벨 정확도 | ◆결론◆ 키워드 → 라벨 추출 → 정답 비교 (F1) |
| 2 | 구조 완성도 | ◆구성 대비◆, ◆판단◆, ◆결론◆ 3섹션 존재 여부 |
| 3 | 행 수 일치 | 구성대비표 행 수 비교 |
| 4 | 법리 일관성 | 라벨 vs 대응분석표 논리 정합성 |

### 산출물

```
SLLM_model/outputs/
├── gemma3-1b-v2/              # Gemma3 1B LoRA adapter
└── qwen2.5-1.5b-lora/         # Qwen2.5 1.5B LoRA adapter
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

---

## 현재 상태 (2026-02-15 업데이트)

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
| bini/ → SLLM_model/ 리네이밍 | ✅ 완료 |
| sLLM 비교 학습 스크립트 작성 | ✅ 완료 |
| 학습 데이터 clone (patent-data repo) | ✅ 완료 |

### 진행 필요 (TODO)

| 항목 | 설명 | 우선순위 |
|------|------|----------|
| **sLLM 비교 학습 실행** | `train_compare.py` 실행 (Gemma3 1B / Qwen2.5 1.5B) | 🔴 높음 |
| **sLLM 평가** | 학습 완료 후 eval 스크립트로 비교 | 🔴 높음 |
| **RAG 인덱스 재빌드** | GPU 환경에서 `python -m rag.indexer` 실행 | 🔴 높음 |
| **백엔드-sLLM 연동** | 선택된 모델을 text_analyzer.py에 연결 | 🟡 중간 |
| **백엔드-RAG 연동** | search_service.py에서 rag.search() 호출 | 🟡 중간 |
| 디자인 분석 | 이미지 기반 검색 | 🟢 낮음 |

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
HF_TOKEN=your-huggingface-token
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
