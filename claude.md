# BINI 프로젝트 - Claude 가이드

> **Claude에게**: 대화 시작 시 이 파일을 먼저 읽고 프로젝트 상황을 파악한 후 진행하세요.

## 프로젝트 목적

**상품 출시 전 특허 침해 여부 사전 검증 서비스**
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
├── backend/                 # FastAPI 백엔드
│   └── app/                 # API 서버 (인증, 채팅, 분석)
│
├── FRONTEND/                # 정적 HTML/JS 프론트엔드
│
└── past/                    # 이전 프로젝트들 (fashion, vegan)
```

---

## sLLM 모델 현황

| 항목 | 내용 |
|------|------|
| 베이스 모델 | google/gemma-3-1b-it |
| 학습 방법 | LoRA (r=16, alpha=32) |
| **정확도** | **97.1%** (34/35) |
| JSON 유효성 | 100% |
| 학습 데이터 | 147개 샘플 (3개 특허) |

현재 설정 (`lora_config.yaml`)에서는 **4B 모델**로 업그레이드 준비 중:
- `base_model: google/gemma-3-4b-it`
- `output_dir: outputs/gemma3-4b-it-lora`

---

## 백엔드 API (FastAPI)

```python
# 엔드포인트
/api/auth    # 인증 (로그인/회원가입)
/api/chat    # 채팅 기록
/api/analysis # 특허 분석
```

SQLite DB (`bini_test.db`) 사용 중

---

## 프론트엔드

정적 HTML/CSS/JS로 구성:
- `index.html` - 메인 페이지
- `analysis.html` - 분석 페이지
- `login.html`, `signup.html` - 인증
- `chat.html` - 채팅

---

## 학습 데이터 형식

**입력 (seed_cases.json)**:
```json
{
  "regit_num": "1029180910000",
  "claim_text": "아세틸트리부틸스트레이트...화장료 조성물",
  "user_query": "tributyl acetylcitrate를 함유하는 앰플을 만들었어"
}
```

**출력 (train.jsonl)**:
```json
{
  "regit_num": "1029180910000",
  "comparisons": [
    {"patent_element": "...", "user_product_element": "...", "match": "대응"}
  ],
  "risk_level": "높음",
  "decision_reason": "..."
}
```

---

## 현재 상태

| 완료 | 진행 중 | 해야 할 일 |
|------|---------|-----------|
| sLLM 1B 학습 | 4B 데이터 확장 | 4B 모델 학습 |
| ERD 설계 | 디자인 특허 이미지 수집 | RAG 시스템 |
| 백엔드 기본 구조 | | Reranker 적용 |
| 프론트엔드 기본 구조 | | 로카르노 분류 모델 |

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

Gemma 모델은 Hugging Face gated 모델이므로 토큰 설정 필요:

```bash
cp bini/.env.example bini/.env
# .env 파일에 HF_TOKEN 입력
```

---

## 팀 정보

- 프로젝트: SKN20-FINAL-2TEAM
- GitHub: SKNETWORKS-FAMILY-AICAMP/SKN20-FINAL-2TEAM
