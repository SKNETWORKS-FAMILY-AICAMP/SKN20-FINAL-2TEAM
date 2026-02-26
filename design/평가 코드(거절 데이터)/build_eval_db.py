"""
Step 1: 평가 전용 ChromaDB 구성
- 기존 DB(photo/chroma_db_v1, 'design' collection) 복사
- _similar 이미지들을 추가
"""
import chromadb
import torch
import clip
from PIL import Image
from pathlib import Path

# ── 설정 ──────────────────────────────────────────
EXISTING_DB_PATH    = "/Users/kangminji/__SKN20_FINAL/Backup2/FTO_ImgProject/data/sketch/chroma_db_v2"
EXISTING_COLLECTION = "design"
EVAL_DB_PATH        = "./chroma_eval_db"
EVAL_COLLECTION     = "eval_collection"
REJECTED_DIR        = "./rejected_images/"
# ─────────────────────────────────────────────────

device = (
    "cuda" if torch.cuda.is_available()
    else "mps" if torch.backends.mps.is_available()
    else "cpu"
)
print(f"Device: {device}")
clip_model, preprocess = clip.load("ViT-B/32", device=device)


def get_clip_embedding(image_path: str) -> list:
    image = preprocess(Image.open(image_path).convert("RGB")).unsqueeze(0).to(device)
    with torch.no_grad():
        emb = clip_model.encode_image(image)
        emb = emb / emb.norm(dim=-1, keepdim=True)
    return emb.cpu().numpy()[0].tolist()


def parse_similar_img_no(stem: str, app_num: str) -> str:
    """
    파일명 stem에서 img_no 추출.
    예) '3020140047287_img1_similar' -> 'img1'
        '3020200012215_img_1_similar' -> 'img_1'
    """
    prefix = f"{app_num}_"
    suffix = "_similar"
    middle = stem[len(prefix):]          # 'img1_similar' or 'img_1_similar'
    img_no = middle[: -len(suffix)]      # 'img1' or 'img_1'
    return img_no


def build_eval_db():
    # 기존 DB 복사
    src_client = chromadb.PersistentClient(path=EXISTING_DB_PATH)
    src_col    = src_client.get_collection(EXISTING_COLLECTION)
    total      = src_col.count()
    print(f"기존 DB 복사 중... ({total}건)")

    eval_client = chromadb.PersistentClient(path=EVAL_DB_PATH)
    eval_col    = eval_client.get_or_create_collection(
        name=EVAL_COLLECTION,
        metadata={"hnsw:space": "cosine"}
    )

    batch_size = 500
    offset = 0
    while offset < total:
        chunk = src_col.get(
            include=["embeddings", "metadatas"],
            limit=batch_size,
            offset=offset
        )
        if not chunk["ids"]:
            break
        eval_col.add(
            ids=chunk["ids"],
            embeddings=chunk["embeddings"],
            metadatas=chunk["metadatas"],
        )
        offset += batch_size
        print(f"  복사: {min(offset, total)}/{total}")

    # _similar 이미지 추가
    similar_paths = [
        p for p in Path(REJECTED_DIR).iterdir()
        if p.suffix in [".jpg", ".jpeg", ".png"] and "_similar" in p.stem
    ]
    print(f"\n_similar 이미지 추가 중... ({len(similar_paths)}건)")

    for img_path in sorted(similar_paths):
        stem    = img_path.stem                    # '3020140047287_img1_similar'
        app_num = stem.split("_")[0]               # '3020140047287'
        img_no  = parse_similar_img_no(stem, app_num)  # 'img1' or 'img_1'
        doc_id  = f"similar_{app_num}_{img_no}"

        if eval_col.get(ids=[doc_id])["ids"]:
            print(f"  [SKIP] 이미 존재: {doc_id}")
            continue

        try:
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
            print(f"  추가: {doc_id}")
        except Exception as e:
            print(f"  [ERROR] {img_path.name}: {e}")

    print(f"\n완료. 총 {eval_col.count()}건")


if __name__ == "__main__":
    build_eval_db()
