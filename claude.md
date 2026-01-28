# BINI 프로젝트 - Claude 가이드

## 프로젝트 개요
특허 침해 리스크 평가를 위한 sLLM(Small LLM) 미세조정 프로젝트

### 핵심 목표
사용자가 개발 중인 제품이 특정 특허를 침해할 가능성을 자동으로 평가하는 경량 AI 모델 개발

### 모델 로드맵
| 단계 | 모델 | 파라미터 | 상태 |
|------|------|----------|------|
| 1단계 | google/gemma-3-1b-it | 1B | 진행 중 |
| 2단계 | google/gemma-3-4b-it | 4B | 대기 |
| 3단계 | google/gemma-3-8b-it | 8B | 대기 |

## 현재 상태

### 완료된 작업
- [x] 프로젝트 구조 설정
- [x] 출력 스키마 정의 (`output_schema.json`)
- [x] 시드 케이스 35개 생성 (`seed_cases.json`)
- [x] 라벨 데이터 생성 (`train.jsonl`)
- [x] SFT 데이터셋 빌더 (`build_sft_jsonl.py`)
- [x] 학습 스크립트 (`train.py`)
- [x] LoRA 설정 (`lora_config.yaml`)

### 해야 할 작업
- [ ] 데이터셋 품질 검증 및 수정
- [ ] 1B 모델 학습 실행
- [ ] 평가 스크립트 작성
- [ ] 추론 스크립트 작성
- [ ] 데이터셋 확장 (더 많은 특허, 더 다양한 케이스)
- [ ] 4B/8B 모델 업그레이드

## 파일 구조

```
bini/
├── training/
│   ├── train.py              # 메인 학습 스크립트
│   ├── build_sft_jsonl.py    # 데이터셋 빌더
│   ├── lora_config.yaml      # 학습 설정
│   └── requirements.txt      # 의존성
├── data/
│   ├── raw/seeds/
│   │   └── seed_cases.json   # 입력 데이터
│   ├── processed/
│   │   ├── train.jsonl       # 라벨 (정답)
│   │   └── sft_train.jsonl   # 학습용 데이터
│   └── schema/
│       └── output_schema.json
└── prompts/                   # (현재 미사용)
```

## 작업 가이드라인

### Claude가 도와줄 수 있는 작업

1. **데이터 품질 개선**
   - seed_cases.json과 train.jsonl 간의 불일치 수정
   - 더 다양한 케이스 추가
   - 라벨링 오류 검토

2. **코드 수정**
   - train.py 개선 (로깅, 체크포인트 등)
   - 평가/추론 스크립트 작성
   - 데이터 전처리 개선

3. **모델 업그레이드**
   - lora_config.yaml에서 base_model 변경
   - 모델 크기에 맞는 하이퍼파라미터 조정

4. **실험 관리**
   - 실험 결과 기록
   - 성능 비교 분석

### 주의사항

- 모든 대답은 **한글**로 할 것
- 코드 수정 시 기존 구조 유지
- 학습 데이터 수정 시 JSON 형식 검증 필수
- 모델 업그레이드 시 GPU 메모리 고려

## 모델별 권장 설정

### Gemma 1B (현재)
```yaml
base_model: google/gemma-3-1b-it
r: 16
lora_alpha: 32
per_device_train_batch_size: 1
gradient_accumulation_steps: 8
```

### Gemma 4B (예정)
```yaml
base_model: google/gemma-3-4b-it
r: 32
lora_alpha: 64
per_device_train_batch_size: 1
gradient_accumulation_steps: 16
```

### Gemma 8B (예정)
```yaml
base_model: google/gemma-3-8b-it
r: 64
lora_alpha: 128
per_device_train_batch_size: 1
gradient_accumulation_steps: 32
```

## 현재 데이터셋 이슈

### 발견된 문제점
1. **라벨 불일치**: 일부 sft_train.jsonl에서 user_query와 라벨이 매칭되지 않음
   - 예: "트리부틸 아세틸시트레이트를 함유한 세럼"인데 라벨에는 "retinol"로 되어 있음

2. **데이터 다양성 부족**: 현재 1개 특허(102918091)만 사용 중

### 개선 방향
- 라벨 데이터 재검토 및 수정
- 추가 특허 케이스 확보
- 다양한 산업 분야 특허 추가

## 빠른 명령어

```bash
# 데이터셋 생성
cd bini && python training/build_sft_jsonl.py

# 학습 실행
cd bini && python training/train.py

# 의존성 설치
pip install -r bini/training/requirements.txt
```

## 연락처 / 메모
- 프로젝트: SKN20-FINAL-2TEAM
- 다정님 확인 필요 데이터: `data/다정님이_확인하기전데이터/`
