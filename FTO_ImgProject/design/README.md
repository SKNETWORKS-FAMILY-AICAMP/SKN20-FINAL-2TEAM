# 디자인 특허 유사 이미지 검색 시스템

> **목적**: KIPRIS 특허 도면 이미지를 대상으로 Hybrid Retrieval (Dense CLIP + BM25) 기반 유사 디자인 검색  
> **데이터 규모**: 21,829개 특허 도면 | 7,401개 출원번호 | 692개 물품 카테고리

---

## 목차

1. [전체 파이프라인](#1-전체-파이프라인)
2. [디렉터리 구조 및 파일 역할](#2-디렉터리-구조-및-파일-역할)
3. [데이터 흐름 상세](#3-데이터-흐름-상세)
4. [핵심 파라미터 및 설정 이유](#4-핵심-파라미터-및-설정-이유)
5. [실행 방법](#5-실행-방법)
6. [학습 결과 (train_history.csv)](#6-학습-결과)
7. [알려진 한계 및 개선 방향](#7-알려진-한계-및-개선-방향)
8. [의존성 설치](#8-의존성-설치)

---

## 1. 전체 파이프라인

```
[rawdata/1981-2026.xlsx]
        │  KIPRIS 검색식으로 수집한 출원번호 목록
        ▼
[api_xml/*.xml]
        │  KIPRIS Open API → XML 수집 (7,427개)
        ▼
[json/*.json]
        │  XML 파싱 → 정제된 JSON (21,909개)
        ▼
[images_v2/*.jpg]          [images_v1/*.jpg]
        │  이미지 다운로드          │  v1 원본 이미지
        │  + 스케치 자동 감지/변환   │  (스케치 변환 없음)
        ▼
[embeddings_v2/*.json]     [embeddings_v1/*.json]
        │  CLIP ViT-B/32 임베딩     │  CLIP ViT-B/32 임베딩
        │  (Canny Edge 전처리 적용) │  (전처리 없음)
        ▼
[chroma_db_v2/]            [chroma_db_v1/]
        │  ChromaDB 벡터 저장       │  v1 벡터 저장
        ▼
[app.py]
        Streamlit 검색 UI
        Hybrid Retrieval (Dense + BM25)
```

> **v1 vs v2 차이**: v2는 이미지가 사진인지 스케치 도면인지 자동 판별 후  
> 사진이면 Canny Edge Detection으로 스케치 변환, 도면이면 원본 유지.

---

## 2. 디렉터리 구조 및 파일 역할

```
3차_테스트/
│
├── rawdata/
│   └── 1981-2026.xlsx          # KIPRIS 검색식 기반 수집 대상 출원번호 목록
│                               # 검색식: (용기+케이스+병+...) * LC=[09-01]
│
├── api_xml/                    # 7,427개 XML 파일
│   └── {출원번호}.xml           # KIPRIS Open API 응답 원본
│                               # 포함 정보: 출원번호, 물품명, 창작요점,
│                               #           출원인, 대리인, 등록상태, 도면 URL
│
├── json/                       # 21,909개 JSON 파일
│   └── {출원번호}-{도면번호}.json # XML 파싱 후 정제된 단일 도면 단위 데이터
│                               # api_xml 1개 → json 여러 개 (도면 수만큼 분리)
│
├── images_v1/                  # 21,895개 .jpg (원본 이미지, 전처리 없음)
├── images_v2/                  # 21,829개 .jpg (스케치 자동 감지 + 변환 적용)
│   └── {출원번호}-api_xml-{도면인덱스}_{번호}.jpg
│
├── embeddings_v1/              # 21,801개 임베딩 JSON (v1 이미지 기반)
├── embeddings_v2/              # 21,829개 임베딩 JSON (v2 이미지 기반) ← 사용 중
│   └── {출원번호}-api_xml-{도면인덱스}-{도면번호}_embedding.json
│       구조: { "id", "embedding": [512차원], "metadata": {...} }
│
├── chroma_db_v1/               # v1 임베딩 기반 ChromaDB (사용 안 함)
├── chroma_db_v2/               # v2 임베딩 기반 ChromaDB ← 현재 사용
│   ├── chroma.sqlite3          # 메타데이터 + 인덱스 (29.2 MB)
│   └── {uuid}/                 # HNSW 벡터 인덱스 파일
│
├── triplets.csv                # CLIP 파인튜닝용 Triplet 쌍 (41,792개)
│   컬럼: anchor_path, positive_path, negative_path,
│         anchor_id, positive_id, negative_id,
│         applicationNumber, articleName, negative_type(hard/easy)
│
├── train_history.csv           # 학습 이력 (100 epoch)
│   컬럼: epoch, train_loss, R@1, R@5, R@10
│
└── 평가데이터/
    ├── images_reject_v2/       # 57개 거절 특허 이미지
    ├── embeddings_reject_v2/   # 57개 거절 특허 임베딩
    ├── chroma_db_train_v2/     # 57개 평가용 ChromaDB ← app.py 기본값
    └── chroma_db_finetuned/    # 파인튜닝 완료 후 재구축되는 ChromaDB

design/
├── app.py                      # Streamlit 검색 앱 (메인 실행 파일)
├── inference.py                # 파인튜닝 모델로 재임베딩 + ChromaDB 재구축
├── clip_finetune.py            # CLIP Triplet Loss 파인튜닝 (train.py 역할)
├── vectordb.py                 # embeddings JSON → ChromaDB 구축
├── embeddings_v2.py            # 이미지 다운로드 + 스케치 변환 + CLIP 임베딩
├── xml_to_json.py              # api_xml XML → json 폴더 변환
├── requirements_app.txt        # 의존성 목록
└── README.md                   # 이 파일
```

### 임베딩 JSON 내부 구조

```json
{
  "id": "3020180025466-api_xml-1-IMG-1",
  "embedding": [0.123, -0.456, ...],   // 512차원 float 배열 (norm ≈ 11.x, 비정규화)
  "metadata": {
    "design_id":           "3020180025466-api_xml-1",
    "applicationNumber":   "3020180025466",
    "registrationNumber":  "3009827470000",
    "status": {
      "regFg":             "Y",
      "admstStat":         "등록",
      "lastDispositionDate": "2018-11-15"
    },
    "articleName":         "식품포장용 용기",
    "LCCode":              "api_xml",
    "imagePath":           "http://plus.kipris.or.kr/...",  // KIPRIS URL (만료 위험)
    "imageNumber":         1,
    "designSummary":       "\"식품포장용 용기\"의 형상과 모양의 결합을 ...",
    "is_converted_to_sketch": true    // 사진 → 스케치 변환 여부
  }
}
```

> ⚠️ **주의**: `embedding` 값의 norm ≈ 11.x (비정규화 상태).  
> ChromaDB 저장 시 vectordb.py 에서 `F.normalize` 적용 필요 (개선 완료).

### ChromaDB 메타데이터 컬럼

| 컬럼 | 내용 | 예시 |
|---|---|---|
| `design_id` | 도면 고유 ID | `3020180025466-api_xml-1` |
| `applicationNumber` | 출원번호 | `3020180025466` |
| `articleName` | 물품명 | `식품포장용 용기` |
| `LCCode` | 출처 코드 | `api_xml` |
| `imageNumber` | 도면 번호 | `1` |
| `admstStat` | 처리상태 | `등록` / `공개` / `출원` |
| `imagePath` | 이미지 경로 | 로컬 경로 또는 KIPRIS URL |

---

## 3. 데이터 흐름 상세

### Step 1. rawdata → api_xml (KIPRIS 수집)

`rawdata/1981-2026.xlsx` 에 저장된 검색식으로 KIPRIS Open API를 호출하여  
각 출원번호별 XML 응답을 `api_xml/{출원번호}.xml` 로 저장.

XML 주요 블록:
```
<response>
  <body>
    <item>
      <biblioSummaryInfoArray>   출원번호, 물품명, 등록상태
      <applicantInfoArray>       출원인 정보
      <agentInfoArray>           대리인 정보
      <creativeDescriptionInfoArray>  디자인 설명
      <creativeSummaryInfoArray>      창작의 요점 (designSummary)
      <legalStatusInfoArray>     법적 상태 이력
```

---

### Step 2. api_xml → json (XML 파싱)

`xml_to_json.py` 실행 → `api_xml/*.xml` 을 파싱하여 도면 단위로 분리.

하나의 출원번호에 도면이 3개면 → JSON 3개 생성:
```
3020040015192.xml  →  3020040015192-0.json
                       3020040015192-1.json
                       3020040015192-2.json
```

JSON 구조:
```json
{
  "design_id":         "3020040015192-api_xml-1",
  "applicationNumber": "3020040015192",
  "status":   { "regFg", "admstStat", "lastDispositionDate" },
  "meta":     { "articleName", "LCCode", "applicantName", "agentName" },
  "image":    { "image_id", "imageName", "imagePath", "number" },
  "creative": { "designSummary", "designDescription" }
}
```

---

### Step 3. json → images_v2 + embeddings_v2 (임베딩 생성)

`embeddings_v2.py` 실행 → JSON에서 이미지 URL 추출 → 다운로드 → 전처리 → CLIP 임베딩.

```
json/{출원번호}-{n}.json
        │
        ├── imagePath URL로 이미지 다운로드
        │
        ├── detect_if_photo() 판별
        │       white_ratio > 0.95 AND mean_brightness > 250  → 스케치 도면 (원본 유지)
        │       그 외                                          → 사진 (스케치 변환)
        │
        ├── [사진인 경우] convert_to_sketch()
        │       GaussianBlur(5, 5, σ=1.0) → 노이즈 제거
        │       Canny(low=30, high=120)   → 엣지 검출
        │       dilate(kernel=2×2, iter=1) → 선 굵게
        │       invert(255 - edges)        → 흰 배경 + 검은 선
        │
        ├── images_v2/{design_id}_{imageName}.jpg 저장
        │
        └── CLIP ViT-B/32 encode_image()
                → 512차원 임베딩
                → embeddings_v2/{design_id}-{number}_embedding.json 저장
```

**전체 처리 결과 (21,829개)**:

| 구분 | 개수 | 비율 |
|---|---|---|
| 스케치 변환됨 (`is_converted_to_sketch: true`) | 10,698개 | 49.0% |
| 원본 유지 (`is_converted_to_sketch: false`) | 11,131개 | 51.0% |

---

### Step 4. embeddings_v2 → chroma_db_v2 (ChromaDB 구축)

`vectordb.py` 실행 → embeddings_v2 JSON을 읽어 ChromaDB에 저장.

```python
# 컬렉션 설정
image_collection = chroma_client.get_or_create_collection(
    name="design",
    metadata={"hnsw:space": "cosine"}   # 코사인 거리 사용
)
```

> ⚠️ **개선된 vectordb.py**: F.normalize 적용 + 로컬 이미지 경로 자동 매핑 포함.

---

### Step 5. app.py (검색 실행)

```
업로드 이미지
        │
        ├── convert_to_sketch_query()   ← DB 임베딩과 동일한 전처리
        │       GaussianBlur(5,5,1.0) / Canny(30,120) / dilate(2×2)
        │
        ├── CLIP encode_image() + F.normalize()  → 쿼리 벡터 (512차원, norm=1.0)
        │
        ├── ChromaDB.query()  →  Dense Top-50 후보 추출
        │       거리 방식: cosine  (distance = 1 - cosine_similarity)
        │
        ├── BM25  →  Dense 1위 결과의 articleName을 텍스트 쿼리로 사용
        │            전체 57개 대상 BM25 점수 계산
        │
        ├── min-max 정규화 (Dense + BM25 각각)
        │
        └── Hybrid Score = Dense × 0.8 + BM25 × 0.2
                    → Top-10 반환
```

---

## 4. 핵심 파라미터 및 설정 이유

### 스케치 판별 임계값 (`detect_if_photo`)

```python
is_sketch = (white_ratio > 0.95 and mean_brightness > 250)
```

| 파라미터 | 값 | 설정 이유 |
|---|---|---|
| `white_ratio > 0.95` | 픽셀의 95% 이상이 흰색 | 특허 도면은 흰 배경에 검은 선이므로 흰색 비율이 매우 높음 |
| `mean_brightness > 250` | 평균 밝기 250 이상 | 밝기가 낮으면 실제 사진 또는 색상 도면일 가능성 높음 |
| AND 조건 | 두 조건 모두 만족 | 어느 하나만으로는 오판 발생 — 둘 다 만족해야 확실한 스케치 |

> **결과**: 전체 21,829개 중 49%가 스케치 변환됨 (사진 비율 높았음)

---

### Canny Edge Detection 파라미터 (`convert_to_sketch`)

```python
blurred = cv2.GaussianBlur(img_array, (5, 5), 1.0)
edges   = cv2.Canny(blurred, 30, 120)
edges   = cv2.dilate(edges, np.ones((2, 2), np.uint8), iterations=1)
```

| 파라미터 | 값 | 설정 이유 |
|---|---|---|
| `GaussianBlur kernel (5, 5)` | 5×5 | 노이즈 제거에 충분한 크기. 3×3은 작아서 노이즈 잔존, 7×7은 선이 뭉침 |
| `GaussianBlur σ=1.0` | 1.0 | 세부 선이 유지되는 최소 blur. 값이 크면 디자인 특징이 사라짐 |
| `Canny low=30` | 30 | 낮은 임계값 → 약한 엣지도 포착. 특허 도면의 가는 선을 놓치지 않기 위함 |
| `Canny high=120` | 120 | high/low 비율 = 4:1. Canny 권장 비율 2:1~3:1 보다 넓게 설정하여 연결선 보존 |
| `dilate kernel (2, 2)` | 2×2 | 검출된 엣지 선을 1픽셀 굵게. 얇은 선이 CLIP 입력 시 소실되는 것 방지 |
| `dilate iterations=1` | 1회 | 1회로 충분. 2회 이상이면 선들이 합쳐져 디자인 특징 훼손 |

---

### CLIP 모델

```python
CLIP_MODEL_NAME = "ViT-B/32"
```

| 항목 | 내용 |
|---|---|
| 모델 | CLIP ViT-B/32 (Vision Transformer Base, patch 32) |
| 임베딩 차원 | 512차원 |
| 선택 이유 | 속도-성능 균형. ViT-L/14는 768차원으로 검색 속도 느림. ViT-B/32는 로컬 CPU에서도 실시간 검색 가능 |
| 한계 | 범용 모델 → 같은 카테고리(용기류) 내 미세한 디자인 차이 구분 어려움 |

---

### Hybrid Retrieval 파라미터 (`app.py`)

```python
DENSE_WEIGHT    = 0.8   # Dense 가중치
BM25_WEIGHT     = 0.2   # BM25 가중치
TOP_K           = 10    # 최종 반환 개수
RETRIEVAL_TOP_K = 50    # Dense 초기 검색 풀 크기
```

| 파라미터 | 값 | 설정 이유 |
|---|---|---|
| `DENSE_WEIGHT = 0.8` | 80% | 이미지 기반 검색이 핵심. BM25는 보조 역할 |
| `BM25_WEIGHT = 0.2` | 20% | 물품명 텍스트가 같으면 유사도 소폭 보정. 단독 사용 시 모든 '화장품 용기'가 동점 |
| `RETRIEVAL_TOP_K = 50` | 50개 | 57개 DB에서 전체의 88%를 후보로 잡음. BM25 reranking 대상 충분히 확보 |
| `TOP_K = 10` | 10개 | 심사관이 실제로 검토 가능한 수. 57개 중 10개는 18% |

> **BM25 쿼리 방식 주의**: 이미지 쿼리이므로 텍스트 쿼리가 없음.  
> Dense 검색 1위 결과의 `articleName`을 BM25 텍스트 쿼리로 사용.  
> → 결과적으로 BM25가 같은 물품명을 가진 항목들을 부스팅하는 효과.

---

### 임베딩 정규화

```python
# 저장 시 (vectordb.py - 개선 후)
normed = F.normalize(tensor, dim=-1)   # norm: ~11 → 1.0

# 검색 시 (app.py)
emb = F.normalize(emb, dim=-1)         # unit vector 보장
```

| 구분 | 이전 | 이후 |
|---|---|---|
| 저장된 임베딩 norm | ~11.x (비정규화) | 1.0 (unit vector) |
| 쿼리 임베딩 norm | 1.0 | 1.0 |
| 이유 | ChromaDB cosine은 수식상 처리하지만 명시적 정규화가 안정적 | 쿼리-DB 스케일 완전 통일 |

---

## 5. 실행 방법

### 환경 설정

```bash
# 의존성 설치 (requirements_app.txt 기준)
pip install -r design/requirements_app.txt

# CLIP 별도 설치 (pip 미지원)
pip install git+https://github.com/openai/CLIP.git

# OpenCV (Canny 전처리용)
pip install opencv-python
```

---

### 파이프라인 전체 실행 순서

#### 1단계: XML → JSON 변환

```bash
python design/xml_to_json.py
# 입력: 3차_테스트/api_xml/*.xml
# 출력: 3차_테스트/json/*.json
```

#### 2단계: 이미지 다운로드 + 스케치 변환 + CLIP 임베딩

```bash
python design/embeddings_v2.py
# 입력:  3차_테스트/json/*.json
# 출력:  3차_테스트/images_v2/*.jpg
#        3차_테스트/embeddings_v2/*_embedding.json
# 소요:  약 2~4시간 (21,829개, CPU 기준)
```

#### 3단계: ChromaDB 구축

```bash
python design/vectordb.py
# 입력:  3차_테스트/embeddings_v2/*_embedding.json
#        3차_테스트/images_v2/*.jpg  (로컬 경로 자동 매핑)
# 출력:  3차_테스트/chroma_db_v2/
```

#### 4단계: 검색 앱 실행

```bash
streamlit run design/app.py
# 접속: http://localhost:8501
```

> **파인튜닝 없이 바로 실행 가능** — 원본 CLIP으로 검색.

---

### (선택) CLIP 파인튜닝 실행 순서

#### 1단계: Triplet CSV 생성

이미 생성됨 → `3차_테스트/triplets.csv` (41,792개 triplet)

직접 생성하려면:
```python
# 핵심 로직
# Positive: 같은 applicationNumber, 다른 도면 인덱스
# Negative: 다른 applicationNumber
#   hard(70%): 같은 articleName, 다른 applicationNumber
#   easy(30%): 다른 articleName
```

#### 2단계: CLIP 파인튜닝

```bash
python design/clip_finetune.py
# 입력:  3차_테스트/triplets.csv
# 출력:  3차_테스트/clip_finetuned/clip_finetuned_best.pt
#        3차_테스트/clip_finetuned/training_log.csv
# 소요:  약 2~4시간 (GPU), 10~20시간 (MPS/CPU)
```

학습 모니터링:
```
Epoch 01/30 | Train=0.1823 | Val=0.1901 | d_pos=0.2134 | d_neg=0.4521 | gap=+0.2387
                                                                              ↑
                                                           이 값이 양수로 증가하면 성공
```

#### 3단계: 파인튜닝 모델로 재임베딩 + ChromaDB 재구축

```bash
python design/inference.py
# 입력:  clip_finetuned_best.pt
#        평가데이터/images_reject_v2/*.jpg
# 출력:  평가데이터/embeddings_reject_finetuned/*.json
#        평가데이터/chroma_db_finetuned/
```

#### 4단계: app.py 파인튜닝 모드 전환

`design/app.py` 상단 설정 2줄 수정:

```python
# 변경 전 (원본 CLIP)
CHROMA_DB_PATH       = ".../chroma_db_train_v2"
FINETUNED_MODEL_PATH = None

# 변경 후 (파인튜닝 모델)
CHROMA_DB_PATH       = ".../chroma_db_finetuned"
FINETUNED_MODEL_PATH = ".../clip_finetuned_best.pt"
```

---

## 6. 학습 결과

`train_history.csv` 100 에폭 학습 결과:

| 에폭 | Train Loss | R@1 | R@5 | R@10 |
|---|---|---|---|---|
| 1 | 1.4575 | 0.2857 | 0.6429 | 0.8095 |
| 10 | - | - | - | - |
| 50 | ~0.5 | - | - | - |
| 98 | 0.2170 | 0.2143 | **1.0** | **1.0** |
| 99 | 0.2362 | 0.2381 | **1.0** | **1.0** |
| 100 | 0.2191 | 0.2143 | **1.0** | **1.0** |

**해석**:

- **R@5 = 1.0, R@10 = 1.0 (에폭 후반)**: Top-5, Top-10 검색 내에 정답이 항상 포함됨
- **R@1 = 0.21 (에폭 후반)**: 1순위 정확도는 낮음 — 같은 디자인의 다른 뷰가 1위가 아닌 경우 존재
- **Train Loss 하강 + R@1 정체**: 모델이 쉬운 패턴은 학습했으나 세밀한 구분은 어려움
- **R@5/R@10 = 1.0 이면**: 실용적으로 "Top-10 결과 안에 반드시 유사 이미지 존재" 보장

---

## 7. 알려진 한계 및 개선 방향

### 한계 1: DB 도메인 단일성 (가장 큰 문제)

```
21,829개의 99.6% = 용기/포장 계열
→ 카테고리 간 평균 코사인 유사도 0.85~0.95
→ 어떤 이미지를 입력해도 Dense Score 0.7대로 수렴
```

**개선**: 다양한 물품류(가방, 가전, 신발 등) 데이터 추가.

---

### 한계 2: CLIP ViT-B/32 카테고리 수준 인식

```
CLIP은 "화장품용기"라는 카테고리를 인식
→ 화장품용기 A vs 화장품용기 B : 유사도 0.79 (육안으로 달라도)
```

**개선**: Triplet Loss 파인튜닝으로 같은 출원번호 도면끼리 더 가깝게, 다른 출원번호는 멀게 학습.

---

### 한계 3: KIPRIS URL 만료

```
imagePath에 저장된 KIPRIS URL은 세션 토큰 기반
→ 시간 경과 후 만료 → 엉뚱한 이미지 표시
```

**해결 (완료)**: `vectordb.py` 개선으로 로컬 이미지 절대경로 저장.

---

### 한계 4: 임베딩 비정규화

```
embeddings_v2.py 생성 시 F.normalize 미적용
→ 저장된 벡터 norm ≈ 11.x
→ 쿼리 벡터 norm = 1.0 (app.py에서 적용)
→ 스케일 불일치
```

**해결 (완료)**: `vectordb.py` 에서 저장 전 `F.normalize` 적용.

---

## 8. 의존성 설치

```bash
# requirements_app.txt 기반
pip install streamlit>=1.32.0
pip install chromadb>=0.4.0
pip install git+https://github.com/openai/CLIP.git
pip install torch>=1.13.0 torchvision>=0.14.0
pip install Pillow>=9.0.0
pip install rank-bm25>=0.2.2
pip install pandas>=1.5.0 numpy>=1.21.0
pip install opencv-python          # Canny Edge Detection

# 파인튜닝 추가 의존성
pip install ftfy regex tqdm
```

---

> 📌 **빠른 시작 요약**
>
> ```bash
> # 1. 의존성
> pip install -r design/requirements_app.txt
> pip install git+https://github.com/openai/CLIP.git opencv-python
>
> # 2. (이미 구축된 경우) 검색 앱 바로 실행
> streamlit run design/app.py
>
> # 3. DB 재구축이 필요한 경우
> python design/vectordb.py   # embeddings_v2 → chroma_db_v2
> ```
