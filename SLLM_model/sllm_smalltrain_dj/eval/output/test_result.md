# sLLM 평가 output 구조

> 실험 단계별로 폴더 분류. 각 폴더에 infer(추론), eval_detail(평가), eval_summary(비교) 파일 포함.

---

## 폴더 구조

```
output/
├── s1_gemma_qwen_718/              # Stage 1: 소규모 학습 모델 비교 (718건 테스트)
├── s2_1.5b_ft_vs_3b_b/             # Stage 2: 1.5B FT vs 3B Base (4,317건 테스트)
├── s3_3b_ft_vs_7b_b/               # Stage 3: 3B FT vs 7B Base (4,317건 테스트)
├── s4_7b_ft_4096_vs_over4096/      # Stage 4: 7B FT 장문 성능 비교
├── s5_7b_ft_vs_14b_b/              # Stage 5: 7B FT vs 14B Base
├── s6_ft_all/                      # Stage 6: FT 모델 전체 비교 (1.5B/3B/7B/14B)
└── test_result.md
```

---

## Stage 1: `s1_gemma_qwen_718/`

**목적**: 2,869건 학습 모델 초기 비교 (Gemma 1B vs Qwen 1.5B)
**테스트 데이터**: `sllm_test_718.xlsx` (718건)

| 파일 | 설명 |
|------|------|
| `infer_gemma_base.xlsx` | Gemma 1B Base 추론 결과 |
| `infer_gemma1b_ft.xlsx` | Gemma 1B FT 추론 결과 |
| `infer_qwen_base.xlsx` | Qwen 1.5B Base 추론 결과 |
| `infer_qwen1.5b_ft.xlsx` | Qwen 1.5B FT 추론 결과 |
| `eval_detail_gemma_base.xlsx` | Gemma 1B Base 평가 상세 |
| `eval_detail_gemma1b_ft.xlsx` | Gemma 1B FT 평가 상세 |
| `eval_detail_qwen_base.xlsx` | Qwen 1.5B Base 평가 상세 |
| `eval_detail_qwen1.5b_ft.xlsx` | Qwen 1.5B FT 평가 상세 |
| `eval_summary_base모델비교_gem_qwen.md` | Gemma 1B Base vs Qwen 1.5B Base 비교 |
| `eval_summary_4천개비교_gem_qwen.md` | Gemma 1B FT vs Qwen 1.5B FT 비교 |

**학습 정보**:
- 학습 데이터: 2,869건 (`sllm_train_2869.xlsx`)
- 모델: `google/gemma-3-1b-it`, `Qwen/Qwen2.5-1.5B-Instruct`
- LoRA 어댑터: `inference_outputs/gemma3-1b-it-lora/`, `inference_outputs/qwen2.5-1.5b-lora/`
- HuggingFace: `77eileen/qwen2.5-1.5b-patent-fto`

---

## Stage 2: `s2_1.5b_ft_vs_3b_b/`

**목적**: 파인튜닝 1.5B가 베이스 3B를 이길 수 있는가?
**테스트 데이터**: `sllm_test.xlsx` (4,317건)

| 파일 | 설명 |
|------|------|
| `infer_qwen1.5b_ft.xlsx` | Qwen 1.5B FT(17,377건 학습) 추론 결과 |
| `infer_qwen3b_base.xlsx` | Qwen 3B Base 추론 결과 |
| `eval_detail_qwen1.5b_ft.xlsx` | Qwen 1.5B FT 평가 상세 |
| `eval_detail_qwen3b_base.xlsx` | Qwen 3B Base 평가 상세 |
| `eval_summary_1.5b_ft_3b.md` | 1.5B FT vs 3B Base 비교 결과 |

**학습 정보**:
- 학습 데이터: 17,377건
- FT 모델: `Qwen/Qwen2.5-1.5B-Instruct` + LoRA
- Base 모델: `Qwen/Qwen2.5-3B-Instruct`
- HuggingFace FT: `77eileen/qwen2.5-1.5b-patent-fto` (v2)
- HuggingFace 3B FT: `itsbini/qwen2.5-3b-fto`

---

## Stage 3: `s3_3b_ft_vs_7b_b/`

**목적**: 파인튜닝 3B가 베이스 7B를 이길 수 있는가?
**테스트 데이터**: `sllm_test.xlsx` (4,317건)

| 파일 | 설명 |
|------|------|
| `infer_qwen3b_ft.xlsx` | Qwen 3B FT 추론 결과 |
| `infer_qwen7b_base.xlsx` | Qwen 7B Base 추론 결과 |
| `eval_detail_qwen3b_ft.xlsx` | Qwen 3B FT 평가 상세 |
| `eval_detail_qwen7b_base.xlsx` | Qwen 7B Base 평가 상세 |
| `eval_summary_3b_7b.md` | 3B FT vs 7B Base 비교 결과 |

**학습 정보**:
- FT 모델: `itsbini/qwen2.5-3b-fto`
- Base 모델: `Qwen/Qwen2.5-7B-Instruct`

---

## Stage 4: `s4_7b_ft_4096_vs_over4096/`

**목적**: 4096 토큰 이하로 학습한 7B FT 모델이 4096 초과 입력에서도 성능을 유지하는가?
**테스트 데이터**: `sllm_test.xlsx` (4,317건, 4096이하) + `sllm_test_over4096.xlsx` (4,379건, 4096초과, 최대 32,621 토큰)

| 파일 | 설명 |
|------|------|
| `infer_qwen7b_ft.xlsx` | 7B FT, 4096 이하 테스트 추론 |
| `infer_qwen7b_ft_over4096.xlsx` | 7B FT, 4096 초과 테스트 추론 |
| `eval_detail_qwen7b_ft.xlsx` | 7B FT 4096이하 평가 상세 |
| `eval_detail_qwen7b_ft_over4096.xlsx` | 7B FT 4096초과 평가 상세 |
| `eval_summary_qwen7b_4096_over_compare.md` | 4096이하 vs 4096초과 비교 결과 |

**학습 정보**:
- FT 모델: `77eileen/qwen2.5-7b-patent-fto` (17,377건 학습)
- 추론시 `--max_model_len 32768` 사용 (over4096)

---

## Stage 5: `s5_7b_ft_vs_14b_b/`

**목적**: 파인튜닝 7B가 베이스 14B를 이길 수 있는가?
**테스트 데이터**: `sllm_test.xlsx` (4,317건)

| 파일 | 설명 |
|------|------|
| `infer_qwen7b_ft.xlsx` | Qwen 7B FT 추론 결과 |
| `infer_qwen14b_base.xlsx` | Qwen 14B Base 추론 결과 |
| `eval_detail_qwen7b_ft.xlsx` | Qwen 7B FT 평가 상세 |
| `eval_detail_qwen14b_base.xlsx` | Qwen 14B Base 평가 상세 |
| `eval_summary_7b_ft_vs_14b_base.md` | 7B FT vs 14B Base 비교 결과 |

**학습 정보**:
- FT 모델: `77eileen/qwen2.5-7b-patent-fto` (17,377건 학습)
- Base 모델: `Qwen/Qwen2.5-14B-Instruct`
- RunPod A100 PCIe 사용

---

## Stage 6: `s6_ft_all/`

**목적**: 파인튜닝 모델 크기별 성능 비교 (1.5B / 3B / 7B / 14B)
**테스트 데이터**: `sllm_test.xlsx` (4,317건)

| 파일 | 설명 |
|------|------|
| `infer_qwen14b_ft.xlsx` | Qwen 14B FT 추론 결과 |
| `eval_detail_qwen14b_ft.xlsx` | Qwen 14B FT 평가 상세 |
| `eval_summary_7b_ft_vs_14b_ft.md` | 7B FT vs 14B FT 비교 |
| `eval_summary_ft_all.md` | 1.5B/3B/7B/14B FT 전체 비교 |

**학습 정보**:
- 1.5B FT: `77eileen/qwen2.5-1.5b-patent-fto`
- 3B FT: `itsbini/qwen2.5-3b-fto`
- 7B FT: `77eileen/qwen2.5-7b-patent-fto`
- 14B FT: `itsbini/qwen2.5-14b-fto`

---

## 실험 전체 흐름

```
학습 규모 증가 →  2,869건(s1)  →  17,377건(s2~s6)
모델 크기 비교 →  1B vs 1.5B(s1) → 1.5B vs 3B(s2) → 3B vs 7B(s3) → 7B vs 14B(s5)
장문 성능 검증 →  s4 (4096이하 vs 4096초과)
FT 모델 종합  →  s6 (1.5B/3B/7B/14B FT 전체 비교)
```

**핵심 질문**: "작은 모델을 파인튜닝하면 한 단계 위 베이스 모델을 이길 수 있는가?"

---

## 평가 스크립트

```bash
# 추론 (vLLM, GPU 필요)
python 01_infer_vllm_v2.py --model_path <모델경로|HF_repo> --model_name <이름> --test_data <테스트파일>

# 추론 (Gemini API, GPU 불필요)
python 01_infer_gemini.py --model gemini-2.5-pro-preview-05-06 --model_name gemini25pro

# 개별 평가
python 02_evaluate.py --input output/<infer파일> --model_name <이름>

# 두 모델 비교 (주의: eval_summary.md 덮어쓰기됨 → 수동 rename 필요)
python 03_compare.py --model_a output/<eval_detail_A> --model_b output/<eval_detail_B>

# 다중 모델 비교
python 04_compare_multi.py --models <파일1> <파일2> <파일3> --names <이름1> <이름2> <이름3> --output <출력경로>
```

---

*최종 업데이트: 2026-02-24*
