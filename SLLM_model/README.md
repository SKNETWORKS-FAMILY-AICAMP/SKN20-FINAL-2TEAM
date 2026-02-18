# SLLM_model - 화장품 특허 FTO 분석 sLLM

화장품 특허 침해(FTO) 분석을 위한 sLLM 파인튜닝 및 평가 작업 전체 기록

---

## 전체 작업 현황

| 단계 | 내용 | 상태 | 날짜 |
|------|------|------|------|
| 1 | 데이터셋 구성 | 완료 | - |
| 2 | Gemma3 1B QLoRA 파인튜닝 | 완료 | 2026-02-16 |
| 3 | Qwen2.5 1.5B QLoRA 파인튜닝 | 완료 | 2026-02-16 |
| 4 | Gemma 추론 (718건) | 완료 | 2026-02-16 |
| 5 | Qwen 추론 (718건) | 완료 | 2026-02-18 |
| 6 | Gemma 평가 | 완료 | 2026-02-18 |
| 7 | Qwen 평가 | 완료 | 2026-02-18 |
| 8 | 두 모델 비교 | 완료 | 2026-02-18 |

---

## 디렉토리 구조 및 파일 설명

```
SLLM_model/
├── data/
│   └── sllm_smalltrain/
│       ├── sllm_train_2869.xlsx   # 학습 데이터 (2,869건)
│       └── sllm_test_718.xlsx     # 테스트 데이터 (718건)
│
├── outputs/
│   ├── gemma3-1b-it-lora/         # Gemma3 1B 파인튜닝 완료 모델 (LoRA adapter)
│   │   ├── adapter_config.json
│   │   ├── adapter_model.safetensors
│   │   └── checkpoint-50/         # 중간 체크포인트
│   └── qwen2.5-1.5b-lora/         # Qwen2.5 1.5B 파인튜닝 완료 모델 (LoRA adapter)
│       ├── adapter_config.json
│       ├── adapter_model.safetensors
│       ├── checkpoint-7150/       # 중간 체크포인트
│       └── checkpoint-7175/       # 최종 체크포인트
│
├── sllm_smalltrain_dj/
│   ├── README.md                  # 데이터셋 및 평가 가이드
│   └── eval/
│       ├── 01_infer.py            # 추론 스크립트 (모델 → 예측 결과 xlsx)
│       ├── 02_evaluate.py         # 개별 평가 스크립트 (라벨정확도/구조/법리일관성)
│       ├── 03_compare.py          # 두 모델 비교 스크립트 → eval_summary.md 생성
│       ├── common.py              # 공통 유틸리티
│       └── output/
│           └── infer_gemma.xlsx   # Gemma 추론 결과 (718건)
│
├── logs/                          # 자동 저장 로그
│   ├── train_2026-02-16_05-06-35.log      # Gemma 학습 로그
│   ├── train_2026-02-16_08-20-13.log      # Qwen 학습 로그
│   ├── eval_infer_2026-02-16_12-16-58.log # Gemma 추론 로그
│   ├── eval_infer_2026-02-18_07-53-41.log # Qwen 추론 로그
│   ├── eval_evaluate_2026-02-18_*.log     # 평가 로그
│   └── eval_compare_2026-02-18_*.log      # 비교 로그
│
├── reports/
│   ├── report_2026-02-16_05-06-35.md  # Gemma 학습 리포트
│   └── report_2026-02-16_08-20-13.md  # Qwen 학습 리포트
│
└── requirements.txt               # 패키지 의존성

# 평가 결과 출력 위치 (프로젝트 루트 /output/)
/root/SKN20-FINAL-2TEAM/output/
├── infer_qwen.xlsx            # Qwen 추론 결과 (718건)
├── eval_detail_gemma.xlsx     # Gemma 행별 평가 결과
├── eval_detail_qwen.xlsx      # Qwen 행별 평가 결과
└── eval_summary.md            # 두 모델 최종 비교 리포트
```

---

## 데이터셋

| 파일 | 건수 | 설명 |
|------|------|------|
| `sllm_train_2869.xlsx` | 2,869건 | 학습 데이터 |
| `sllm_test_718.xlsx` | 718건 | 테스트 데이터 |

| 라벨 | 학습 | 테스트 |
|------|------|--------|
| 침해 | 760 | 190 |
| 비침해 | 760 | 190 |
| 애매 | 589 | 148 |
| 침해_전문가 | 760 | 190 |

---

## 모델 학습 결과

### Gemma3 1B (google/gemma-3-1b-it)

| 항목 | 값 |
|------|-----|
| 설정 | LoRA r=16, alpha=32, lr=3e-05, epochs=5 |
| 학습 데이터 | 2,869건 |
| 학습 시간 | 2026-02-16 05:07 ~ 07:45 (약 2시간 38분) |
| 총 step | 7,175 |
| 시작 loss | 1.3599 |
| 최종 loss | 0.0821 |
| 최소 loss | 0.0367 (step 5530) |
| loss 감소율 | 94.0% |
| HuggingFace | `77eileen/gemma3-1b-patent-fto` (private) |

### Qwen2.5 1.5B (Qwen/Qwen2.5-1.5B-Instruct)

| 항목 | 값 |
|------|-----|
| 설정 | LoRA r=16, alpha=32, lr=3e-05, epochs=5 |
| 학습 데이터 | 2,869건 |
| 학습 시간 | 2026-02-16 08:21 ~ 11:00 (약 2시간 39분) |
| 총 step | 7,175 |
| 시작 loss | 0.6650 |
| 최종 loss | 0.0655 |
| 최소 loss | 0.0241 (step 6560) |
| loss 감소율 | 90.2% |
| HuggingFace | `77eileen/qwen2.5-1.5b-patent-fto` (private) |

---

## 추론 결과

| 모델 | 테스트 건수 | 소요 시간 | 결과 파일 |
|------|------------|----------|----------|
| Gemma3 1B | 718건 | 약 5시간 45분 (2026-02-16) | `sllm_smalltrain_dj/eval/output/infer_gemma.xlsx` |
| Qwen2.5 1.5B | 718건 | 약 6시간 (2026-02-18) | `/output/infer_qwen.xlsx` |

---

## 평가 결과 (2026-02-18)

### 종합 비교

| 평가 항목 | Gemma3 1B | Qwen2.5 1.5B |
|-----------|-----------|--------------|
| **라벨 정확도** | **56.1%** | **71.7%** |
| 구조 성공률 | 96.9% (696/718) | 99.6% (715/718) |
| 법리 일관성 | 82.6% (497/602) | 92.7% (493/532) |
| 행수 일치율 | 93.5% (671/718) | 99.0% (711/718) |
| 매핑 실패 | 14건 | 1건 |

### 라벨별 F1 성능

| 라벨 | Gemma F1 | Qwen F1 |
|------|----------|---------|
| 침해 | 0.648 | 0.762 |
| 비침해 | 0.601 | 0.715 |
| 애매 | 0.517 | 0.753 |
| 침해_전문가 | 0.490 | 0.646 |
| **macro avg** | **0.564** | **0.719** |

> **결론: Qwen2.5 1.5B가 모든 지표에서 Gemma3 1B를 상회. 라벨 정확도 +15.6%p, 매핑실패 14건 → 1건.**

---

## 평가 스크립트 실행 방법

```bash
# 패키지 설치
pip install -r /root/SKN20-FINAL-2TEAM/SLLM_model/requirements.txt

# 1. 추론
python sllm_smalltrain_dj/eval/01_infer.py \
  --model_path outputs/gemma3-1b-it-lora \
  --model_name gemma \
  --test_data data/sllm_smalltrain/sllm_test_718.xlsx

# 2. 평가
python sllm_smalltrain_dj/eval/02_evaluate.py \
  --input sllm_smalltrain_dj/eval/output/infer_gemma.xlsx \
  --model_name gemma

# 3. 비교
python sllm_smalltrain_dj/eval/03_compare.py \
  --model_a output/eval_detail_gemma.xlsx \
  --model_b output/eval_detail_qwen.xlsx
```

---

## HuggingFace 모델 저장소

| 모델 | 저장소 | 접근 |
|------|--------|------|
| Gemma3 1B | `77eileen/gemma3-1b-patent-fto` | private |
| Qwen2.5 1.5B | `77eileen/qwen2.5-1.5b-patent-fto` | private |
