> **Claude에게**: 대화 시작 시 이 파일을 먼저 읽고 프로젝트 상황을 파악한 후 진행하세요.

# BINI 프로젝트 - Claude 가이드

## 프로젝트 개요

**상품 출시 전 특허 침해 여부 사전 검증 서비스**

### 서비스 대상
- 상품을 출시하려는 사람
- 특허 침해 여부를 사전에 확인하고 싶은 사람

### 핵심 기능
1. **이미지 분석**: 제품 이미지 → 로카르노 분류 → 이미지 RAG → 유사도 모델 → LLM 답변
2. **텍스트 분석**: 제품 설명 → 키워드 추출 → 청구항 RAG → Rerank → sLLM 답변
3. **채팅 기록**: 로그인 사용자만 사용 가능, 채팅 기록 저장/조회

---

## 시스템 아키텍처

### 이미지 입력 플로우
```
이미지 업로드 → 로카르노 분류 (자동) → 이미지 RAG (Top 20) → 유사도 모델 검증 → LLM 답변
```

### 텍스트 입력 플로우
```
텍스트 입력 → Key값 추출 → 청구항 RAG → Rerank → sLLM 답변
```

---

## 현재 상태

### 완료된 작업
- [x] 프로젝트 구조 설정
- [x] 청구항 데이터 (seed_cases.json, train.jsonl)
- [x] sLLM 학습 (Gemma 1B + LoRA) - 97.1% 정확도
- [x] 평가/추론/비교 스크립트
- [x] ERD 설계 완료 (ERD_FINAL.md)

### 진행 중인 작업 (팀원)
- [ ] 디자인 특허 이미지 데이터 수집
- [ ] 이미지 유사도 모델 학습

### 해야 할 작업
- [ ] **4B 모델 학습** (다음 작업 - 아래 상세 참조)
- [ ] 로카르노 분류 모델
- [ ] 이미지 RAG 시스템
- [ ] 텍스트 RAG 시스템 (청구항)
- [ ] Reranker 적용
- [ ] 백엔드 API 개발
- [ ] 프론트엔드 개발
- [ ] 로그인/회원가입 시스템

---

## 파일 구조

```
bini/
├── data/
│   ├── raw/seeds/
│   │   └── seed_cases.json       # 텍스트 학습 데이터
│   ├── processed/
│   │   ├── train.jsonl           # 라벨 데이터
│   │   └── sft_train.jsonl       # SFT 학습 데이터
│   └── schema/
│       └── output_schema.json    # 출력 스키마
│
├── training/
│   ├── train.py                  # sLLM 학습 스크립트
│   ├── evaluate.py               # 평가 스크립트
│   ├── inference.py              # 추론 스크립트
│   ├── compare_models.py         # 모델 비교
│   ├── build_sft_jsonl.py        # 데이터셋 빌더
│   ├── lora_config.yaml          # LoRA 설정
│   └── requirements.txt          # 의존성
│
├── outputs/
│   └── gemma3-1b-it-lora/        # 학습된 sLLM
│
└── docs/
    ├── ERD_FINAL.md              # 최종 ERD (13개 테이블)
    ├── TRAINING_REPORT.md        # 학습 결과 리포트
    └── PRESENTATION_GUIDE.md     # 발표 가이드
```

---

## 모델 현황

### sLLM (텍스트 분석용)
| 항목 | 내용 |
|------|------|
| 베이스 모델 | google/gemma-3-1b-it |
| 학습 방법 | LoRA (r=16, alpha=32) |
| 정확도 | 97.1% (34/35) |
| 저장 위치 | outputs/gemma3-1b-it-lora |

### 이미지 유사도 모델 (예정)
- 팀원이 학습 진행 중
- 디자인 특허 이미지 데이터 수집 중

### 로카르노 분류 모델 (예정)
- 이미지 → 로카르노 클래스 자동 분류

---

## 데이터베이스 (ERD 요약)

### 테이블 13개

| 구분 | 테이블 |
|------|--------|
| 사용자 | `users` |
| 채팅 | `chats`, `messages` |
| 분석 | `analyses`, `analysis_images`, `analysis_keywords`, `image_matches`, `claim_matches` |
| 디자인특허 | `design_patents`, `design_embeddings` |
| 일반특허 | `patents`, `claims`, `claim_embeddings` |

### 주요 관계
- users → chats (1:N)
- chats → messages (1:N)
- messages → analyses (1:1)
- analyses → image_matches / claim_matches (1:N)

---

## 기술 스택

| 구분 | 기술 |
|------|------|
| sLLM | Gemma 1B + LoRA |
| 이미지 임베딩 | CLIP (예정) |
| 텍스트 임베딩 | OpenAI ada-002 또는 KoSimCSE |
| Vector DB | PostgreSQL + pgvector |
| Reranker | bge-reranker (예정) |
| 백엔드 | FastAPI (예정) |
| 프론트엔드 | React/Next.js (예정) |

---

## 작업 가이드라인

### Claude가 도와줄 수 있는 작업
1. **코드 개발**: 백엔드 API, RAG 시스템, 모델 추론
2. **데이터 처리**: 특허 데이터 전처리, 임베딩 생성
3. **모델 개선**: sLLM 추가 학습, 평가
4. **문서화**: ERD, API 문서, 가이드

### 주의사항
- 모든 대답은 **한글**로 할 것
- 로그인 필수 - 비로그인 사용 불가
- 이미지 플로우: 로카르노 분류 → RAG → 유사도 모델 → LLM
- 텍스트 플로우: 키워드 추출 → RAG → Rerank → sLLM

---

## 빠른 명령어

```bash
# sLLM 학습
cd bini && python training/train.py

# 평가
python training/evaluate.py

# 추론 테스트
python training/inference.py

# 의존성 설치
pip install -r bini/training/requirements.txt
```

---

## 다음 작업: 4B 모델 학습

### 목표
- Gemma 4B 모델을 다양한 청구항으로 학습
- 1B 모델보다 일반화된 성능 확보

### 데이터 요구사항

| 목표 | 특허 수 | 특허당 샘플 | 총 샘플 |
|------|---------|-------------|---------|
| **최소** | 5~10개 | 20~30개 | 100~300개 |
| **권장** | 10~20개 | 30~40개 | 300~800개 |

### 각 특허당 샘플 분포 (균형 중요)
- **높음** ~30%: 특허 성분/기술 포함한 제품
- **애매** ~30%: 성분 정보 없음 / 모호한 설명
- **낮음** ~40%: 다른 성분/기술 사용한 제품

### 데이터 형식 (train.jsonl)
```json
{
  "product_description": "tributyl acetylcitrate를 함유하는 앰플을 만들었어",
  "patent_number": "102918091",
  "claim": "아세틸트리부틸스트레이트... 미백용 화장료 조성물",
  "comparisons": [
    {"patent_element": "성분A", "user_product_element": "성분A", "match": "대응"},
    {"patent_element": "제품유형", "user_product_element": "앰플", "match": "대응"}
  ],
  "risk_level": "높음",
  "decision_reason": "사용자의 제품 구성은..."
}
```

### match 값
- `대응`: 특허 요소와 제품 요소가 일치
- `미대응`: 특허 요소와 제품 요소가 불일치
- `판단불가`: 정보 부족으로 판단 불가

### 다양성 확보 (중요)
1. 다양한 산업 분야 (화장품, 의약품, 식품, 전자기기 등)
2. 다양한 청구항 유형 (성분, 방법, 구조 특허)
3. 다양한 표현 (영어/한글, 약어, 동의어)

### 학습 환경
- GPU: RTX 2000 Ada 16GB (4B LoRA 가능)
- 예상 학습 시간: 데이터 양에 따라 다름

---

## 팀 정보
- 프로젝트: SKN20-FINAL-2TEAM
- GitHub: SKNETWORKS-FAMILY-AICAMP/SKN20-FINAL-2TEAM
