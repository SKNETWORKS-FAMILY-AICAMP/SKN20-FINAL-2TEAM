"""
Step 2: 평가 스크립트
- 평가 단위: 출원번호
- img1/2/3 중 하나라도 top-K 안에 _similar가 있으면 hit
"""
import chromadb
import torch
import clip
from PIL import Image
from pathlib import Path
import csv
from datetime import datetime
from collections import defaultdict

# ── 설정 ──────────────────────────────────────────
EXPERIMENT_NAME = "clip_vitb32_sketch_db"
EVAL_DB_PATH    = "./chroma_eval_db"
EVAL_COLLECTION = "eval_collection"
REJECTED_DIR    = "./rejected_images/"
TOP_K           = 100
K_LIST          = [5, 10, 20, 100]
OUTPUT_DIR      = "./eval_results"
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
    similar 파일명 stem에서 img_no 추출.
    예) '3020140047287_img1_similar' -> 'img1'
        '3020200012215_img_1_similar' -> 'img_1'
    """
    prefix = f"{app_num}_"
    suffix = "_similar"
    middle = stem[len(prefix):]
    return middle[: -len(suffix)]


def get_answer_ids(app_num: str) -> set:
    """파일 시스템에서 해당 출원번호의 _similar ID 목록 생성"""
    similar_files = [
        p for p in Path(REJECTED_DIR).iterdir()
        if p.suffix in [".jpg", ".jpeg", ".png"]
        and p.stem.startswith(f"{app_num}_")
        and "_similar" in p.stem
    ]
    ids = set()
    for f in similar_files:
        img_no = parse_similar_img_no(f.stem, app_num)
        ids.add(f"similar_{app_num}_{img_no}")
    return ids


def run_evaluation():
    out_dir = Path(OUTPUT_DIR) / EXPERIMENT_NAME
    out_dir.mkdir(parents=True, exist_ok=True)
    col = chromadb.PersistentClient(path=EVAL_DB_PATH).get_collection(EVAL_COLLECTION)
    print(f"평가 DB 총 {col.count()}건\n")

    # 쿼리 파일 수집 (_similar 제외)
    query_paths = [
        p for p in Path(REJECTED_DIR).iterdir()
        if p.suffix in [".jpg", ".jpeg", ".png"] and "_similar" not in p.stem
    ]

    # 출원번호별 그룹핑
    grouped = defaultdict(list)
    for qpath in query_paths:
        app_num = qpath.stem.split("_")[0]
        # img_no: 출원번호 제거 후 나머지 (예: 'img1', 'img2')
        img_no = qpath.stem[len(app_num) + 1:]
        grouped[app_num].append((img_no, qpath))

    detail_records  = []
    per_app_records = []

    for app_num, img_list in sorted(grouped.items()):
        answer_ids = get_answer_ids(app_num)
        if not answer_ids:
            print(f"[SKIP] _similar 없음: {app_num}")
            continue

        print(f"\n[{app_num}] 쿼리 {len(img_list)}개, 정답 {len(answer_ids)}개")
        print(f"  정답 IDs: {answer_ids}")

        app_hits = {k: False for k in K_LIST}

        for img_no, qpath in sorted(img_list):
            emb = get_clip_embedding(str(qpath))
            results = col.query(
                query_embeddings=[emb],
                n_results=TOP_K,
                include=["metadatas"]
            )
            retrieved_ids = results["ids"][0]

            first_hit_rank = None
            for rank, rid in enumerate(retrieved_ids, start=1):
                if rid in answer_ids:
                    first_hit_rank = rank
                    break

            for k in K_LIST:
                if first_hit_rank is not None and first_hit_rank <= k:
                    app_hits[k] = True

            print(f"  {img_no}: first_hit_rank={first_hit_rank}")

            detail_records.append({
                "application_number": app_num,
                "img_no":             img_no,
                "n_similar":          len(answer_ids),
                "first_hit_rank":     first_hit_rank if first_hit_rank is not None else "miss",
                **{f"img_hit@{k}": int(first_hit_rank is not None and first_hit_rank <= k)
                   for k in K_LIST}
            })

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

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    global_summary = {
        "experiment": EXPERIMENT_NAME,
        "n_apps":     n,
        "timestamp":  ts,
        **{f"HitRate@{k}": hit_rate(k) for k in K_LIST}
    }

    print("\n\n=== 평가 결과 (출원번호 단위) ===")
    for k, v in global_summary.items():
        print(f"  {k}: {v}")

    def save_csv(path, records):
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=records[0].keys())
            w.writeheader()
            w.writerows(records)

    save_csv(out_dir / f"{ts}_detail.csv",  detail_records)
    save_csv(out_dir / f"{ts}_per_app.csv", per_app_records)
    save_csv(out_dir / f"{ts}_summary.csv", [global_summary])
    print(f"\n저장 완료: {out_dir}/")


if __name__ == "__main__":
    run_evaluation()
