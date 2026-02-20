# sLLM 학습 TODO (RunPod 환경)

## 목표

**파인튜닝된 작은 모델이 파인튜닝 안 된 큰 모델보다 성능이 좋다는 것을 입증**

```
학습된 1.5B > 학습 안 한 3B  ✅ 입증 완료 (86.2% vs 30.1%)
학습된 3B > 학습 안 한 7B    (예정)
...
```

---

## 현재 상태 (2026-02-20 기준)

| 모델 | 파인튜닝 | 데이터 | 정확도 | 구조성공률 | 법리일관성 | 행수일치율 |
|------|----------|--------|--------|-----------|-----------|-----------|
| Qwen 1.5B | O | 17,377건 | **86.2%** | 97.3% | 99.6% | 97.5% |
| Qwen 3B | X | - | 30.1% | 85.2% | 91.3% | 29.3% |
| GPT-4o-mini | X | - | 미완료 | - | - | - |
| Qwen 3B | O | - | 예정 | - | - | - |
| Qwen 7B | X | - | 예정 | - | - | - |

---

## 완료된 작업

### ✅ Phase 1: Qwen 1.5B 재학습
- 데이터: `data/sllm_qwen_data/sllm_train.xlsx` (17,377건)
- 학습 스크립트: `training/train_qwen_v2.py`
- 출력 모델: `outputs/qwen2.5-1.5b-v2/`
- 에폭: 2, 5,000스텝마다 eval
- 정확도: **86.2%** (기존 71.7%에서 대폭 향상)

### ✅ Phase 2: 학습된 1.5B vs 학습 안 한 3B 비교
- 결과: **86.2% vs 30.1%** → 목표 입증 완료
- 비교 리포트: `sllm_smalltrain_dj/eval/output/eval_summary.md`

---

## 다음 작업 순서

### Phase 2-1: GPT-4o-mini 비교 (다음 순서)

```bash
cd SLLM_model/sllm_smalltrain_dj/eval
export OPENAI_API_KEY=sk-...

# 추론 (약 $0.7, 전체 4,317건)
python 01_infer_gpt4o.py --model gpt-4o-mini --model_name gpt4o_mini

# 평가
python 02_evaluate.py --input output/infer_gpt4o_mini.xlsx --model_name gpt4o_mini

# 비교
python 03_compare.py \
  --model_a output/eval_detail_qwen_v2.xlsx \
  --model_b output/eval_detail_gpt4o_mini.xlsx \
  --model_a_name "Qwen1.5B(파인튜닝)" \
  --model_b_name "GPT-4o-mini"
```

### Phase 3: Qwen 3B 파인튜닝

`train_qwen_v2.py` 참고하여 3B 학습 스크립트 신규 작성 (`training/train_qwen3b.py`)

```bash
# 학습
python -m SLLM_model.training.train_qwen3b

# 추론 및 평가
cd SLLM_model/sllm_smalltrain_dj/eval
python 01_infer_vllm.py --model_path ../../outputs/qwen2.5-3b-v1 --model_name qwen3b_ft
python 02_evaluate.py --input output/infer_qwen3b_ft.xlsx --model_name qwen3b_ft
```

### Phase 4: 학습된 3B vs 학습 안 한 7B 비교

```bash
python 01_infer_vllm.py --model_path Qwen/Qwen2.5-7B-Instruct --model_name qwen7b_base
python 02_evaluate.py --input output/infer_qwen7b_base.xlsx --model_name qwen7b_base

python 03_compare.py \
  --model_a output/eval_detail_qwen3b_ft.xlsx \
  --model_b output/eval_detail_qwen7b_base.xlsx \
  --model_a_name "Qwen3B(파인튜닝)" \
  --model_b_name "Qwen7B(베이스)"
```

### Phase 5: 반복 (필요시)

- 7B 학습 → 14B 비교
- ...

---

## 파일 구조

```
SLLM_model/
├── training/
│   ├── train_compare.py        # 구버전 (Gemma vs Qwen 비교용)
│   └── train_qwen_v2.py        # ✅ 현재 사용 스크립트 (17,377건)
├── data/
│   ├── sllm_smalltrain/        # 구 데이터 (2,869/718)
│   └── sllm_qwen_data/         # ✅ 현재 데이터 (17,377/4,317)
├── outputs/
│   ├── qwen2.5-1.5b-lora/      # 구버전 모델 (71.7%)
│   └── qwen2.5-1.5b-v2/        # ✅ 현재 모델 (86.2%)
├── sllm_smalltrain_dj/eval/
│   ├── 01_infer.py             # HuggingFace 추론
│   ├── 01_infer_vllm.py        # ✅ vLLM 추론 (LoRA 자동감지)
│   ├── 01_infer_gpt4o.py       # ✅ GPT-4o/mini API 추론
│   ├── 02_evaluate.py          # 정확도 평가
│   ├── 03_compare.py           # 두 모델 비교 리포트
│   └── output/
│       ├── infer_qwen_v2.xlsx          # ✅ 완료
│       ├── eval_detail_qwen_v2.xlsx    # ✅ 완료
│       ├── infer_qwen3b_base.xlsx      # ✅ 완료
│       ├── eval_detail_qwen3b_base.xlsx # ✅ 완료
│       └── eval_summary.md             # ✅ 1.5B(FT) vs 3B(베이스) 비교
└── requirements.txt
```

---

## 메모

- GPU: A100 권장 (3B, 7B 학습 시)
- 3B 학습 시 batch_size 조정 필요할 수 있음
- 7B 학습 시 gradient_checkpointing 활성화 권장
- GPT-4o-mini 전체 추론 비용: 약 $0.7 (4,317건)
- vllm 설치 필요: `pip install vllm`
- transformers 버전 고정: `4.57.6` (5.x 호환 불가)
