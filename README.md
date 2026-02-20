# 디자인 유사 이미지 검색 시스템 — 분석 및 개선 보고서

> 작성 기준: `chroma_db_train_v2` + `embeddings_reject_v2` + `images_reject_v2`  
> 검색 방식: Hybrid Retrieval (Dense CLIP + BM25)

---

## 목차

1. [프로젝트 구조](#1-프로젝트-구조)
2. [발견된 문제와 원인 분석](#2-발견된-문제와-원인-분석)
3. [수정 내용 (app.py / vectordb.py)](#3-수정-내용)
4. [DB 전체 유사도 분석](#4-db-전체-유사도-분석)
5. [CLIP 파인튜닝 전략](#5-clip-파인튜닝-전략)
6. [실행 방법](#6-실행-방법)

---

## 1. 프로젝트 구조

```
3차_테스트/
├── images_v2/              # 21,829개 특허 도면 이미지 (스케치 변환 완료)
├── embeddings_v2/          # 21,829개 CLIP 임베딩 JSON
├── chroma_db_v2/           # 21,829개 벡터 DB (학습용)
├── triplets.csv            # ← NEW: 파인튜닝용 41,792개 Triplet 쌍
└── 평가데이터/
    ├── images_reject_v2/   # 57개 거절 특허 이미지
    ├── embeddings_reject_v2/  # 57개 CLIP 임베딩 JSON
    └── chroma_db_train_v2/ # 57개 벡터 DB (평가용)

design/
├── app.py            # Streamlit 검색 앱
├── vectordb.py       # ChromaDB 구축 스크립트
├── embeddings_v2.py  # CLIP 임베딩 생성 스크립트
└── clip_finetune.py  # ← NEW: CLIP Triplet Loss 파인튜닝 스크립트
```

### 파일명 패턴 및 키 매핑

| 구분 | 패턴 예시 | 공통 키 추출 방법 |
|---|---|---|
| 이미지 파일 | `3020140047287-reject-0_11.jpg` | `rsplit('_', 1)[0]` → `3020140047287-reject-0` |
| 임베딩 ID | `3020140047287-reject-0-IMG-0` | `rsplit('-IMG-', 1)[0]` → `3020140047287-reject-0` |

> ✅ 21,829개 전수 100% 자동 매핑 가능 — 수동 작업 불필요

---

## 2. 발견된 문제와 원인 분석

### 문제 ① — Streamlit에서 DB에 없는 이미지가 표시됨

**원인: KIPRIS URL 토큰 만료**

`chroma_db_train_v2`의 `imagePath` 메타데이터에 KIPRIS API URL이 저장됨:

```
http://plus.kipris.or.kr/openapi/fileToss.jsp?arg=ad7a17eeeef6e4ea...
```

이 URL의 `arg` 파라미터는 **세션 기반 토큰**으로 시간이 지나면 만료됨.  
만료된 URL을 `st.image()`로 로드하면 KIPRIS가 **엉뚱한 이미지**를 반환.

**해결**: 메타데이터에 로컬 절대경로 저장 (`vectordb.py` 수정)

---

### 문제 ② — Dense 점수가 비정상적으로 높음 (0.7910)

예시: 출원번호 `3020170053571` vs `3020140047287`  
육안으로 완전히 다른 화장품 용기인데 Dense Score = **0.7910**

**원인 3가지:**

#### 원인 A — 임베딩 저장 시 F.normalize 미적용

```python
# embeddings_v2.py (저장 시) — 문제 코드
image_embedding = model.encode_image(image_tensor)
embedding_array = image_embedding.cpu().numpy()
# → norm ≈ 11.2 ~ 11.5  (비정규화 상태)

# app.py (검색 시) — 정규화 적용
emb = F.normalize(emb, dim=-1)
# → norm = 1.0  (정규화됨)
```

저장된 벡터와 쿼리 벡터의 스케일이 달라 비교가 부정확함.

#### 원인 B — 스케치 전처리 불일치 (핵심 원인)

```
저장된 임베딩 = Canny Edge Detection 변환 이미지 기반
쿼리 임베딩   = 원본 이미지 그대로 (전처리 없음)
```

`embeddings_v2.py`는 모든 이미지를 Canny Edge 스케치로 변환 후 임베딩.  
하지만 `app.py`의 쿼리는 원본 이미지를 그대로 임베딩 → 도메인 불일치.

> 확인 결과: 57개 임베딩 **전부** `is_converted_to_sketch: True`

#### 원인 C — CLIP ViT-B/32의 카테고리 수준 인식 한계

CLIP은 의미론적(semantic) 유사도를 측정함.  
같은 카테고리("화장품용기")끼리는 디자인이 달라도 임베딩 공간에서 가깝게 위치.

```
실제 측정값 (정규화 후 코사인 유사도):
  3571[0] vs 7287[0]: 0.7911  ← 앱에서 표시된 값과 정확히 일치
  '화장품용기' vs '포장용기' 카테고리 평균: 0.9509
```

---

### 문제 ③ — DB 전체가 높은 유사도로 뭉쳐 있음

57개 임베딩 간 pairwise 코사인 유사도:

```
구간별 분포:
  [0.60 ~ 0.70):  303쌍  (19.0%)
  [0.70 ~ 0.75):  300쌍  (18.8%)
  [0.75 ~ 0.80):  302쌍  (18.9%)
  [0.80 ~ 0.85):  381쌍  (23.9%)  ← 최빈 구간
  [0.85 ~ 0.90):  204쌍  (12.8%)

→ 전체 1,596쌍 중 79.3%가 이미 유사도 0.7 이상
→ 평균 유사도: 0.7720
```

**어떤 이미지를 넣어도 0.7대 결과가 나오는 것은 DB 자체의 구조적 문제.**

---

## 3. 수정 내용

### vectordb.py 수정사항

#### 변경 1: F.normalize로 unit vector 저장

```python
def normalize_embedding(raw_emb: list) -> list:
    tensor = torch.tensor(raw_emb, dtype=torch.float32).unsqueeze(0)
    normed = F.normalize(tensor, dim=-1)   # norm: 11.x → 1.0
    return normed.squeeze(0).tolist()
```

#### 변경 2: 로컬 이미지 경로 자동 매핑

```python
def build_img_dict(image_dir: str) -> dict:
    img_dict = {}
    for fname in os.listdir(image_dir):
        stem = fname.rsplit(".", 1)[0]     # 확장자 제거
        key  = stem.rsplit("_", 1)[0]      # 번호 제거 → 공통 키
        img_dict[key] = os.path.join(image_dir, fname)
    return img_dict

# 임베딩 ID → 공통 키
key = emb_id.rsplit("-IMG-", 1)[0]        # '3020140047287-reject-0-IMG-0' → '3020140047287-reject-0'
local_path = img_dict.get(key, "")        # 로컬 절대경로
```

#### 변경 3: ChromaDB 클린 재구축

```python
# 기존 컬렉션 삭제 후 재생성 (중복 ID 에러 방지)
chroma_client.delete_collection(name=COLLECTION_NAME)
image_collection = chroma_client.get_or_create_collection(...)
```

---

### app.py 수정사항

#### 변경 1: 쿼리 이미지에 스케치 전처리 추가

`embeddings_v2.py`와 **완전히 동일한 파라미터**로 Canny Edge Detection 적용:

```python
def convert_to_sketch_query(image: Image.Image) -> Image.Image:
    img_array  = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
    blurred    = cv2.GaussianBlur(img_array, (5, 5), 1.0)   # v2.py 동일
    edges      = cv2.Canny(blurred, 30, 120)                 # v2.py 동일
    edges      = cv2.dilate(edges, np.ones((2, 2)), iterations=1)
    sketch     = 255 - edges
    return Image.fromarray(cv2.cvtColor(sketch, cv2.COLOR_GRAY2RGB))

def get_image_embedding(image, model, preprocess):
    image = convert_to_sketch_query(image)   # ← 추가된 줄
    tensor = preprocess(image).unsqueeze(0).to(DEVICE)
    with torch.no_grad():
        emb = model.encode_image(tensor).float()
        emb = F.normalize(emb, dim=-1)
    return emb.cpu().numpy()[0]
```

#### 변경 2: 사이드바에 스케치 미리보기 추가

```python
show_sketch = st.checkbox("🖊️ 쿼리 스케치 변환 미리보기", value=False)
# 체크 시: 원본 이미지 / 스케치 변환 결과 나란히 표시
```

---

## 4. DB 전체 유사도 분석

### 21,829개 데이터 카테고리 분포

| 카테고리 | 개수 | 비율 |
|---|---|---|
| 화장품 용기 (표기 통일 시) | ~6,000+ | ~27% |
| 포장용 용기 | 3,135 | 14.4% |
| 식품포장용 용기 | 1,832 | 8.4% |
| 기타 용기류 | ~10,000 | ~46% |
| **비용기 계열 전체** | **82** | **0.4%** |

> ⚠️ **99.6%가 용기/포장 계열** → 도메인이 극도로 단일

### CLIP 파인튜닝 가능 여부

| 조건 | 결과 |
|---|---|
| 57개 데이터로 파인튜닝 | ❌ 불가 — 심각한 과적합 |
| 21,829개 + 전부 용기류 | ⚠️ 제한적 — 카테고리 내 미세 차이 학습 시도 가능 |
| 21,829개 + Triplet 구조 | ✅ **가능** — 같은 출원번호 도면끼리 가깝게 학습 |

---

## 5. CLIP 파인튜닝 전략

### Triplet 데이터 자동 구성

```
같은 출원번호 내 도면 = Positive 쌍 (같은 디자인, 다른 뷰)
다른 출원번호 도면    = Negative 쌍

총 7,401개 출원번호 × 평균 3장 도면
→ 41,792개 Triplet 자동 생성 (triplets.csv)
  - hard negative: 20,318개 (같은 물품명, 다른 디자인)  ← 세밀한 차이 학습
  - easy negative: 21,474개 (다른 물품명, 다른 디자인)  ← 기본 분리 학습
```

### 학습 설계 (clip_finetune.py)

```
모델:   CLIP ViT-B/32
동결:   앞단 Visual Encoder 전체 + Text Encoder 전체
학습:   Visual Encoder 마지막 4개 Transformer Block + Projection Layer
        (전체 파라미터의 약 14%만 업데이트)

Loss:   Triplet Margin Loss (margin=0.2)
        목표: d(anchor, positive) + 0.2 < d(anchor, negative)

Optimizer: AdamW (lr=1e-5, weight_decay=1e-4)
Scheduler: ReduceLROnPlateau (patience=3)
Batch:     32
Epochs:    30
```

### 학습 모니터링 지표

| 지표 | 의미 | 목표 방향 |
|---|---|---|
| `train_loss` | 학습 Triplet Loss | ↓ 감소 |
| `val_loss` | 검증 Triplet Loss | ↓ 감소 |
| `d_pos` | anchor ↔ positive 평균 거리 | ↓ 감소 |
| `d_neg` | anchor ↔ negative 평균 거리 | ↑ 증가 |
| `gap` = d_neg - d_pos | 분리 정도 | ↑ **클수록 성공** |

---

## 6. 실행 방법

### Step 1: ChromaDB 재구축 (vectordb.py 수정 반영)

```bash
cd /Users/kangminji/__SKN20_FINAL/데이터셋만들기/design
python vectordb.py
# 출력 예시:
# ✅ 이미지 딕셔너리 구축 완료: 57개
# ✅ [1] 3020140047287-reject-0-IMG-0 → 3020140047287-reject-0_11.jpg
# 📦 최종 컬렉션 크기: 57개
```

### Step 2: Streamlit 앱 실행

```bash
streamlit run app.py
# 사이드바 → "🖊️ 쿼리 스케치 변환 미리보기" 체크로 전처리 확인 가능
```

### Step 3 (선택): CLIP 파인튜닝

```bash
# 의존성 설치
pip install ftfy regex tqdm

# 학습 시작 (GPU 권장, 약 2~4시간)
python clip_finetune.py

# 결과물
# clip_finetuned/clip_finetuned_best.pt   ← 최적 모델
# clip_finetuned/training_log.csv         ← 에폭별 loss/gap 추이
```

---

## 개선 우선순위 정리

| 우선순위 | 작업 | 난이도 | 효과 |
|---|---|---|---|
| ⭐⭐⭐ | vectordb.py 재실행 (F.normalize + 로컬경로) | 낮음 | 즉시 이미지 표시 정상화 |
| ⭐⭐⭐ | app.py 스케치 전처리 통일 | 낮음 | 쿼리-DB 도메인 일치 |
| ⭐⭐ | CLIP Triplet Loss 파인튜닝 | 중간 | 같은 출원번호 도면 간 거리 개선 |
| ⭐ | 비용기 카테고리 데이터 추가 | 높음 | 카테고리 간 상대적 차별화 |

---

> 📌 **핵심 결론**  
> 현재 DB의 근본적 한계는 99.6%가 용기류라는 **데이터 도메인 단일성**입니다.  
> 단기적으로는 전처리 통일(스케치) + 정규화(F.normalize)로 일관성을 확보하고,  
> 중기적으로 Triplet Loss 파인튜닝으로 **같은 디자인의 다른 뷰는 가깝게, 다른 디자인은 멀게** 만드는 방향이 현실적입니다.
