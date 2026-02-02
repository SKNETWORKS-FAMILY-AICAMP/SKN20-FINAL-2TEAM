# OpenCLIP Vector Similarity

디자인 특허 JSON 데이터에서 이미지와 텍스트를 추출하여 OpenCLIP으로 동일 벡터 공간에 임베딩하고, 유사도를 계산하는 파이프라인입니다.

## 주요 기능

- JSON 메타데이터에서 이미지 URL 추출 및 다운로드
- 텍스트 문서 구성 (제품명, 분류코드, 출원인, 디자인 요점/설명)
- OpenCLIP ViT-L/14로 이미지/텍스트 임베딩 (같은 벡터 공간)
- 배치 처리 지원 (기본 batch_size=32)
- 이미지-텍스트 cosine similarity 계산
- 결과 저장: JSONL, NPZ, ChromaDB (선택)

## 설치

```bash
pip install torch open_clip_torch pillow numpy requests tqdm

# ChromaDB 사용 시
pip install chromadb
```

## 사용법

### 기본 실행

```bash
python openclip_vector_similarity.py
```

### 옵션 지정

```bash
python openclip_vector_similarity.py \
    --input_dir "09-01/2000년도/2000_json" \
    --output_dir "09-01/2000년도" \
    --batch_size 32 \
    --device cuda
```

### 전체 옵션

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--input_dir` | `09-01/2000년도/2000_json` | 입력 JSON 폴더 경로 |
| `--output_dir` | `09-01/2000년도` | 출력 폴더 경로 |
| `--model_name` | `ViT-L-14` | OpenCLIP 모델명 |
| `--pretrained` | `laion2b_s32b_b82k` | 사전학습 가중치 |
| `--device` | 자동 감지 | `cuda`, `mps`, `cpu` |
| `--batch_size` | `32` | 배치 크기 |
| `--no_download` | `False` | 이미지 다운로드 스킵 |
| `--build_chroma` | `False` | ChromaDB 저장 활성화 |
| `--collection` | `openclip_same_space` | ChromaDB 컬렉션명 |

## 입력 JSON 구조

```json
{
  "design_id": "D001",
  "applicationNumber": "30-2000-0001234",
  "registrationNumber": "30-0001234",
  "image": {
    "image_id": "img_001",
    "imageName": "design.jpg",
    "imagePath": "https://example.com/images/design.jpg"
  },
  "meta": {
    "articleName": "휴대폰 케이스",
    "LCCode": "14-03",
    "applicantName": "홍길동"
  },
  "creative": {
    "designSummary": "곡선형 모서리 처리",
    "designDescription": "인체공학적 그립감을 위한 디자인"
  }
}
```

## 출력 파일

### 1. `openclip_metadata.jsonl`

각 레코드별 메타데이터와 유사도 점수:

```json
{
  "id": "D001::img_001",
  "document": "제품명: 휴대폰 케이스\nLocarno: 14-03\n...",
  "metadata": {
    "design_id": "D001",
    "applicationNumber": "30-2000-0001234",
    "articleName": "휴대폰 케이스",
    "LCCode": "14-03",
    "image_id": "img_001",
    "image_url": "https://...",
    "image_local_path": "09-01/2000년도/img/D001__img_001.jpg",
    "modality": "image+text"
  },
  "image_text_cosine": 0.2847
}
```

### 2. `openclip_embeddings.npz`

NumPy 압축 파일:

```python
import numpy as np

data = np.load("openclip_embeddings.npz")
print(data["ids"])              # 레코드 ID 배열
print(data["image_embeddings"]) # (N, 768) 이미지 벡터
print(data["text_embeddings"])  # (N, 768) 텍스트 벡터
print(data["image_text_cosine"]) # (N,) 유사도 점수
```

### 3. `img/` 폴더

다운로드된 이미지 파일들:

```
img/
├── D001__img_001.jpg
├── D002__img_002.jpg
└── ...
```

### 4. `chroma_openclip/` (선택)

ChromaDB 영구 저장소. `--build_chroma` 플래그 사용 시 생성:

```python
import chromadb

client = chromadb.PersistentClient(path="09-01/2000년도/chroma_openclip")
col = client.get_collection("openclip_same_space")

# 이미지로 유사 텍스트 검색
results = col.query(
    query_embeddings=[image_vector],
    where={"modality": "text"},
    n_results=10
)

# 텍스트로 유사 이미지 검색
results = col.query(
    query_embeddings=[text_vector],
    where={"modality": "image"},
    n_results=10
)
```

## 임베딩 활용 예시

### 이미지-텍스트 유사도 분석

```python
import numpy as np

data = np.load("openclip_embeddings.npz")
sims = data["image_text_cosine"]

print(f"평균 유사도: {sims.mean():.4f}")
print(f"최고 유사도: {sims.max():.4f}")
print(f"최저 유사도: {sims.min():.4f}")
```

### 이미지 간 유사도 검색

```python
import numpy as np

data = np.load("openclip_embeddings.npz")
img_embs = data["image_embeddings"]  # 이미 L2 정규화됨

# 첫 번째 이미지와 나머지 이미지 간 유사도
query = img_embs[0]
sims = img_embs @ query  # cosine similarity

top_k = np.argsort(sims)[::-1][:10]
print("유사한 이미지 인덱스:", top_k)
```

### 텍스트 쿼리로 이미지 검색

```python
import open_clip
import numpy as np

# 모델 로드
model, _, preprocess = open_clip.create_model_and_transforms("ViT-L-14", pretrained="laion2b_s32b_b82k")
tokenizer = open_clip.get_tokenizer("ViT-L-14")

# 쿼리 임베딩
query_text = "곡선형 휴대폰 케이스"
tokens = tokenizer([query_text])
query_emb = model.encode_text(tokens)
query_emb = query_emb / query_emb.norm(dim=-1, keepdim=True)
query_emb = query_emb.detach().numpy()

# 검색
data = np.load("openclip_embeddings.npz")
img_embs = data["image_embeddings"]
sims = img_embs @ query_emb.T

top_k = np.argsort(sims.flatten())[::-1][:10]
print("검색 결과:", data["ids"][top_k])
```

## 디렉토리 구조

```
09-01/2000년도/
├── 2000_json/                    # 입력: JSON 파일들
│   ├── design_001.json
│   ├── design_002.json
│   └── ...
├── img/                          # 출력: 다운로드된 이미지
│   ├── D001__img_001.jpg
│   └── ...
├── openclip_metadata.jsonl       # 출력: 메타데이터
├── openclip_embeddings.npz       # 출력: 임베딩 벡터
└── chroma_openclip/              # 출력: ChromaDB (선택)
```

## 성능 팁

- **GPU 사용**: `--device cuda`로 GPU 가속 활성화
- **배치 크기 조절**: VRAM에 따라 `--batch_size` 조절 (8GB VRAM → 32~64 권장)
- **이미지 재사용**: `--no_download`로 기존 다운로드 이미지 재사용

## 라이선스

MIT License