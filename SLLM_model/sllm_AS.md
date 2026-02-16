# sLLM 학습 분석 및 개선사항 (AS)

## 1. 현재 학습 설정

| 항목 | 값 |
|------|-----|
| 학습 데이터 | `sllm_train_2869.xlsx` (2,869건) |
| 테스트 데이터 | `sllm_test_718.xlsx` (718건) |
| 학습 방법 | QLoRA (4-bit NF4) |
| LoRA r / alpha | 16 / 32 |
| **max_seq_length (학습)** | **4096 토큰** |
| **max_tokens (추론)** | **2048 토큰** |
| epochs | 5 |
| batch_size | 2 |
| learning_rate | 3e-5 |
| optimizer | paged_adamw_8bit |
| GPU | A100 40GB (RunPod) |

---

## 2. 데이터 길이 분석 결과

### 컬럼별 글자수

| 컬럼 | 평균 | 최대 |
|------|------|------|
| user_query | 138자 | 804자 |
| claim_reg (등록청구항) | 1,061자 | 19,832자 |
| claim_pub (공개청구항) | 1,183자 | 23,401자 |
| components (구성요소) | 254자 | 1,414자 |
| output_form (정답 출력) | 806자 | 2,720자 |

### 전체 합산 (시스템프롬프트 + 입력 + 출력)

| 구간 | 건수 | 비율 |
|------|------|------|
| 전체 평균 | 3,441자 | - |
| 전체 최대 | 44,679자 | - |
| **4,000자 초과** | **758건** | **26.4%** |
| 8,000자 초과 | 84건 | 2.9% |
| 12,000자 초과 | 20건 | 0.7% |

> 한국어는 약 1글자 = 1~3토큰이므로, 평균 3,441자도 토큰으로 변환하면 5,000~10,000토큰으로 4096을 초과할 수 있음

### 문제점

- 현재 `max_seq_length=4096`으로 학습했기 때문에, 4096 토큰을 넘는 데이터는 **뒷부분이 잘림 (truncation)**
- 특히 등록청구항(claim_reg)과 공개청구항(claim_pub)이 길어서 잘리는 경우 많음
- 2,869건 중 약 **26% (758건)** 이 4,000자 초과 → 잘렸을 가능성 높음

---

## 3. 모델별 최대 컨텍스트

| 모델 | 최대 컨텍스트 | 현재 설정 | 여유 |
|------|-------------|----------|------|
| Gemma3 1B (`google/gemma-3-1b-it`) | **8,192** 토큰 | 4,096 | 2배 여유 |
| Qwen2.5 1.5B (`Qwen/Qwen2.5-1.5B-Instruct`) | **32,768** 토큰 | 4,096 | 8배 여유 |

---

## 4. max_seq_length vs max_tokens 차이

| 설정 | 사용 시점 | 의미 |
|------|----------|------|
| `max_seq_length=4096` | **학습** (train_compare.py) | 입력 + 출력 합쳐서 최대 4096 토큰 |
| `--max_tokens=2048` | **추론** (01_infer.py) | 모델이 생성하는 응답만 최대 2048 토큰 |

- 학습: 시스템프롬프트 + 사용자입력 + 모델응답 전체가 max_seq_length 안에 들어가야 함
- 추론: 입력은 별도, 모델이 새로 만드는 응답만 max_tokens 제한

---

## 5. 재학습 시 개선 방안

### 권장 설정

| 항목 | 현재 | 권장 | 비고 |
|------|------|------|------|
| max_seq_length | 4096 | **8192** | Gemma 한계치, Qwen은 더 올릴 수 있음 |
| max_tokens (추론) | 2048 | **4096** | 학습에서 긴 응답 배우면 추론도 올려야 함 |
| batch_size | 2 | 1~2 | 시퀀스 길어지면 메모리 더 먹으므로 줄일 수 있음 |
| gradient_accumulation | 1 | 4 | batch_size 줄이면 이걸 올려서 보정 |

### GPU 메모리 참고

| max_seq_length | A100 40GB 예상 |
|----------------|---------------|
| 4096 | 여유 있음 |
| 8192 | 가능 (batch_size 조정 필요할 수 있음) |
| 16384 | Qwen만 가능, 메모리 빡빡 |

### 수정 위치

- 학습: `SLLM_model/training/train_compare.py` → `lora_cfg["max_seq_length"]`
- 추론: `SLLM_model/sllm_smalltrain_dj/eval/01_infer.py` → `--max_tokens`

---

## 6. 현재 진행 상태

| 단계 | 상태 | 비고 |
|------|------|------|
| 1차 학습 (Gemma3 1B) | 완료 | max_seq_length=4096, 5 epochs |
| 1차 학습 (Qwen2.5 1.5B) | 완료 | max_seq_length=4096, 5 epochs |
| HuggingFace 업로드 | 완료 | `77eileen/gemma3-1b-patent-fto`, `77eileen/qwen2.5-1.5b-patent-fto` |
| **1차 평가** | **진행 예정** | RunPod에서 eval 스크립트 실행 |
| 2차 학습 (max_seq_length 개선) | 미정 | 1차 평가 결과 보고 결정 |

---

## 7. 평가 실행 방법

RunPod SSH 접속 후:

```bash
# eval 디렉토리로 이동
cd /workspace/SKN20-FINAL-2TEAM/SLLM_model/sllm_smalltrain_dj/eval

# 1) Gemma 추론
python 01_infer.py --model_path /workspace/SKN20-FINAL-2TEAM/SLLM_model/outputs/gemma3-1b-v2 --model_name gemma --test_data /workspace/SKN20-FINAL-2TEAM/SLLM_model/data/sllm_smalltrain/sllm_test_718.xlsx

# 2) Qwen 추론
python 01_infer.py --model_path /workspace/SKN20-FINAL-2TEAM/SLLM_model/outputs/qwen2.5-1.5b-lora --model_name qwen --test_data /workspace/SKN20-FINAL-2TEAM/SLLM_model/data/sllm_smalltrain/sllm_test_718.xlsx

# 3) Gemma 평가
python 02_evaluate.py --input output/infer_gemma.xlsx --model_name gemma

# 4) Qwen 평가
python 02_evaluate.py --input output/infer_qwen.xlsx --model_name qwen

# 5) 두 모델 비교
python 03_compare.py --model_a output/eval_detail_gemma.xlsx --model_b output/eval_detail_qwen.xlsx
```

### 로그 저장 위치

| 스크립트 | 로그 파일 |
|----------|----------|
| 학습 | `SLLM_model/logs/train_*.log` |
| 추론 | `SLLM_model/logs/eval_infer_*.log` |
| 평가 | `SLLM_model/logs/eval_evaluate_*.log` |
| 비교 | `SLLM_model/logs/eval_compare_*.log` |
