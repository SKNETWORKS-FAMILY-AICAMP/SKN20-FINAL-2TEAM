# sLLM 학습 TODO (RunPod 환경)

## 목표

**파인튜닝된 작은 모델이 파인튜닝 안 된 큰 모델보다 성능이 좋다는 것을 입증**

```
학습된 1.5B > 학습 안 한 3B
학습된 3B > 학습 안 한 7B
...
```

---

## 현재 상태

- **Qwen2.5 1.5B** 학습 완료 (2,869건, 정확도 71.7%)
- 테스트 데이터: 718건
- 학습 스크립트: `training/train_compare.py`
- 평가 스크립트: `sllm_smalltrain_dj/eval/`

---

## 다음 작업 순서

### Phase 1: Qwen 1.5B 추가 학습 (더 많은 데이터)

1. **새 학습 데이터 준비** (사용자가 제공 예정)
2. **Qwen 1.5B 재학습**
   ```bash
   python -m SLLM_model.training.train_compare --model qwen
   ```
3. **평가**
   ```bash
   cd SLLM_model/sllm_smalltrain_dj/eval
   python 01_infer.py --model_path ../../outputs/qwen2.5-1.5b-lora --model_name qwen_v2 --test_data ../../data/sllm_smalltrain/sllm_test_718.xlsx
   python 02_evaluate.py --input output/infer_qwen_v2.xlsx --model_name qwen_v2
   ```

### Phase 2: 학습된 1.5B vs 학습 안 한 3B 비교

1. **Qwen 3B 베이스 모델로 추론** (학습 없이)
   - 모델: `Qwen/Qwen2.5-3B-Instruct`
   - 동일한 테스트 데이터로 추론
2. **평가 및 비교**
   - 학습된 1.5B vs 학습 안 한 3B
   - 정확도, 구조 성공률, 법리 일관성 비교

### Phase 3: Qwen 3B 학습

1. **Qwen 3B QLoRA 파인튜닝**
   - `train_compare.py`에 3B 모델 추가 필요
2. **평가**

### Phase 4: 학습된 3B vs 학습 안 한 7B 비교

1. **Qwen 7B 베이스 모델로 추론** (학습 없이)
   - 모델: `Qwen/Qwen2.5-7B-Instruct`
2. **평가 및 비교**

### Phase 5: 반복 (필요시)

- 7B 학습 → 14B 비교
- ...

---

## 파일 구조

```
SLLM_model/
├── training/
│   └── train_compare.py      # 학습 스크립트 (3B, 7B 추가 필요)
├── data/
│   └── sllm_smalltrain/      # 현재 데이터 (2,869/718)
│   └── (새 데이터 추가 예정)
├── outputs/
│   └── qwen2.5-1.5b-lora/    # 현재 학습된 모델
│   └── (새 모델들 추가 예정)
├── sllm_smalltrain_dj/eval/  # 평가 스크립트
└── reports/                  # 결과 리포트
```

---

## 수정 필요 사항

### train_compare.py 수정

Qwen 3B, 7B 모델 추가:

```python
MODEL_CONFIGS = {
    "qwen": {
        "model_id": "Qwen/Qwen2.5-1.5B-Instruct",
        "output_dir": "outputs/qwen2.5-1.5b-lora",
    },
    "qwen3b": {
        "model_id": "Qwen/Qwen2.5-3B-Instruct",
        "output_dir": "outputs/qwen2.5-3b-lora",
    },
    "qwen7b": {
        "model_id": "Qwen/Qwen2.5-7B-Instruct",
        "output_dir": "outputs/qwen2.5-7b-lora",
    },
}
```

### 베이스 모델 추론 스크립트

학습 안 한 베이스 모델로 추론하는 스크립트 필요:
- `01_infer.py` 수정 또는 새 스크립트 작성
- LoRA 어댑터 없이 베이스 모델만 로드

---

## 예상 결과 테이블

| 모델 | 파인튜닝 | 데이터 | 정확도 |
|------|----------|--------|--------|
| Qwen 1.5B | O | 2,869건 | 71.7% |
| Qwen 1.5B | O | (새 데이터) | ? |
| Qwen 3B | X | - | ? |
| Qwen 3B | O | (새 데이터) | ? |
| Qwen 7B | X | - | ? |
| ... | | | |

---

## 메모

- GPU: A100 권장 (3B, 7B 학습 시)
- 3B 학습 시 batch_size 조정 필요할 수 있음
- 7B 학습 시 gradient_checkpointing 활성화 권장
