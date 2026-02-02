# 디자인 특허 유사도 분석 시스템 (2000년도 데이터)

## 📋 개요

2000년도 디자인 특허 데이터를 벡터화하고, 이미지 및 텍스트 유사도를 계산하여 CSV 형태로 저장하는 시스템입니다.

## 🗂️ 프로젝트 구조

```
2000년도/
├── README.md                           # 이 파일
├── 2000_xml/                          # 원본 XML 파일들 (463개)
├── 2000_json/                         # 변환된 JSON 파일들 (4,371개)
├── 2000_xml_to_json.py               # XML → JSON 변환 스크립트
├── vector_similarity.py              # 벡터화 및 유사도 계산 스크립트
├── 09-01_2000_vectors.pkl            # 벡터 DB (생성됨)
├── 09-01_2000_similarity_results.csv # 유사도 분석 결과 (생성됨)
├── failed_images.txt                 # 이미지 다운로드 실패 목록 (생성됨)
└── failed_jsons.txt                  # JSON 처리 실패 목록 (생성됨)
```

## 🚀 사용 방법

### 1단계: XML → JSON 변환

XML 파일에서 이미지 1장당 JSON 파일 1개를 생성합니다.

```bash
cd /Users/kangminji/__SKN20_FINAL/Image_similar/img_similarity/09-01/2000년도
python3 2000_xml_to_json.py
```

**결과:**
- 입력: `2000_xml/` 폴더의 463개 XML 파일
- 출력: `2000_json/` 폴더에 4,371개 JSON 파일 생성
- 파일명 형식: `{출원번호}-{도면번호}.json` (예: `3020000000039-01.json`)

### 2단계: 벡터화 및 유사도 분석

```bash
python3 vector_similarity.py
```

**처리 과정:**
1. JSON 파일들을 로드하여 이미지 및 텍스트 벡터 생성
2. 랜덤하게 2,000개 쌍을 선택하여 유사도 계산
3. 결과를 CSV 파일로 저장

**결과:**
- 벡터 DB: `09-01_2000_vectors.pkl` (약 3,324개 디자인 벡터화)
- 결과 CSV: `09-01_2000_similarity_results.csv`
- 실패 로그: `failed_images.txt`, `failed_jsons.txt`

## 📊 출력 CSV 형식

`09-01_2000_similarity_results.csv` 파일의 컬럼 구조:

| 컬럼명 | 설명 |
|--------|------|
| `pair_id` | 비교 쌍 ID (1부터 시작) |
| `design1_id` | 첫 번째 디자인 ID |
| `design2_id` | 두 번째 디자인 ID |
| `design1_name` | 첫 번째 디자인 물품명 |
| `design2_name` | 두 번째 디자인 물품명 |
| `design1_image_url` | 첫 번째 디자인 이미지 URL |
| `design2_image_url` | 두 번째 디자인 이미지 URL |
| `image_similarity` | 이미지 유사도 (0~1, null 가능) |
| `text_similarity` | 텍스트 유사도 (0~1) |
| `total_similarity` | 종합 유사도 (이미지 70% + 텍스트 30%) |
| `label` | 유사 여부 (1: 유사, 0: 비유사) |

## 🎯 Label 결정 기준

**이미지 유사도 기반:**
- `image_similarity ≥ 0.5` → `label = 1` (유사)
- `image_similarity < 0.5` → `label = 0` (비유사)
- 이미지가 없는 경우 → 텍스트 유사도 기준 적용

## ⚙️ 설정 값

`vector_similarity.py` 파일 내 설정:

```python
JSON_FOLDER = "./2000_json"                    # JSON 파일 폴더
VECTOR_DB_PATH = "09-01_2000_vectors.pkl"      # 벡터 DB 저장 경로
OUTPUT_CSV = "09-01_2000_similarity_results.csv"  # 결과 CSV

N_PAIRS = 2000                  # 비교할 쌍 개수
IMAGE_WEIGHT = 0.7              # 이미지 가중치
TEXT_WEIGHT = 0.3               # 텍스트 가중치
SIMILARITY_THRESHOLD = 0.5      # 유사 판정 임계값
INCLUDE_VECTORS = False         # CSV에 벡터 포함 여부
```

## 🔧 사용된 모델

### 이미지 벡터화
- **모델:** `openai/clip-vit-base-patch32`
- **설명:** OpenAI의 CLIP 모델로 이미지를 512차원 벡터로 변환
- **이유:** 이미지와 텍스트를 동일한 임베딩 공간에 매핑하며, 이미지-텍스트 간 유사도 직접 비교 가능
- **디바이스:** MPS (Mac GPU) / CUDA / CPU 자동 선택

### 텍스트 벡터화
- **모델:** `jhgan/ko-sroberta-multitask`
- **설명:** 한국어 특화 Sentence-BERT 모델
- **이유:** 범용적인 문장과 NLP 태스크로 동시 학습이 가능하며 빠른 유사도 계산이 가능
- **디바이스:** CPU (MPS 호환성 문제로)

### 유사도 계산
- **방법:** Cosine Similarity
- **종합 유사도:** `total_similarity = 0.7 × image_sim + 0.3 × text_sim`

## 📈 통계 정보

### 벡터화 결과
- 총 JSON 파일: 4,371개
- 성공적으로 벡터화: 3,324개 (약 76%)
- JSON 처리 실패: 약 1,047개 (약 24%)
- 이미지 다운로드 실패: 
    - URL 접근 불가 (404, 403 등)
    - 네트워크 타임아웃 (15초 초과)
    - 서버 응답 오류
    - 이미지 포맷 문제

## 🐛 문제 해결

### 이미지 다운로드 실패
- `failed_images.txt` 파일에서 실패한 디자인 ID 확인
- 해당 이미지들은 0 벡터로 처리됨
- 텍스트 유사도만 사용하여 계산

### JSON 처리 실패
- `failed_jsons.txt` 파일에서 실패 원인 확인
- 일반적 원인: JSON 파싱 오류, 필수 필드 누락

### 메모리 부족
- `N_PAIRS` 값을 줄여서 실행
- `INCLUDE_VECTORS = False`로 설정하여 CSV 크기 감소


### 유사도 분석 결과 (예시)
```
📈 요약 통계
  총 비교: 2,000쌍
  유사 (label=1): XXX개 (XX.X%)
  비유사 (label=0): XXX개
  평균 이미지 유사도: 0.XXXX
  평균 텍스트 유사도: 0.XXXX
  평균 종합 유사도: 0.XXXX
```


## 📝 JSON 파일 구조

각 JSON 파일은 다음과 같은 구조를 가집니다:

```json
{
  "design_id": "3020000000039-09-01",
  "applicationNumber": "3020000000039",
  "registrationNumber": "3002602570000",
  "status": {
    "regFg": "Y",
    "admstStat": "소멸",
    "lastDispositionDate": "2000-02-25"
  },
  "meta": {
    "articleName": "포장용 병",
    "LCCode": "09-01",
    "designNumber": "M01",
    "applicantName": "문영만"
  },
  "creative": {
    "designSummary": "포장용 병의 형상과 모양의 결합...",
    "designDescription": "1. 재질은 점토임..."
  },
  "image": {
    "image_id": "3020000000039-01",
    "imageName": "000.JPG",
    "imagePath": "http://plus.kipris.or.kr/...",
    "number": "1"
  }
}
```

## 💡 활용 방안

1. **학습 데이터 생성:** 디자인 유사도 판별 모델 학습용 데이터셋
2. **유사도 분석:** 기존 디자인과의 유사도 검증
3. **침해 가능성 검토:** 새로운 디자인의 침해 가능성 1차 스크리닝
4. **검색 시스템:** 유사 디자인 검색 시스템 구축

## 🔗 의존성

```bash
pip install torch transformers sentence-transformers scikit-learn
pip install requests Pillow tqdm numpy
```

## 📄 라이선스

이 프로젝트는 디자인 특허 데이터 분석을 위한 연구 목적으로 작성되었습니다.

## 👤 작성자

SKN20_강민지

---

**마지막 업데이트:** 2026년 1월 29일
