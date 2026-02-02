# OpenCLIP 이미지 유사도 비교 시스템

## 📋 개요

이 프로젝트는 **OpenCLIP** 모델을 활용하여 디자인 이미지 간의 유사도를 측정하고, 디자인 침해 위험을 평가하는 시스템입니다.

KIPRIS(특허정보검색서비스)에서 수집한 2000년도 디자인 데이터를 기반으로 합니다.

---

## 🗂️ 프로젝트 구조

```
09-01/2000년도/
├── openclip_vector_similarity_v2.py   # 메인 유사도 비교 스크립트
├── Split_jsonl.py                      # JSONL 파일 분리 도구
├── openclip_metadata.jsonl             # 원본 메타데이터
├── split_output/                       # Split_jsonl.py 출력 디렉토리
│   ├── documents.jsonl                 # 분리된 document 데이터
│   ├── metadata.csv                    # 메타데이터 (CSV)
│   └── metadata.parquet                # 메타데이터 (Parquet)
├── img/                                # 디자인 이미지 저장 디렉토리
├── similarity_results.csv              # 유사도 비교 결과
└── README.md                           # 이 파일
```

---

## 🚀 설치

### 필수 패키지

```bash
pip install open-clip-torch torch numpy pandas pillow tqdm
```

### 권장 환경

- Python 3.10+
- CUDA GPU (선택사항, MPS/CPU도 지원)

---

## 📖 사용법

### 1. 데이터 준비 (Split_jsonl.py)

JSONL 파일에서 document, metadata를 분리합니다:

```bash
python Split_jsonl.py \
  --in_jsonl openclip_metadata.jsonl \
  --out_dir split_output \
  --save_csv
```

**옵션:**
| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `--in_jsonl` | 입력 JSONL 파일 경로 | (필수) |
| `--out_dir` | 출력 디렉토리 | (필수) |
| `--save_csv` | metadata를 CSV로도 저장 | False |
| `--log_interval` | 진행 로깅 간격 | 10000 |
| `--verbose` | 상세 로깅 | False |

---

### 2. 이미지 유사도 비교 (openclip_vector_similarity_v2.py)

랜덤으로 이미지 쌍을 선택하여 코사인 유사도를 계산합니다:

```bash
# 기본 실행 (100개 쌍)
python openclip_vector_similarity_v2.py

# 사용자 정의 옵션
python openclip_vector_similarity_v2.py \
  --num_pairs 500 \
  --threshold 0.8 \
  --output my_results.csv
```

**옵션:**
| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `--metadata` | Metadata CSV 경로 | `split_output/metadata.csv` |
| `--base_dir` | 이미지 기준 디렉토리 | `.` |
| `--num_pairs` | 생성할 랜덤 쌍 개수 | 100 |
| `--threshold` | 유사도 임계값 | 0.7 |
| `--output` | 결과 CSV 파일명 | `similarity_results.csv` |
| `--model` | OpenCLIP 모델명 | `ViT-L-14` |
| `--pretrained` | Pretrained 가중치 | `laion2b_s32b_b82k` |
| `--device` | 디바이스 (cuda/mps/cpu) | 자동 감지 |
| `--seed` | 랜덤 시드 | 42 |

---

## 🏷️ 레이블 정의

| Label | 설명 | 조건 |
|-------|------|------|
| **1** | 유사 (침해 위험 높음) | cosine_similarity ≥ threshold |
| **0** | 비유사 (침해 위험 낮음) | cosine_similarity < threshold |

---

## 📊 출력 형식

### similarity_results.csv

| 컬럼 | 설명 |
|------|------|
| `pair_id` | 쌍 번호 |
| `image1_id` | 첫 번째 이미지 ID |
| `image1_path` | 첫 번째 이미지 경로 |
| `image2_id` | 두 번째 이미지 ID |
| `image2_path` | 두 번째 이미지 경로 |
| `cosine_similarity` | 코사인 유사도 (0~1) |
| `label` | 침해 위험 레이블 (0 또는 1) |
| `label_desc` | 레이블 설명 |

---

## 🔧 기술 스택

- **OpenCLIP**: 이미지 임베딩 생성 (ViT-L-14)
- **PyTorch**: 딥러닝 프레임워크
- **Pandas**: 데이터 처리
- **Pillow**: 이미지 로딩

---

## 📈 실행 예시

```
============================================================
OpenCLIP Vector Similarity Comparison v2
============================================================
Metadata: split_output/metadata.csv
Number of pairs: 100
Threshold: 0.7
============================================================
Loaded 3324 records from split_output/metadata.csv
Found 3324 valid images
Using device: mps
Loaded OpenCLIP model: ViT-L-14 (laion2b_s32b_b82k)
Computing similarities: 100%|██████████| 100/100 [01:10<00:00]

============================================================
결과 통계
============================================================
총 쌍 개수: 100
유사 (label=1): 28 (28.0%)
비유사 (label=0): 72 (72.0%)
평균 유사도: 0.6234
최소 유사도: 0.4521
최대 유사도: 0.8102
============================================================

✅ 완료!
```

---

## 📝 참고사항

- 이미지 경로는 `metadata.csv`의 `image_local_path` 컬럼을 기준으로 합니다.
- L2 정규화된 벡터 간의 내적으로 코사인 유사도를 계산합니다.
- 동일한 이미지가 쌍으로 선택되지 않도록 처리됩니다.
- 랜덤 시드를 고정하여 재현 가능한 결과를 얻을 수 있습니다.

---

## 📜 라이선스

MIT License
