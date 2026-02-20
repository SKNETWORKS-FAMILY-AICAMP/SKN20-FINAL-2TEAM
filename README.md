# FTO_ImgProject — 디자인 유사 이미지 검색 시스템

> **FTO(Freedom To Operate) 분석을 위한 특허 디자인 유사도 검색 시스템**
> CLIP 임베딩 + ChromaDB + Hybrid Retrieval (Dense + BM25) + RAG(GPT-4o)

---

## 목차

1. [프로젝트 구조](#1-프로젝트-구조)
2. [파일별 역할](#2-파일별-역할)
3. [전체 데이터 파이프라인 (v1 vs v2)](#3-전체-데이터-파이프라인-v1-vs-v2)
4. [데이터 수집](#4-데이터-수집)
5. [데이터 전처리](#5-데이터-전처리)
6. [데이터 임베딩](#6-데이터-임베딩)
7. [ChromaDB 저장 컬럼](#7-chromadb-저장-컬럼)
8. [RAG 구조](#8-rag-구조)
9. [DB 전체 유사도 분석](#9-db-전체-유사도-분석)
10. [CLIP 파인튜닝 전략](#10-clip-파인튜닝-전략)
11. [Triplet 데이터 자동 구성](#11-triplet-데이터-자동-구성)
12. [학습 설계](#12-학습-설계)
13. [학습 모니터링 지표](#13-학습-모니터링-지표)
14. [실행 방법](#14-실행-방법)
15. [환경변수](#15-환경변수)
16. [핵심 결론](#16-핵심-결론)

---

## 1. 프로젝트 구조

```
FTO_ImgProject/
├── .env                          # API 키 (OpenAI, KIPRIS+)
├── .gitignore
│
├── design/                       # 검색 앱 메인 모듈
│   ├── app.py                    # Streamlit 검색 웹앱
│   ├── inference.py              # 파인튜닝 모델로 DB 재임베딩
│   ├── rag.py                    # 기본 RAG 체인 (ChromaDB + GPT-4o)
│   ├── rag_advanced.py           # 고급 멀티스테이지 RAG
│   ├── prompts.py                # LLM 프롬프트 템플릿 모음
│   ├── utils.py                  # 공통 유틸 함수
│   ├── requirements_app.txt      # 앱 실행 의존성
│   └── processedSketch/          # 엣지 검출 알고리즘 실험
│       ├── Photo_sketch_canny1.py
│       ├── Photo_sketch_canny세밀튜닝2.py
│       ├── Structured Edge Detection4.py
│       ├── Sobel_hysteresis3.py
│       └── HED_edge_detection.py
│
├── train/                        # CLIP 파인튜닝 모듈
│   ├── train.py                  # InfoNCE Contrastive Loss 파인튜닝
│   ├── inference.py              # 파인튜닝 모델로 전체 재임베딩
│   ├── requirements.txt          # 학습 의존성
│   └── checkpoints/              # 저장된 모델 체크포인트
│       ├── best_model.pt         # 최적 모델 (R@1 기준)
│       └── train_history.csv     # epoch별 loss/recall 기록
│
├── processed/                    # 데이터 파이프라인 스크립트
│   ├── embeddings_v2.py          # CLIP 임베딩 생성 (스케치 변환 포함)
│   ├── vectordb.py               # ChromaDB 구축
│   ├── xml_to_json.py            # KIPRIS XML → JSON 변환
│   ├── png_to_jpg.py             # 이미지 포맷 변환
│   ├── api_design.py             # KIPRIS API 호출
│   ├── compaire.py               # 임베딩 비교 유틸
│   └── redownload_failed_images.py  # 실패 이미지 재다운로드
│
└── data/                         # 데이터 저장소
    ├── sketch/
    │   ├── images_v2/            # 21,829개 특허 도면 (스케치 변환)
    │   ├── embeddings_v2/        # 21,829개 CLIP 임베딩 JSON
    │   └── chroma_db_v2/         # 메인 ChromaDB (21,829벡터)
    ├── evaldata/
    │   ├── images_reject/        # 57개 거절 특허 (원본)
    │   ├── images_reject_v2/     # 57개 거절 특허 (스케치 변환)
    │   ├── embeddings_reject_v2/ # 57개 CLIP 임베딩 JSON
    │   ├── chroma_db_train_v2/   # 평가용 ChromaDB (57벡터)
    │   ├── dataset_combined_final.xlsx   # 파인튜닝 페어 데이터 (cross-folder)
    │   ├── dataset_images_reject.xlsx    # 파인튜닝 페어 데이터 (reject)
    │   └── dataset_images_reject_v2.xlsx # 파인튜닝 페어 데이터 (reject_v2)
    ├── json/                     # 특허 메타데이터 JSON
    ├── api_xml/                  # KIPRIS API 원본 XML
    ├── rawdata/                  # 원시 특허 데이터
    ├── photo/                    # 원본 사진 데이터 (legacy)
    └── error_Flow/               # 에러 로그 파일
```

---

## 2. 파일별 역할

| 파일 | 역할 |
|---|---|
| `design/app.py` | Streamlit 웹앱. 이미지 업로드 → 스케치 전처리 → Hybrid Retrieval → Top-10 결과 표시 |
| `design/inference.py` | 파인튜닝된 CLIP 모델로 전체 DB 재임베딩 + ChromaDB 재구축 |
| `design/rag.py` | 기본 RAG: ChromaDB 벡터 검색 → GPT-4o 보고서 생성 |
| `design/rag_advanced.py` | 고급 RAG: 이미지 분석 → 유사도 비교 → 검증 → FTO 보고서 생성 (멀티스테이지) |
| `design/prompts.py` | GPT-4o 프롬프트 7종 (이미지 분석, 비교, 검증, 보고서 등) |
| `processed/embeddings_v2.py` | KIPRIS JSON → 이미지 다운로드 → 사진/스케치 자동 감지 → Canny 변환 → CLIP 임베딩 저장 |
| `processed/vectordb.py` | 임베딩 JSON → F.normalize → ChromaDB 적재 (로컬경로 매핑 포함) |
| `processed/xml_to_json.py` | KIPRIS API XML 응답을 구조화된 JSON으로 변환 |
| `train/train.py` | CLIP ViT-B/32 파인튜닝 (InfoNCE Loss, Partial Freeze, Cosine Annealing) |
| `train/inference.py` | 파인튜닝 체크포인트 로드 → 전체 이미지 재임베딩 → ChromaDB 재구축 |

---

## 3. 전체 데이터 파이프라인 (v1 vs v2)

### 파이프라인 개요

```
[data/rawdata/]                출원번호 목록 (Excel: 거절출원번호_유사이미지있음.xlsx)
      ↓
processed/api_design.py        KIPRIS+ API 호출 (getBibliographyDetailInfoSearch)
      ↓
data/api_xml/                  특허 서지정보 .xml 파일 저장 (출원번호당 1개)
      ↓
processed/xml_to_json.py       XML → 구조화 JSON 변환 (도면번호 0, 1, 2만 추출)
      ↓
data/json/                     특허 도면당 .json 파일 저장 (메타데이터 + 이미지 URL)
      ↓
      ├─ processed/embeddings_v1.py ─────────────────────────────────────┐
      │     사진 그대로 + 스케치 그대로 다운로드                              │
      │     data/sketch/images_v1/       ← 사진 + 스케치 혼재 이미지        │
      │     data/sketch/embeddings_v1/   ← CLIP 임베딩 JSON (F.normalize ✗) │
      │                                                                    │
      └─ processed/embeddings_v2.py ─────────────────────────────────────┐
            사진 → 스케치 변환 + 스케치 그대로 다운로드                        │
            data/sketch/images_v2/       ← 스케치 전용 이미지               │
            data/sketch/embeddings_v2/   ← CLIP 임베딩 JSON (F.normalize ✓) │
      ↓
processed/vectordb.py
      ├─ embeddings_v1/ → data/sketch/chroma_db_v1/   (사진 + 스케치 도면 혼재)
      └─ embeddings_v2/ → data/sketch/chroma_db_v2/   (스케치 도면만 — 검색 품질 ↑)
```

### v1 vs v2 핵심 차이

| 구분 | v1 | v2 |
|---|---|---|
| 이미지 처리 방식 | 사진 그대로 + 스케치 그대로 | 사진 → Canny 스케치 변환, 스케치 그대로 |
| 이미지 저장 폴더 | `data/sketch/images_v1/` | `data/sketch/images_v2/` |
| 임베딩 저장 폴더 | `data/sketch/embeddings_v1/` | `data/sketch/embeddings_v2/` |
| ChromaDB | `data/sketch/chroma_db_v1/` | `data/sketch/chroma_db_v2/` |
| 임베딩 도메인 | 사진 + 스케치 혼재 ⚠️ | 스케치 도면만 ✅ |
| F.normalize 적용 | ✗ (raw 벡터, norm ≈ 11) | ✓ (unit vector, norm = 1.0) |
| `is_converted_to_sketch` 필드 | 없음 | 있음 |
| 검색 쿼리 전처리 일치 | ✗ 불일치 | ✅ 일치 |

> **왜 v2가 최종 사용 버전인가?**
> CLIP은 사진(photo)과 선화(sketch)를 완전히 다른 도메인으로 인식합니다.
> DB에 사진과 스케치가 혼재하면, 쿼리 이미지와의 유사도 비교가 부정확해집니다.
> **v2에서는 DB 전체를 스케치로 통일**하고, `app.py`에서 쿼리 이미지도 동일한
> Canny Edge Detection으로 스케치 변환하여 **도메인 일관성**을 확보합니다.

### Step별 상세 설명

#### Step 1: rawdata → KIPRIS+ API → api_xml (`api_design.py`)

```
입력:  data/rawdata/ 또는 엑셀 파일 → 출원번호 목록
API:   KIPRIS+ getBibliographyDetailInfoSearch
출력:  data/api_xml/{출원번호}.xml
```

- 엑셀에서 출원번호 목록 로드 (`pandas.read_excel`)
- 출원번호당 KIPRIS+ API 1회 호출 → XML 응답 저장
- 에러 처리: 타임아웃 / 연결오류 / HTTP 오류 → 에러 로그 + 실패 목록 별도 저장
- Rate limit: 요청 간 **0.9초 슬립** (API 과부하 방지)

```python
base_url = "http://plus.kipris.or.kr/kipo-api/kipi/designInfoSearchService/getBibliographyDetailInfoSearch"
params = {"applicationNumber": app_num, "ServiceKey": API_KEY}
```

#### Step 2: api_xml → JSON (`xml_to_json.py`)

```
입력:  data/api_xml/{출원번호}.xml
출력:  data/json/{출원번호}-{도면번호}.json  (도면번호 0·1·2 → 최대 3개 JSON)
```

- ElementTree로 XML 파싱 → 네임스페이스 자동 제거
- **도면 번호 0, 1, 2만 추출** (정면도·측면도·사시도)
- 한 출원에 도면이 여러 장이면 각 도면마다 별도 JSON 생성

```python
# 추출 필드 구조
{
  "design_id":          "{applicationNumber}-{LCCode}-{imageNumber}",
  "applicationNumber":  "3020140047287",
  "registrationNumber": "...",
  "publicationNumber":  "...",
  "status": {
    "regFg":               "Y",        # 등록 여부
    "admstStat":           "등록",     # 행정 처리 상태
    "lastDispositionDate": "2015-03-20"
  },
  "meta": {
    "articleName":   "화장품용기",      # 물품명
    "LCCode":        "02-01",          # 로카르노 분류 코드
    "designNumber":  "...",
    "applicantName": "...",            # 출원인명
    "agentName":     "..."             # 대리인명
  },
  "image": {
    "imageName": "3020140047287_0.jpg",
    "imagePath": "http://plus.kipris.or.kr/...",  # 이미지 다운로드 URL
    "number":    "0"
  },
  "creative": {
    "designSummary":     "...",        # 창작의 요점
    "designDescription": "..."         # 디자인 설명
  }
}
```

#### Step 3-A: JSON → 임베딩 v1 (`embeddings_v1.py`) — 사진 + 스케치 그대로

```
입력:  data/json/
출력:  data/sketch/images_v1/      ← 원본 이미지 (사진·스케치 혼재)
       data/sketch/embeddings_v1/  ← CLIP 임베딩 JSON (F.normalize 미적용)
```

- JSON에서 `imagePath` URL로 이미지 다운로드
- **전처리 없음** — 사진도 스케치도 원본 그대로 저장
- CLIP ViT-B/32 `encode_image()` → 512차원 raw 벡터 (norm ≈ 11.2)
- 메타데이터: `is_converted_to_sketch` 필드 **없음**

#### Step 3-B: JSON → 임베딩 v2 (`embeddings_v2.py`) — 사진 → 스케치 변환

```
입력:  data/json/
출력:  data/sketch/images_v2/      ← 전부 스케치 변환 이미지
       data/sketch/embeddings_v2/  ← CLIP 임베딩 JSON (F.normalize 적용)
```

- JSON에서 `imagePath` URL로 이미지 다운로드
- `detect_if_photo()` 로 사진/스케치 **자동 판별**
  - 흰색 픽셀 비율 > 95% && 평균 밝기 > 250 → 스케치 (그대로 유지)
  - 그 외 → 사진 → **Canny Edge Detection 스케치 변환**
- CLIP ViT-B/32 `encode_image()` + **F.normalize(dim=-1)** → unit vector (norm = 1.0)
- 메타데이터에 `is_converted_to_sketch: true/false` 기록

#### Step 4: 임베딩 JSON → ChromaDB (`vectordb.py`)

```
입력:  data/sketch/embeddings_v1/  또는  data/sketch/embeddings_v2/
출력:  data/sketch/chroma_db_v1/   또는  data/sketch/chroma_db_v2/
```

- 임베딩 JSON 읽기 → **F.normalize 재적용** (norm 불일치 방지)
- KIPRIS URL 대신 **로컬 절대경로** 매핑 (`imagePath` 필드)
- ChromaDB 컬렉션 클린 재구축 (기존 컬렉션 삭제 후 생성)
- `hnsw:space = cosine` 설정

```
최종 결과:
  chroma_db_v1/  ← 사진 + 스케치 혼재 임베딩 (레거시, 참고용)
  chroma_db_v2/  ← 스케치 도면만 임베딩 (app.py 기본 사용 버전)
```

---

## 4. 데이터 수집

### 출처: KIPRIS+ API (한국 특허정보원)

```
https://plus.kipris.or.kr/
API 키: KIPRISPLUS_API_KEY (환경변수)
```

### 수집 흐름

```
KIPRIS+ API
    ↓ (XML 응답)
processed/api_design.py       ← API 호출
    ↓
processed/xml_to_json.py      ← XML → JSON 파싱
    ↓
data/json/                    ← 특허별 메타데이터 + 이미지 URL 저장
    ↓
processed/embeddings_v2.py    ← URL에서 이미지 다운로드
    ↓
data/sketch/images_v2/        ← 전처리된 이미지 (21,829개)
```

### 수집 데이터 규모

| 항목 | 수량 |
|---|---|
| 총 특허 도면 이미지 | 21,829개 |
| 고유 출원번호 | 7,401개 |
| 평가용 거절 특허 | 57개 |
| JSON 메타데이터 | 21,829개 |

> **데이터 편향**: 전체의 99.6%가 화장품 용기·포장 계열 (비용기 계열 0.4%)

---

## 5. 데이터 전처리

### 사진/스케치 자동 감지 (`embeddings_v2.py`)

KIPRIS 특허 도면에는 **사진과 스케치 선화** 두 종류가 혼재합니다.
CLIP은 두 도메인이 혼재하면 임베딩 일관성이 저하되므로 **전부 스케치로 통일**합니다.

```python
def detect_if_photo(image):
    img_array = np.array(image.convert('L'))
    white_ratio      = np.sum(img_array > 260) / img_array.size
    mean_brightness  = np.mean(img_array)
    is_sketch = (white_ratio > 0.95 and mean_brightness > 250)
    return not is_sketch  # True면 사진 → 변환 필요
```

### Canny Edge Detection 변환 (스케치 통일화)

사진으로 판별된 이미지를 **흰 배경 + 검은 선화**로 변환합니다.
`embeddings_v2.py`, `app.py`, `design/inference.py` 세 파일 **완전히 동일한 파라미터** 사용.

```python
def convert_to_sketch(image: Image.Image) -> Image.Image:
    img_array = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
    blurred   = cv2.GaussianBlur(img_array, (5, 5), 1.0)  # 노이즈 제거
    edges     = cv2.Canny(blurred, 30, 120)                # 엣지 검출
    edges     = cv2.dilate(edges, np.ones((2, 2)), iterations=1)  # 선 두껍게
    sketch    = 255 - edges                                # 반전 (흰 배경)
    return Image.fromarray(cv2.cvtColor(sketch, cv2.COLOR_GRAY2RGB))
```

| 파라미터 | 값 | 설명 |
|---|---|---|
| GaussianBlur kernel | (5, 5) | 노이즈 제거 |
| GaussianBlur σ | 1.0 | 블러 강도 |
| Canny lower | 30 | 약한 엣지 임계값 |
| Canny upper | 120 | 강한 엣지 임계값 |
| Dilate kernel | (2, 2) | 선 두께 보정 |
| Dilate 반복 | 1회 | 선 두께 |
| 결과 포맷 | RGB (흰배경 + 검은선) | CLIP 입력 형식 |

> ✅ 57개 임베딩 전부 `is_converted_to_sketch: True` 로 확인됨

---

## 6. 데이터 임베딩

### 임베딩 생성 파이프라인 (`processed/embeddings_v2.py`)

```
JSON 메타데이터 읽기
    ↓
이미지 URL에서 다운로드 (requests)
    ↓
사진/스케치 자동 감지 (detect_if_photo)
    ↓ (사진이면)
Canny Edge Detection 스케치 변환
    ↓
data/sketch/images_v2/ 에 JPG로 저장
    ↓
CLIP ViT-B/32 encode_image()
    ↓
F.normalize(dim=-1) → unit vector (L2 norm = 1.0)
    ↓
512차원 벡터 + 메타데이터 → JSON 저장 (embeddings_v2/)
```

### CLIP 모델 설정

| 항목 | 값 |
|---|---|
| 모델 | CLIP ViT-B/32 (OpenAI) |
| 입력 크기 | 224 × 224 RGB |
| 출력 차원 | 512차원 |
| 정규화 | L2 normalize (F.normalize, dim=-1) → norm = 1.0 |
| 거리 지표 | 코사인 유사도 (0~1, 높을수록 유사) |
| 디바이스 | CUDA > MPS (Mac) > CPU 자동 감지 |

### ChromaDB 적재 (`processed/vectordb.py`)

임베딩 JSON을 읽어 ChromaDB에 적재할 때 두 가지 핵심 처리를 추가합니다.

```python
# [핵심 수정 1] F.normalize 재적용 (임베딩 생성 시 누락됐을 경우 대비)
def normalize_embedding(raw_emb: list) -> list:
    tensor = torch.tensor(raw_emb, dtype=torch.float32).unsqueeze(0)
    normed = F.normalize(tensor, dim=-1)   # norm: 11.x → 1.0
    return normed.squeeze(0).tolist()

# [핵심 수정 2] KIPRIS URL 대신 로컬 경로 매핑
def build_img_dict(image_dir: str) -> dict:
    # '3020140047287-reject-0_11.jpg' → key: '3020140047287-reject-0'
    img_dict = {}
    for fname in os.listdir(image_dir):
        stem = fname.rsplit(".", 1)[0]
        key  = stem.rsplit("_", 1)[0]
        img_dict[key] = os.path.join(image_dir, fname)
    return img_dict
```

---

## 7. ChromaDB 저장 컬럼

### 임베딩 JSON 구조 (`embeddings_v2/`)

```json
{
  "id": "3020140047287-reject-0-IMG-0",
  "embedding": [0.023, -0.014, ... ],   // 512차원 float 배열 (L2 정규화)
  "metadata": {
    "design_id":           "3020140047287-reject-0",
    "applicationNumber":   "3020140047287",
    "registrationNumber":  "3020140047287",
    "status": {
      "admstStat": "등록",
      "regFg": "Y"
    },
    "articleName":         "화장품용기",
    "LCCode":              "02-01",
    "image_id":            "img_001",
    "imagePath":           "http://plus.kipris.or.kr/...",
    "imageNumber":         "0",
    "designSummary":       "용기 전면부에 ...",
    "is_converted_to_sketch": true
  }
}
```

### ChromaDB 메타데이터 컬럼

| 컬럼명 | 타입 | 설명 | 예시 |
|---|---|---|---|
| `design_id` | str | 도면 고유 ID (출원번호-reject-인덱스) | `3020140047287-reject-0` |
| `applicationNumber` | str | 특허 출원번호 | `3020140047287` |
| `LCCode` | str | 로카르노 분류 코드 | `02-01` |
| `articleName` | str | 물품명 | `화장품용기` |
| `imageNumber` | str | 도면 번호 (출원 내 순번) | `0` |
| `admstStat` | str | 행정 처리 상태 | `등록`, `공개`, `출원` |
| `imagePath` | str | 로컬 이미지 파일 절대경로 | `/Users/.../image.jpg` |

### 파일명/ID 키 매핑 규칙

| 구분 | 패턴 | 공통 키 추출 방법 |
|---|---|---|
| 이미지 파일 | `3020140047287-reject-0_11.jpg` | `rsplit('_', 1)[0]` → `3020140047287-reject-0` |
| 임베딩 JSON ID | `3020140047287-reject-0-IMG-0` | `rsplit('-IMG-', 1)[0]` → `3020140047287-reject-0` |

---

## 8. RAG 구조

### 기본 RAG (`design/rag.py`)

```
사용자 이미지 업로드
    ↓
CLIP encode_image → 512차원 벡터
    ↓
ChromaDB.query() → Top-K 유사 도면 검색
    ↓
검색 결과 + 사용자 질문 → GPT-4o 프롬프트 조합
    ↓
FTO 분석 보고서 생성
```

### 고급 멀티스테이지 RAG (`design/rag_advanced.py`)

```
Stage 1: 입력 이미지 형상 분석
  └─ IMAGE_ANALYSIS_PROMPT → GPT-4o Vision
      "이미지에서 보이는 형상 요소만 객관적으로 서술하시오"

Stage 2: ChromaDB 유사도 검색
  └─ CLIP 임베딩 → Top-K 후보 도면 추출

Stage 3: 각 결과 도면 형상 분석
  └─ IMAGE_ANALYSIS_PROMPT (결과 도면에 동일 적용)

Stage 4: 입력 vs 결과 도면 1:1 비교
  └─ IMAGE_COMPARISON_PROMPT
      "두 디자인의 유사점/차이점을 시각적 요소 기준으로 분석하시오"

Stage 5: FTO 최종 보고서 생성
  └─ REPORT_PROMPT → GPT-4o
      "FTO 분석 참고 보고서 (법적 의견 아님)"

Stage 6: 답변 품질 검증
  └─ IMAGE_VALIDATION_PROMPT → 점수(1~10) 평가
```

### 프롬프트 목록 (`design/prompts.py`)

| 프롬프트 | 목적 |
|---|---|
| `IMAGE_ANALYSIS_PROMPT` | 이미지 형상 요소 분석 (가정 없이 관찰만) |
| `IMAGE_COMPARISON_PROMPT` | 두 디자인 유사점/차이점 비교 |
| `TEXT_SEARCH_COMBINED_ANALYSIS_PROMPT` | 텍스트 쿼리와 검색 결과 연관성 분석 |
| `IMAGE_FINAL_RESPONSE_PROMPT` | 이미지 쿼리 최종 응답 생성 |
| `TEXT_FINAL_RESPONSE_PROMPT` | 텍스트 쿼리 최종 응답 생성 |
| `IMAGE_VALIDATION_PROMPT` | 응답 품질 검증 (1~10점) |
| `REPORT_PROMPT` | FTO 비교 분석 보고서 생성 |

### Hybrid Retrieval (`design/app.py`)

```
쿼리 이미지
    │
    ├─ Dense Retrieval (CLIP 코사인 유사도 80%)
    │   └─ ChromaDB.query() → 50개 후보
    │
    └─ BM25 Retrieval (물품명 텍스트 유사도 20%)
        └─ Dense 1위 결과의 articleName → BM25 스코어 계산

min-max 정규화 후 가중 합산
    Hybrid = 0.8 × Dense_norm + 0.2 × BM25_norm

출원번호별 중복 제거 (동일 출원번호 중 최고 점수만 유지)
    ↓
Top-10 결과 반환
```

---

## 9. DB 전체 유사도 분석

### 데이터 카테고리 분포 (21,829개)

| 카테고리 | 개수 | 비율 |
|---|---|---|
| 화장품 용기 | ~6,000+ | ~27% |
| 포장용 용기 | 3,135 | 14.4% |
| 식품포장용 용기 | 1,832 | 8.4% |
| 기타 용기류 | ~10,000 | ~46% |
| **비용기 계열 전체** | **82** | **0.4%** |

> ⚠️ **99.6%가 용기/포장 계열** → 도메인이 극도로 단일화됨

### pairwise 코사인 유사도 분포 (57개 평가셋 기준)

```
구간별 분포 (전체 1,596쌍):
  [0.60 ~ 0.70):  303쌍  (19.0%)
  [0.70 ~ 0.75):  300쌍  (18.8%)
  [0.75 ~ 0.80):  302쌍  (18.9%)
  [0.80 ~ 0.85):  381쌍  (23.9%)  ← 최빈 구간
  [0.85 ~ 0.90):  204쌍  (12.8%)

→ 전체 1,596쌍 중 79.3%가 이미 유사도 0.7 이상
→ 평균 유사도: 0.7720
```

**결론**: 어떤 이미지를 쿼리해도 0.7~0.8대 결과가 나오는 것은 데이터 도메인의 구조적 문제.

### 발생한 문제 3가지

#### 문제 ① — KIPRIS URL 토큰 만료

```
http://plus.kipris.or.kr/openapi/fileToss.jsp?arg=ad7a17ee...
```
`arg` 파라미터가 세션 기반 토큰으로 시간이 지나면 만료 → 엉뚱한 이미지 반환

**해결**: 메타데이터에 로컬 절대경로 저장 (`imagePath`)

#### 문제 ② — 임베딩 정규화 불일치

```python
# embeddings_v2.py (저장 시) — 문제 코드: norm ≈ 11.2
image_embedding = model.encode_image(image_tensor)

# app.py (검색 시) — 정규화 적용: norm = 1.0
emb = F.normalize(emb, dim=-1)
```

저장 벡터와 쿼리 벡터의 스케일 차이로 비교가 부정확.
**해결**: vectordb.py에서 ChromaDB 적재 전 `F.normalize` 일괄 적용.

#### 문제 ③ — 스케치 전처리 도메인 불일치

```
저장된 임베딩 = Canny Edge Detection 변환 이미지 기반 ✓
쿼리 임베딩   = 원본 이미지 그대로 (전처리 없음) ✗
```

**해결**: `app.py`의 `get_image_embedding()` 내에 `convert_to_sketch_query()` 추가.

---

## 10. CLIP 파인튜닝 전략

### 왜 파인튜닝이 필요한가?

CLIP ViT-B/32는 **의미론적(semantic) 유사도**를 측정합니다.
"화장품용기"라는 카테고리끼리는 디자인이 달라도 임베딩 공간에서 가깝게 위치합니다.

```
측정값 (정규화 후 코사인 유사도):
  서로 다른 출원번호의 화장품 용기:  0.7911 (높음 — 다른 디자인인데도)
  '화장품용기' vs '포장용기' 평균:   0.9509 (매우 높음)
```

**목표**: 같은 출원번호 도면은 가깝게, 다른 출원번호 도면은 멀게 재학습.

### Freeze 전략 (Partial Fine-tuning)

```
CLIP ViT-B/32 전체 파라미터: 151,277,313개
├── Text Encoder          → 완전 동결 (이미지 검색이므로 불필요)
├── Visual Encoder Block 0~9  → 완전 동결 (사전학습 지식 보존)
├── Visual Encoder Block 10~11 → 학습 (마지막 2개 블록)
├── Visual Projection Layer   → 학습
├── LayerNorm (ln_post)       → 학습
└── logit_scale               → 학습

학습 파라미터: ~14,177,281개 (전체의 약 9.4%)
```

### Loss 함수: InfoNCE (NT-Xent, Symmetric)

```python
class InfoNCELoss(nn.Module):
    def forward(self, anchor_feat, positive_feat):
        anchor_feat   = F.normalize(anchor_feat,   dim=-1)
        positive_feat = F.normalize(positive_feat, dim=-1)

        # 유사도 행렬: [B, B]
        logits = torch.matmul(anchor_feat, positive_feat.T) / self.temperature

        # 대각선이 정답 (i번째 anchor ↔ i번째 positive)
        labels = torch.arange(len(logits), device=logits.device)

        # 양방향 symmetric loss
        loss_a2p = F.cross_entropy(logits,   labels)
        loss_p2a = F.cross_entropy(logits.T, labels)
        return (loss_a2p + loss_p2a) / 2
```

- **temperature = 0.07**: 낮을수록 hard negative 구별을 엄격하게 학습
- **In-batch negatives**: 배치 내 다른 샘플이 자동으로 negative 역할 (batch_size가 클수록 효과적)

---

## 11. Triplet 데이터 자동 구성

### 구성 원칙

```
Positive 쌍: 같은 출원번호 내 도면 (같은 디자인, 다른 뷰/각도)
Negative 쌍: 다른 출원번호의 도면 (다른 디자인)
```

### 3개 Excel → 통합 페어 데이터셋

| 파일 | 내용 | Anchor 폴더 | Positive 폴더 |
|---|---|---|---|
| `dataset_combined_final.xlsx` | cross-folder 페어 | `images_reject/` | `images_reject_v2/` |
| `dataset_images_reject.xlsx` | reject 폴더 내 유사 제품 페어 | `images_reject/` | `images_reject/` |
| `dataset_images_reject_v2.xlsx` | reject_v2 폴더 내 유사 제품 페어 | `images_reject_v2/` | `images_reject_v2/` |

### 21,829개 전체 데이터 기반 Triplet 규모

```
7,401개 출원번호 × 평균 3장 도면
→ 41,792개 Triplet 자동 생성

  Hard Negative: 20,318개  (같은 물품명, 다른 출원번호 — 세밀한 차이 학습)
  Easy Negative: 21,474개  (다른 물품명, 다른 출원번호 — 기본 분리 학습)
```

### 데이터 로딩 코드 (`train/train.py`)

```python
def load_all_pairs(cfg) -> pd.DataFrame:
    # 3개 엑셀 통합 후 중복 제거 + 파일 존재 검증
    rows = []
    for excel in [cfg.data_combined, cfg.data_reject, cfg.data_reject_v2]:
        df = pd.read_excel(excel)
        # anchor_path, positive_path 컬럼으로 통일
        rows.extend(...)

    df = pd.DataFrame(rows).drop_duplicates(["anchor_path", "positive_path"])
    df = df[df["anchor_path"].apply(os.path.exists) &
            df["positive_path"].apply(os.path.exists)]
    return df
```

---

## 12. 학습 설계

### 하이퍼파라미터

| 항목 | 값 | 설명 |
|---|---|---|
| 모델 | CLIP ViT-B/32 | 기본 백본 |
| Loss | InfoNCE (Symmetric NT-Xent) | Contrastive Loss |
| Temperature | 0.07 | CLIP 원논문 기본값 |
| Optimizer | AdamW | Adam + weight decay 분리 |
| Learning Rate | 1e-5 | CLIP 미세조정 권장 (낮은 LR) |
| Weight Decay | 1e-4 | L2 정규화 계수 |
| Batch Size | 8 (Mac), 32 (CUDA) | In-batch negatives 수 = batch-1 |
| Epochs | 100 | 총 학습 반복 횟수 |
| Val Ratio | 0.15 | 검증셋 비율 |
| Unfreeze Layers | 2 | Visual Encoder 마지막 2블록만 학습 |
| Seed | 42 | 재현성 고정 |

### LR 스케줄러: Cosine Annealing with Warmup

```python
total_steps  = epochs * len(train_loader)
warmup_steps = int(0.1 * total_steps)   # 초반 10% warmup

def lr_lambda(step):
    if step < warmup_steps:
        return step / max(1, warmup_steps)          # 0 → 1 선형 증가
    progress = (step - warmup_steps) / (total_steps - warmup_steps)
    return 0.5 * (1.0 + np.cos(np.pi * progress))  # 1 → 0 코사인 감소
```

### 디바이스별 처리

| 디바이스 | 혼합정밀도 | GradScaler | 비고 |
|---|---|---|---|
| CUDA | FP16 autocast ✓ | 활성화 | gradient underflow 방지 |
| MPS (Mac) | 미지원 | 비활성화 | 일반 FP32 backward |
| CPU | 미지원 | 비활성화 | 폴백 |

### 모델 저장 기준

```python
# R@1이 이전 최고보다 높을 때 저장
if r1 > best_recall:
    torch.save({
        "epoch":       epoch,
        "model_state": model.state_dict(),
        "optimizer":   optimizer.state_dict(),
        "recalls":     recalls,
        "config":      vars(cfg),
    }, "checkpoints/best_model.pt")
```

---

## 13. 학습 모니터링 지표

### 주요 지표

| 지표 | 의미 | 목표 방향 |
|---|---|---|
| `train_loss` | 학습셋 InfoNCE Loss | ↓ 감소 |
| `R@1` | Recall@1: anchor 기준 Top-1 안에 positive가 있는 비율 | ↑ 증가 |
| `R@5` | Recall@5: Top-5 안에 positive | ↑ 증가 |
| `R@10` | Recall@10: Top-10 안에 positive | ↑ 증가 |

### Recall@K 계산 방법

```python
@torch.no_grad()
def evaluate_recall_at_k(model, val_loader, device, k_list=(1, 5, 10)):
    # 전체 val 셋의 anchor/positive 임베딩 추출
    anchors   = []  # [N, 512]
    positives = []  # [N, 512]

    # 유사도 행렬 [N, N] 계산
    sim_matrix = torch.matmul(anchors, positives.T)

    for k in k_list:
        top_k_indices = sim_matrix.topk(k, dim=1).indices  # [N, K]
        labels        = torch.arange(len(anchors))
        # i번째 anchor의 top-K 안에 i번째 positive가 있으면 correct
        correct = (top_k_indices == labels.unsqueeze(1)).any(dim=1)
        recalls[f"R@{k}"] = correct.float().mean().item()
```

### 학습 결과 저장

```
train/checkpoints/
├── best_model.pt        ← R@1 최고 epoch 모델
└── train_history.csv    ← epoch별 train_loss, R@1, R@5, R@10
```

### 학습 요약 출력 예시

```
╔══════════════════════════════════════════╗
║           📊 학습 결과 요약               ║
╠══════════════════════════════════════════╣
║  [Best Model - Epoch 47]                 ║
║    R@1  : 0.7143                         ║
║    R@5  : 1.0000                         ║
║    R@10 : 1.0000                         ║
║    Loss : 0.0234                         ║
╚══════════════════════════════════════════╝
```

---

## 14. 실행 방법

### Step 0: 환경 설정

```bash
cd FTO_ImgProject
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r design/requirements_app.txt
```

### Step 1: 데이터 수집 (KIPRIS API)

```bash
# KIPRIS XML 수집
python processed/api_design.py

# XML → JSON 변환
python processed/xml_to_json.py
# 결과: data/json/ 에 특허별 JSON 생성
```

### Step 2: 임베딩 생성

```bash
python processed/embeddings_v2.py
# 결과:
#   data/sketch/images_v2/       ← 21,829개 스케치 변환 이미지
#   data/sketch/embeddings_v2/   ← 21,829개 CLIP 임베딩 JSON
```

### Step 3: ChromaDB 구축

```bash
python processed/vectordb.py
# 출력 예시:
#   ✅ 이미지 딕셔너리 구축 완료: 21,829개
#   ✅ [1] 3020140047287-0-IMG-0 → 3020140047287-0_11.jpg
#   📦 최종 컬렉션 크기: 21,829개
```

### Step 4: Streamlit 검색 앱 실행

```bash
streamlit run design/app.py
# → http://localhost:8501 접속
# 사이드바 → "🖊️ 쿼리 스케치 변환 미리보기" 체크로 전처리 확인
```

### Step 5 (선택): CLIP 파인튜닝

```bash
pip install -r train/requirements.txt

# 학습 시작 (CUDA 권장: ~2시간, Mac MPS: ~6시간)
python train/train.py \
    --epochs 100 \
    --batch_size 8 \
    --lr 1e-5 \
    --unfreeze_layers 2

# 결과물
#   train/checkpoints/best_model.pt      ← 최적 모델
#   train/checkpoints/train_history.csv  ← 학습 기록
```

### Step 6 (선택): 파인튜닝 모델로 DB 재구축

```bash
# 파인튜닝된 CLIP으로 전체 이미지 재임베딩 + ChromaDB 재구축
python design/inference.py

# app.py에서 파인튜닝 모델 활성화:
# FINETUNED_MODEL_PATH = "train/checkpoints/best_model.pt"
```

---

## 15. 환경변수

`.env` 파일에 다음 키를 설정합니다.

```env
OPENAI_API_KEY=sk-proj-...          # GPT-4o 호출 (RAG 보고서 생성)
KIPRISPLUS_API_KEY=RX2PxJo5...      # KIPRIS+ 특허 API (데이터 수집)
```

| 변수명 | 용도 | 필수 여부 |
|---|---|---|
| `OPENAI_API_KEY` | GPT-4o Vision API (RAG 분석 보고서) | RAG 사용 시 필수 |
| `KIPRISPLUS_API_KEY` | 한국 특허정보원 KIPRIS+ API (특허 데이터 수집) | 데이터 수집 시 필수 |

---

## 16. 핵심 결론

### 문제 요약

| # | 문제 | 원인 | 해결 |
|---|---|---|---|
| ① | 엉뚱한 이미지 표시 | KIPRIS URL 토큰 만료 | 로컬 절대경로 저장 |
| ② | 유사도 비정상 (0.79) | 임베딩 저장 시 F.normalize 미적용 | vectordb.py에서 재정규화 |
| ③ | 쿼리-DB 도메인 불일치 | DB는 스케치, 쿼리는 원본 | app.py에 Canny 전처리 추가 |
| ④ | 전체 DB 유사도 과집중 | 99.6% 용기류 — 단일 도메인 | Triplet Loss 파인튜닝 |

### 개선 우선순위

| 우선순위 | 작업 | 난이도 | 기대 효과 |
|---|---|---|---|
| ⭐⭐⭐ | vectordb.py 재실행 (F.normalize + 로컬경로) | 낮음 | 즉시 이미지 표시 정상화 |
| ⭐⭐⭐ | app.py 스케치 전처리 통일 | 낮음 | 쿼리-DB 도메인 일치 |
| ⭐⭐ | CLIP InfoNCE Contrastive Fine-tuning | 중간 | 같은 출원번호 도면 거리 개선 |
| ⭐ | 비용기 카테고리 데이터 추가 | 높음 | 카테고리 간 상대적 차별화 |

### 전체 시스템 흐름도

```
[데이터 수집]
KIPRIS API → XML → JSON → 이미지 다운로드
                               ↓
[데이터 전처리]         사진/스케치 자동 감지
                               ↓ (사진이면)
                        Canny Edge Detection → 스케치 변환
                               ↓
[임베딩 생성]          CLIP ViT-B/32 encode_image()
                               ↓
                        F.normalize → unit vector (512차원)
                               ↓
[벡터 DB 구축]         ChromaDB (cosine space) + 로컬경로 매핑
                               ↓
[검색 (app.py)]        이미지 업로드 → Canny 전처리 → CLIP 임베딩
                               ↓
                  ┌──── Dense 80% (CLIP cosine) ────┐
                  └──── BM25  20% (articleName) ────┘
                               ↓
                        Hybrid Score 가중 합산
                               ↓
                        출원번호별 중복 제거
                               ↓
                        Top-10 결과 표시
                               ↓
[RAG 분석]             GPT-4o → FTO 비교 분석 보고서
                               ↓
[파인튜닝 (선택)]      InfoNCE Loss + Partial Freeze
                        → 같은 출원번호 도면: 거리 ↓
                        → 다른 출원번호 도면: 거리 ↑
```

> **핵심 결론**
> 현재 DB의 근본적 한계는 99.6%가 용기류라는 **데이터 도메인 단일성**입니다.
> 단기적으로는 **전처리 통일(스케치)** + **정규화(F.normalize)**로 일관성을 확보하고,
> 중기적으로 **Contrastive Fine-tuning**으로 같은 출원번호 도면은 가깝게,
> 다른 출원번호 도면은 멀게 만드는 방향이 현실적입니다.
> 장기적으로는 비용기 카테고리 데이터 확보가 필요합니다.
