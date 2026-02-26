# 평가 로직 구축 작업 지시서 (최종)

## 환경 전제
- 벡터 DB: **ChromaDB** (기존 DB에는 일반 특허 이미지만 있음)
- 임베딩 모델: **CLIP (ViT-B/32)**
- 거절 데이터 파일명 규칙:
  - 쿼리(출원 디자인): `3020140047287_img1.jpg`, `3020140047287_img2.jpg`, ...
  - 정답(선행 디자인): `3020140047287_img1_similar.jpg`, `3020140047287_img2_similar.jpg`, ...
  - ⚠️ 정답이 2개인 경우도 있음: `3020140047289_img1_similar.jpg`, `3020140047289_img1_similar2.jpg`
    → `_similar`, `_similar2`, ... 모두 정답으로 처리 (둘 중 하나라도 hit이면 hit)
- **평가 단위: 출원번호** — img1/2/3 중 하나라도 top-K 안에 _similar가 있으면 **hit**
- `_similar` 이미지는 현재 DB에 없음 → 평가 전용 DB에 추가 필요

---

## 파일 구조

```
rejected_designs/
├── 3020140047287_img1.jpg            ← 쿼리
├── 3020140047287_img2.jpg            ← 쿼리
├── 3020140047287_img3.jpg            ← 쿼리
├── 3020140047287_img1_similar.jpg    ← 정답 (DB에 추가될 것)
├── 3020140047287_img2_similar.jpg    ← 정답 (DB에 추가될 것)
├── 3020140047287_img3_similar.jpg    ← 정답 (DB에 추가될 것)
├── 3020140047289_img1.jpg            ← 쿼리
├── 3020140047289_img1_similar.jpg    ← 정답 1 (DB에 추가될 것)
├── 3020140047289_img1_similar2.jpg   ← 정답 2 (DB에 추가될 것) ← 이런 케이스 1개 있음
...

eval_results/
├── clip_vitb32_baseline_20250223_143000_detail.csv
├── clip_vitb32_baseline_20250223_143000_per_app.csv
└── clip_vitb32_baseline_20250223_143000_summary.csv
```

---

## Step 1. 평가 전용 ChromaDB 구성

기존 DB를 복사하고, `_similar` / `_similar2` 등 모든 정답 이미지들을 추가한다.

**doc_id 규칙**: `similar_{app_num}_{img_no}_{suffix}`
- 예: `similar_3020140047287_img1_similar`
- 예: `similar_3020140047289_img1_similar2`

```python
# build_eval_db.py
import chromadb
import torch
import clip
from PIL import Image
from pathlib import Path

# ── 설정 ──────────────────────────────────────────
EXISTING_DB_PATH    = "./chroma_db"
EXISTING_COLLECTION = "design"
EVAL_DB_PATH        = "./chroma_eval_db"
EVAL_COLLECTION     = "eval_collection"
REJECTED_DIR        = "./rejected_designs/"
# ─────────────────────────────────────────────────

device = "cuda" if torch.cuda.is_available() else "cpu"
clip_model, preprocess = clip.load("ViT-B/32", device=device)

def get_clip_embedding(image_path: str) -> list:
    image = preprocess(Image.open(image_path).convert("RGB")).unsqueeze(0).to(device)
    with torch.no_grad():
        emb = clip_model.encode_image(image)
        emb = emb / emb.norm(dim=-1, keepdim=True)
    return emb.cpu().numpy()[0].tolist()

def build_eval_db():
    # 기존 DB 복사
    src_col  = chromadb.PersistentClient(path=EXISTING_DB_PATH).get_collection(EXISTING_COLLECTION)
    all_data = src_col.get(include=["embeddings", "metadatas"])

    eval_col = chromadb.PersistentClient(path=EVAL_DB_PATH).get_or_create_collection(
        name=EVAL_COLLECTION,
        metadata={"hnsw:space": "cosine"}
    )

    print(f"기존 DB 복사 중... ({len(all_data['ids'])}건)")
    batch_size = 500
    for i in range(0, len(all_data["ids"]), batch_size):
        eval_col.add(
            ids=all_data["ids"][i:i+batch_size],
            embeddings=all_data["embeddings"][i:i+batch_size],
            metadatas=all_data["metadatas"][i:i+batch_size],
        )

    # _similar* 이미지 추가 (_similar, _similar2 등 모두 포함)
    similar_paths = [
        p for p in Path(REJECTED_DIR).iterdir()
        if p.suffix in [".jpg", ".png"] and "_similar" in p.stem
    ]
    print(f"_similar 이미지 추가 중... ({len(similar_paths)}건)")

    for img_path in similar_paths:
        # 파일명 파싱
        # 예: 3020140047287_img1_similar   → parts = ['3020140047287', 'img1', 'similar']
        # 예: 3020140047289_img1_similar2  → parts = ['3020140047289', 'img1', 'similar2']
        parts = img_path.stem.split("_")
        app_num = parts[0]
        img_no  = parts[1]
        suffix  = "_".join(parts[2:])  # 'similar' or 'similar2'
        doc_id  = f"similar_{app_num}_{img_no}_{suffix}"

        if eval_col.get(ids=[doc_id])["ids"]:
            continue

        emb = get_clip_embedding(str(img_path))
        eval_col.add(
            ids=[doc_id],
            embeddings=[emb],
            metadatas=[{
                "design_id":         doc_id,
                "applicationNumber": app_num,
                "imageNumber":       img_no,
                "admstStat":         "similar",
                "imagePath":         str(img_path),
                "LCCode":            "",
                "articleName":       "",
                "designSummary":     ""
            }]
        )

    print(f"완료. 총 {eval_col.count()}건")

if __name__ == "__main__":
    build_eval_db()
```

---

## Step 2. 평가 스크립트

**평가 단위 = 출원번호** → img1/2/3 중 하나라도 top-K 안에 _similar 있으면 hit

```python
# evaluate.py
import chromadb
import torch
import clip
from PIL import Image
from pathlib import Path
import csv
from datetime import datetime
from collections import defaultdict

# ── 설정 ──────────────────────────────────────────
EXPERIMENT_NAME = "clip_vitb32_baseline"   # 실험마다 바꾸기
EVAL_DB_PATH    = "./chroma_eval_db"
EVAL_COLLECTION = "eval_collection"
REJECTED_DIR    = "./rejected_designs/"
TOP_K           = 100
K_LIST          = [5, 10, 20, 100]
OUTPUT_DIR      = "./eval_results"
# ─────────────────────────────────────────────────

device = "cuda" if torch.cuda.is_available() else "cpu"
clip_model, preprocess = clip.load("ViT-B/32", device=device)

def get_clip_embedding(image_path: str) -> list:
    image = preprocess(Image.open(image_path).convert("RGB")).unsqueeze(0).to(device)
    with torch.no_grad():
        emb = clip_model.encode_image(image)
        emb = emb / emb.norm(dim=-1, keepdim=True)
    return emb.cpu().numpy()[0].tolist()

def get_answer_ids(app_num: str) -> set[str]:
    """파일 시스템에서 해당 출원번호의 _similar* ID 목록 생성
    - _similar, _similar2 등 모두 포함
    - doc_id 규칙: similar_{app_num}_{img_no}_{suffix}
    """
    similar_files = [
        p for p in Path(REJECTED_DIR).iterdir()
        if p.suffix in [".jpg", ".png"]
        and p.stem.startswith(f"{app_num}_")
        and "_similar" in p.stem
    ]
    ids = set()
    for f in similar_files:
        parts = f.stem.split("_")
        img_no = parts[1]
        suffix = "_".join(parts[2:])  # 'similar' or 'similar2'
        ids.add(f"similar_{app_num}_{img_no}_{suffix}")
    return ids

def run_evaluation():
    Path(OUTPUT_DIR).mkdir(exist_ok=True)
    col = chromadb.PersistentClient(path=EVAL_DB_PATH).get_collection(EVAL_COLLECTION)

    # 쿼리만 수집 (_similar 제외)
    query_paths = [
        p for p in list(Path(REJECTED_DIR).glob("*.jpg")) + list(Path(REJECTED_DIR).glob("*.png"))
        if "_similar" not in p.stem
    ]

    # 출원번호별 그룹핑
    grouped = defaultdict(list)
    for qpath in query_paths:
        parts = qpath.stem.split("_")
        grouped[parts[0]].append((parts[1], qpath))  # (img_no, path)

    detail_records  = []
    per_app_records = []

    for app_num, img_list in sorted(grouped.items()):
        answer_ids = get_answer_ids(app_num)
        if not answer_ids:
            print(f"[SKIP] _similar 없음: {app_num}")
            continue

        app_hits = {k: False for k in K_LIST}

        for img_no, qpath in sorted(img_list):
            emb = get_clip_embedding(str(qpath))
            results = col.query(query_embeddings=[emb], n_results=TOP_K, include=["metadatas"])
            retrieved_ids = results["ids"][0]

            first_hit_rank = None
            for rank, rid in enumerate(retrieved_ids, start=1):
                if rid in answer_ids:  # answer_ids가 2개여도 동일하게 동작
                    first_hit_rank = rank
                    break

            for k in K_LIST:
                if first_hit_rank is not None and first_hit_rank <= k:
                    app_hits[k] = True

            detail_records.append({
                "application_number": app_num,
                "img_no":             img_no,
                "n_similar":          len(answer_ids),
                "first_hit_rank":     first_hit_rank if first_hit_rank else "miss",
                **{f"img_hit@{k}": int(first_hit_rank is not None and first_hit_rank <= k)
                   for k in K_LIST}
            })
            print(f"  {app_num} {img_no}: rank={first_hit_rank}")

        per_app_records.append({
            "application_number": app_num,
            "n_queries":          len(img_list),
            "n_similar":          len(answer_ids),
            **{f"app_hit@{k}": int(app_hits[k]) for k in K_LIST}
        })

    if not per_app_records:
        print("평가할 데이터 없음")
        return

    n = len(per_app_records)
    def hit_rate(k):
        return round(sum(r[f"app_hit@{k}"] for r in per_app_records) / n, 4)

    global_summary = {
        "experiment":  EXPERIMENT_NAME,
        "n_apps":      n,
        "timestamp":   datetime.now().strftime("%Y%m%d_%H%M%S"),
        **{f"HitRate@{k}": hit_rate(k) for k in K_LIST}
    }

    print("\n=== 평가 결과 (출원번호 단위) ===")
    for k, v in global_summary.items():
        print(f"  {k}: {v}")

    ts = global_summary["timestamp"]
    def save_csv(path, records):
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=records[0].keys())
            w.writeheader(); w.writerows(records)

    save_csv(f"{OUTPUT_DIR}/{EXPERIMENT_NAME}_{ts}_detail.csv",  detail_records)
    save_csv(f"{OUTPUT_DIR}/{EXPERIMENT_NAME}_{ts}_per_app.csv", per_app_records)
    save_csv(f"{OUTPUT_DIR}/{EXPERIMENT_NAME}_{ts}_summary.csv", [global_summary])
    print(f"저장 완료: {OUTPUT_DIR}/")

if __name__ == "__main__":
    run_evaluation()
```

---

## Step 3. CSV 3종 구조

### ① detail.csv — 이미지별 상세
| application_number | img_no | n_similar | first_hit_rank | img_hit@5 | img_hit@10 | img_hit@20 | img_hit@100 |
|---|---|---|---|---|---|---|---|
| 3020140047287 | img1 | 1 | 4 | 1 | 1 | 1 | 1 |
| 3020140047287 | img2 | 1 | 12 | 0 | 0 | 1 | 1 |
| 3020140047287 | img3 | 1 | miss | 0 | 0 | 0 | 0 |
| 3020140047289 | img1 | 2 | 7 | 0 | 1 | 1 | 1 |

> `n_similar=2` → `_similar` + `_similar2` 둘 다 정답인 케이스

### ② per_app.csv — 출원번호별 요약
| application_number | n_queries | n_similar | app_hit@5 | app_hit@10 | app_hit@20 | app_hit@100 |
|---|---|---|---|---|---|---|
| 3020140047287 | 3 | 1 | **1** | 1 | 1 | 1 |
| 3020140047288 | 2 | 1 | 0 | 0 | 0 | **1** |
| 3020140047289 | 1 | 2 | 0 | **1** | 1 | 1 |

> `app_hit@K = 1` ← img1/2/3 중 하나라도 해당 K 안에 hit이면

### ③ summary.csv — 전체 지표
| experiment | n_apps | HitRate@5 | HitRate@10 | HitRate@20 | HitRate@100 | timestamp |
|---|---|---|---|---|---|---|
| clip_vitb32_baseline | 30 | 0.50 | 0.63 | 0.77 | 0.93 | 20250223_143000 |

---

## 실행 순서

```bash
# 1. 평가 전용 DB 구성 (최초 1회)
python build_eval_db.py

# 2. 평가 실행
python evaluate.py

# 3. 결과 확인
ls eval_results/
```

---

## ⚠️ 실행 전 파일명 파싱 확인

출원번호나 img 번호 형식이 예상과 다를 수 있으니 먼저 확인:

```python
from pathlib import Path
for p in sorted(Path("./rejected_designs").iterdir())[:10]:
    if p.suffix in [".jpg", ".png"]:
        print(p.stem, "→", p.stem.split("_"))
# 기대 출력:
# 3020140047287_img1         → ['3020140047287', 'img1']
# 3020140047287_img1_similar → ['3020140047287', 'img1', 'similar']
# 3020140047289_img1_similar2 → ['3020140047289', 'img1', 'similar2']
```