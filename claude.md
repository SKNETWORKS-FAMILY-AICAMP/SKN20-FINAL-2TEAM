# FTO 프로젝트 - Claude 가이드

> **Claude에게**: 대화 시작 시 이 파일을 먼저 읽고 프로젝트 상황을 파악한 후 진행하세요.

## 프로젝트 목적

**상품 출시 전 특허/디자인 침해 여부 사전 검증 서비스 (FTO: Freedom To Operate)**
- 사용자가 출시하려는 제품이 기존 특허/디자인을 침해하는지 AI로 사전 판단
- 팀명: 긍마 / SKN20-FINAL-2TEAM
- 개발기간: 2026.01.09 ~ 2026.03.11

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
│   │   ├── qwen2.5-1.5b-v2/
│   │   ├── qwen2.5-3b-lora/
│   │   └── qwen2.5-14b-lora/   # 학습 완료
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
├── design/                     # 디자인 유사도 분석 챗봇 (CLIP + VLM)
└── docker-compose.yml          # EC2 배포용 (RDS 연결)
```

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

---

## sLLM 모델 학습 현황

### 목표: 파인튜닝된 작은 모델 > 파인튜닝 안 된 큰 모델 입증

| 모델 | 파인튜닝 | 정확도 | 구조성공률 | 법리일관성 | 행수일치율 | HuggingFace |
|------|----------|--------|-----------|-----------|-----------|-------------|
| Qwen 1.5B | ✅ | 86.2% | 97.3% | 99.6% | 97.5% | itsbini/qwen2.5-1.5b-fto |
| Qwen 3B | ❌ 베이스 | 30.1% | 85.2% | 91.3% | 29.3% | - |
| Qwen 3B | ✅ | 89.5% | 98.9% | 99.6% | 99.3% | itsbini/qwen2.5-3b-fto |
| Qwen 7B | ❌ 베이스 | 31.8% | 98.0% | 48.1% | 70.8% | - |
| Qwen 7B | ✅ | 평가 예정 | - | - | - | 업로드 완료 |
| Qwen 14B | ✅ | 평가 예정 | - | - | - | itsbini/qwen2.5-14b-fto |

### 입증 완료
- ✅ 학습된 1.5B (86.2%) > 학습 안 한 3B (30.1%)
- ✅ 학습된 3B (89.5%) > 학습 안 한 7B (31.8%)

### 추론 완료 파일 (`sllm_smalltrain_dj/eval/output/`)
- `infer_qwen_v2.xlsx` / `eval_detail_qwen_v2.xlsx` — 1.5B FT
- `infer_qwen3b_base.xlsx` / `eval_detail_qwen3b_base.xlsx` — 3B 베이스
- `infer_qwen3b_ft.xlsx` / `eval_detail_qwen3b_ft.xlsx` — 3B FT
- `infer_qwen7b_base.xlsx` / `eval_detail_qwen7b_base.xlsx` — 7B 베이스
- `infer_qwen14b_ft.xlsx` — 14B FT 추론 완료 (평가 미완료)

---

## 검색 파이프라인

```
사용자 Query
    ↓
[RAG 검색] rag/pipeline.py
    ├── 멀티쿼리 생성 (최대 8개)
    ├── Dense 검색 (KURE-v1 + ChromaDB)
    ├── Sparse 검색 (BM25 + kiwipiepy)
    └── RRF 점수 합산 → 상위 10개
    ↓
[필터링] 등록 상태 확인 + 금반언 표시
    ↓
[sLLM 분석] → 침해/비침해/애매/침해_전문가 판단
```

---

## 데이터베이스 스키마

| 테이블 | 건수 | 용도 |
|--------|------|------|
| `patents` | 3,271 | 특허 기본 정보 |
| `patent_ipc` | 17,273 | IPC 분류코드 |
| `claims` | 158,584 | 청구항 (금반언 지원) |
| `claim_elements` | 763,719 | 키워드 검색용 요소 |

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
- [ ] **14B FT 평가 실행**
  ```bash
  cd /root/SKN20-FINAL-2TEAM/SLLM_model/sllm_smalltrain_dj/eval
  python 02_evaluate.py --input output/infer_qwen14b_ft.xlsx --model_name qwen14b_ft
  ```
- [ ] **팀원 DB 데이터 취합 → RDS import**
  - 각 팀원: `mysqldump -u root -p fto > fto_dump.sql`
  - EC2로 전송: `scp -i ~/Downloads/fto-key.pem fto_dump.sql ubuntu@52.78.233.64:~/`
  - RDS import: `mysql -h fto-db.c34w48m8sov6.ap-northeast-2.rds.amazonaws.com -u admin -p fto < fto_dump.sql`
- [ ] **EC2 배포 실행**
  ```bash
  # EC2에서
  cd SKN20-FINAL-2TEAM
  git pull origin main
  sudo docker-compose up --build -d
  ```

### 🟡 중간
- [ ] **14B 베이스 추론 및 비교** (7B FT vs 14B 베이스 입증)
  ```bash
  python 01_infer_vllm.py --model_path Qwen/Qwen2.5-14B-Instruct --model_name qwen14b_base --gpu_memory 0.85
  ```
- [ ] **백엔드 .env 파일 분리** (docker-compose.yml에 비밀번호 노출됨)
- [ ] **백엔드-sLLM 연동** (`text_analyzer.py`에 실제 모델 호출 구현)
- [ ] **백엔드-RAG 연동** (`search_service.py`에서 RAG 파이프라인 호출)
- [ ] **CORS 설정** (EC2 퍼블릭 IP `52.78.233.64` 추가)

### 🟢 낮음
- [ ] **테스트 계획 및 결과 보고서 완성** (`GPT_prompt_테스트계획및결과보고서.md` 활용)
- [ ] **LLM 활용 소프트웨어 산출물 완성** (`GPT_prompt_llm_산출물.md` 활용)

---

## 팀 정보

- GitHub: https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN20-FINAL-2TEAM
- RunPod 작업 경로: `/root/SKN20-FINAL-2TEAM`
