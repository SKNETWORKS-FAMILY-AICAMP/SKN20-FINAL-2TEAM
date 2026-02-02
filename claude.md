> **Claude에게**: 대화 시작 시 이 파일을 먼저 읽고 프로젝트 상황을 파악한 후 진행하세요.
>
> **⚠️ 중요**: sLLM 학습 관련 작업 시, 아래 "금반언(Prosecution History Estoppel) 기능" 섹션을 확인하고 사용자에게 학습 방식(확장/현재)을 먼저 물어보세요.

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
- [x] 4B 모델 학습용 다중 특허 데이터 생성 (85건 / 3개 특허)

### 진행 중인 작업
- [ ] **4B 모델 학습 데이터 확장** — 특허 청구항 추가 입력 대기 중 (아래 "데이터 추가 방법" 참조)
- [ ] 디자인 특허 이미지 데이터 수집 (팀원)
- [ ] 이미지 유사도 모델 학습 (팀원)

### 해야 할 작업
- [ ] **4B 모델 학습** (데이터 충분히 모인 후)
- [ ] sft_train.jsonl 재생성 (`python training/build_sft_jsonl.py`)
- [ ] 로카르노 분류 모델
- [ ] 이미지 RAG 시스템
- [ ] 텍스트 RAG 시스템 (청구항)
- [ ] Reranker 적용
- [ ] 백엔드 API 개발
- [ ] 프론트엔드 개발
- [ ] 로그인/회원가입 시스템

---

## ⚠️ Claude 확인 필요: 금반언(Prosecution History Estoppel) 기능

> **대화 시작 시 사용자에게 반드시 확인할 것!**

### 금반언이란?
- 특허 출원 과정에서 **공개 청구항(claim_pub)**에는 있었으나 **등록 청구항(claim_reg)**에서 삭제된 구성요소는 침해 판단에서 제외됨
- 특허권자가 심사 과정에서 포기한 권리를 나중에 주장할 수 없다는 법리
- **특허 침해 판단의 필수 기능**

### 현재 상태
- 현재 학습 데이터: **단일 청구항(claim)** 구조
- 금반언 판단을 위해서는 **claim_pub/claim_reg 분리** 필요

### 사용자에게 물어볼 질문
```
금반언(Prosecution History Estoppel) 기능 추가 학습을 진행할까요?

1. **확장 방식**: claim_pub(공개 청구항) + claim_reg(등록 청구항) 분리 학습
   - 장점: 금반언 판단 가능, 더 정확한 침해 분석
   - 단점: 기존 데이터 재작성 필요, KIPRIS에서 공개공보 추가 수집 필요

2. **현재 방식 유지**: 단일 청구항(claim)으로 학습
   - 장점: 기존 데이터 활용 가능, 빠른 학습
   - 단점: 금반언 판단 불가
```

### 확장 방식 선택 시 변경 사항
| 파일 | 변경 내용 |
|------|----------|
| seed_cases.json | `claim_text` → `claim_pub`, `claim_reg` 분리 |
| train.jsonl | `claim` → `claim_pub`, `claim_reg` 분리 |
| build_sft_jsonl.py | 새 필드 처리 로직 추가 |
| output_schema.json | 스키마 업데이트 |
| SYSTEM 프롬프트 | 금반언 판단 로직 추가 |

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
# 의존성 설치
pip install -r bini/training/requirements.txt

# sLLM 학습
cd bini && python training/train.py

# 평가
python training/evaluate.py

# 추론 테스트
python training/inference.py
```

---

## 환경 설정 (.env)

Gemma 모델은 Hugging Face gated 모델이므로 토큰 설정이 필요합니다.

### 설정 방법
```bash
# 1. .env.example을 .env로 복사
cp bini/.env.example bini/.env

# 2. .env 파일 열어서 HF_TOKEN 입력
```

### Hugging Face 토큰 발급 순서
1. https://huggingface.co 로그인
2. https://huggingface.co/settings/tokens → 토큰 생성
   - 권한: **"Read access to contents of all public gated repos you can access"**
3. https://huggingface.co/google/gemma-3-4b-it → 모델 접근 권한 승인
4. `.env` 파일에 토큰 입력

> ⚠️ `.env` 파일은 `.gitignore`에 포함되어 있어 Git에 업로드되지 않습니다.

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

## 백엔드 후처리: sLLM 출력 → 테이블 변환

### 결정사항
- sLLM은 **JSON 형식**으로 출력 유지 (파싱 안정성, 검증 용이)
- 백엔드(FastAPI)에서 JSON → 사용자 표시용 테이블 형식으로 **후처리 변환**

### 변환 함수 (백엔드 구현 시 적용)
```python
def format_response(data: dict) -> str:
    regit_num = data["regit_num"]
    comparisons = data["comparisons"]
    decision_reason = data["decision_reason"]

    lines = []
    lines.append(f"특허번호 {regit_num}의 특허 구성과 사용자가 실시하고자 하는 제품의 구성을 비교한 결과는 다음과 같습니다.")
    lines.append("")
    lines.append("[구성 대비]")
    lines.append("| 특허 구성 | 사용자 제품 구성 | 대응 여부 |")
    lines.append("|-----------|------------------|-------|")

    for comp in comparisons:
        pe = comp["patent_element"]
        upe = comp["user_product_element"] if comp["user_product_element"] else "확인 불가"
        match = comp["match"]
        lines.append(f"| {pe} | {upe} | {match} |")

    lines.append("")
    lines.append("[판단]")
    lines.append(decision_reason.replace("해당 특허를", f"해당 특허 {regit_num}를"))

    return "\n".join(lines)
```

### 출력 예시
```
특허번호 1029170800000의 특허 구성과 사용자가 실시하고자 하는 제품의 구성을 비교한 결과는 다음과 같습니다.

[구성 대비]
| 특허 구성 | 사용자 제품 구성 | 대응 여부 |
|-----------|------------------|-------|
| 아크릴레이트/C10-30 알킬 아크릴레이트 크로스폴리머 | 아크릴레이트/C10-30 알킬 아크릴레이트 크로스폴리머 | 대응 |
| 필름포머(...) | 피피지-17/아이피디아이/디엠피에이코폴리머 | 대응 |
| 수중유형 에멀젼 | O/W | 대응 |
| 화장료 조성물 | 선크림 | 대응 |

[판단]
사용자의 제품 구성은 등록된 특허의 구성 성분을 모두 포함하고 있어,
해당 특허 1029170800000를 침해할 가능성은 높은 것으로 판단됩니다.
```

---

## 팀 정보
- 프로젝트: SKN20-FINAL-2TEAM
- GitHub: SKNETWORKS-FAMILY-AICAMP/SKN20-FINAL-2TEAM
