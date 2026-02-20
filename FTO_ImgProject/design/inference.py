"""
inference.py
============
파인튜닝된 CLIP 모델로 전체 이미지를 재임베딩하고 ChromaDB를 재구축.

실행 순서:
  1. clip_finetune.py  →  clip_finetuned_best.pt 생성
  2. inference.py      →  새 임베딩 JSON + ChromaDB 재구축   ← 이 파일
  3. app.py            →  파인튜닝 모델로 검색

처리 흐름:
  파인튜닝 모델 로드
      ↓
  images_reject_v2/ 전체 이미지 순회
      ↓
  Canny 스케치 전처리 (embeddings_v2.py 와 동일)
      ↓
  파인튜닝 모델로 임베딩 생성 + F.normalize
      ↓
  embeddings_reject_finetuned/ 에 JSON 저장
      ↓
  chroma_db_finetuned/ 에 ChromaDB 재구축
"""

import os
import json
import csv
import sqlite3
import cv2
import numpy as np
import torch
import torch.nn.functional as F
import chromadb
import clip
from PIL import Image
from pathlib import Path
from datetime import datetime

PROJECT_ROOT         = Path(__file__).resolve().parent.parent
from collections import defaultdict

# ─────────────────────────────────────────────
# 0. 경로 설정
# ─────────────────────────────────────────────
FINETUNED_MODEL_PATH = str(PROJECT_ROOT / "train/checkpoints/best_model.pt")

# 원본 임베딩 소스 (메타데이터 참조용)
ORIGINAL_EMB_DIR     = str(PROJECT_ROOT / "data/evaldata/embeddings_reject_v2")
IMAGE_DIR            = str(PROJECT_ROOT / "data/evaldata/images_reject_v2")

# 새로운 출력 경로
NEW_EMB_DIR          = str(PROJECT_ROOT / "data/evaldata/embeddings_reject_finetuned")
NEW_CHROMA_PATH      = str(PROJECT_ROOT / "data/evaldata/chroma_db_finetuned")
COLLECTION_NAME      = "design"
CLIP_MODEL_NAME      = "ViT-B/32"
ERROR_LOG            = str(PROJECT_ROOT / "data/evaldata/inference_error_log.txt")

Path(NEW_EMB_DIR).mkdir(parents=True, exist_ok=True)

DEVICE = (
    "cuda" if torch.cuda.is_available() else
    "mps"  if torch.backends.mps.is_available() else
    "cpu"
)
print(f"Device: {DEVICE}")


# ─────────────────────────────────────────────
# 1. 파인튜닝 모델 로드
#    - 원본 CLIP 구조 그대로 불러온 뒤
#    - 저장된 state_dict를 덮어씀
# ─────────────────────────────────────────────
def load_finetuned_clip(model_path: str):
    """
    clip_finetune.py 가 저장한 .pt 파일에서 모델 복원.

    저장 구조:
      {
        "epoch": int,
        "model_state_dict": OrderedDict,
        "val_loss": float,
        "margin_gap": float
      }
    """
    print(f"\n[1] 파인튜닝 모델 로드: {model_path}")

    # 원본 CLIP 구조 초기화
    model, preprocess = clip.load(CLIP_MODEL_NAME, device=DEVICE)
    model = model.float()

    # 저장된 가중치 로드
    checkpoint = torch.load(model_path, map_location=DEVICE)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()

    saved_epoch = checkpoint.get("epoch", "?")
    val_loss    = checkpoint.get("val_loss", "?")
    margin_gap  = checkpoint.get("margin_gap", "?")

    print(f"  ✅ 로드 완료")
    print(f"     저장 에폭:    {saved_epoch}")
    print(f"     Val Loss:     {val_loss:.4f}" if isinstance(val_loss, float) else f"     Val Loss: {val_loss}")
    print(f"     Margin Gap:   {margin_gap:.4f}" if isinstance(margin_gap, float) else f"     Margin Gap: {margin_gap}")

    return model, preprocess


# ─────────────────────────────────────────────
# 2. 스케치 전처리 (embeddings_v2.py 와 완전히 동일한 파라미터)
# ─────────────────────────────────────────────
def convert_to_sketch(image: Image.Image) -> Image.Image:
    """
    Canny Edge Detection 으로 스케치 변환.
    embeddings_v2.py / app.py 와 파라미터 통일:
      GaussianBlur(5, 5, 1.0) / Canny(30, 120) / dilate(2x2, 1회)
    """
    img_array  = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
    blurred    = cv2.GaussianBlur(img_array, (5, 5), 1.0)
    edges      = cv2.Canny(blurred, 30, 120)
    edges      = cv2.dilate(edges, np.ones((2, 2), np.uint8), iterations=1)
    sketch     = 255 - edges
    sketch_rgb = cv2.cvtColor(sketch, cv2.COLOR_GRAY2RGB)
    return Image.fromarray(sketch_rgb)


# ─────────────────────────────────────────────
# 3. 이미지 → 정규화된 임베딩
# ─────────────────────────────────────────────
def get_embedding(image_path: str, model, preprocess) -> np.ndarray:
    """
    로컬 이미지 파일 → 스케치 변환 → 파인튜닝 모델 임베딩 → F.normalize
    """
    image  = Image.open(image_path).convert("RGB")
    image  = convert_to_sketch(image)                          # 스케치 전처리
    tensor = preprocess(image).unsqueeze(0).to(DEVICE)
    with torch.no_grad():
        emb = model.encode_image(tensor).float()
        emb = F.normalize(emb, dim=-1)                         # unit vector
    return emb.cpu().numpy()[0]


# ─────────────────────────────────────────────
# 4. 이미지 ↔ 원본 메타데이터 매핑 구축
# ─────────────────────────────────────────────
def build_mappings():
    """
    images_reject_v2/ 파일 목록과
    embeddings_reject_v2/ JSON의 메타데이터를 연결.

    공통 키: '{applicationNum}-reject-{imgIdx}'
      이미지 파일:  3020140047287-reject-0_11.jpg  → key: '3020140047287-reject-0'
      임베딩 ID:   3020140047287-reject-0-IMG-0   → key: '3020140047287-reject-0'
    """
    # 이미지 파일 딕셔너리
    img_dict = {}
    for fname in os.listdir(IMAGE_DIR):
        if fname.startswith("."):
            continue
        stem = fname.rsplit(".", 1)[0]
        key  = stem.rsplit("_", 1)[0]
        img_dict[key] = os.path.join(IMAGE_DIR, fname)

    # 원본 임베딩 메타데이터 딕셔너리
    meta_dict = {}
    for fname in os.listdir(ORIGINAL_EMB_DIR):
        if not fname.endswith("_embedding.json"):
            continue
        with open(os.path.join(ORIGINAL_EMB_DIR, fname), encoding="utf-8") as f:
            data = json.load(f)
        emb_id = data.get("id", "")
        key    = emb_id.rsplit("-IMG-", 1)[0]
        meta_dict[key] = {
            "id":       emb_id,
            "metadata": data.get("metadata", {}),
        }

    return img_dict, meta_dict


# ─────────────────────────────────────────────
# 5. 전체 재임베딩 + JSON 저장
# ─────────────────────────────────────────────
def reembed_all(model, preprocess, img_dict, meta_dict):
    """
    img_dict 의 모든 이미지를 파인튜닝 모델로 재임베딩.
    NEW_EMB_DIR 에 JSON 저장.
    """
    print(f"\n[2] 전체 재임베딩 시작 ({len(img_dict)}개)...")

    results      = []   # ChromaDB add 용
    error_logs   = []
    success, fail = 0, 0

    for key, img_path in sorted(img_dict.items()):
        if key not in meta_dict:
            error_logs.append(f"메타데이터 없음: {key}\n")
            fail += 1
            continue

        emb_info = meta_dict[key]
        emb_id   = emb_info["id"]
        meta     = emb_info["metadata"]

        try:
            emb = get_embedding(img_path, model, preprocess)

            # JSON 저장
            out_data = {
                "id":        emb_id,
                "embedding": emb.tolist(),
                "metadata":  {
                    **meta,
                    "imagePath":          img_path,       # ← 로컬 경로로 교체
                    "finetuned_model":    FINETUNED_MODEL_PATH,
                    "reembedded_at":      datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            }
            json_name = emb_id.replace("-", "_") + "_ft_embedding.json"
            json_path = os.path.join(NEW_EMB_DIR, json_name)
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(out_data, f, indent=2, ensure_ascii=False)

            results.append(out_data)
            success += 1
            print(f"  ✓ [{success}] {emb_id}")

        except Exception as e:
            msg = f"실패: {emb_id} | {str(e)}\n"
            print(f"  ❌ {msg.strip()}")
            error_logs.append(msg)
            fail += 1

    print(f"\n  완료: 성공 {success}개 / 실패 {fail}개")

    if error_logs:
        with open(ERROR_LOG, "w", encoding="utf-8") as f:
            f.writelines(error_logs)
        print(f"  에러 로그: {ERROR_LOG}")

    return results


# ─────────────────────────────────────────────
# 6. ChromaDB 재구축
# ─────────────────────────────────────────────
def rebuild_chromadb(results: list):
    """
    재임베딩 결과로 NEW_CHROMA_PATH 에 ChromaDB 재구축.
    """
    print(f"\n[3] ChromaDB 재구축: {NEW_CHROMA_PATH}")

    client = chromadb.PersistentClient(path=NEW_CHROMA_PATH)

    # 기존 컬렉션 삭제 (클린 재구축)
    try:
        client.delete_collection(name=COLLECTION_NAME)
        print(f"  🗑️  기존 컬렉션 삭제")
    except Exception:
        print(f"  ℹ️  기존 컬렉션 없음 — 새로 생성")

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )

    for item in results:
        meta = item["metadata"]
        collection.add(
            ids=[item["id"]],
            embeddings=[item["embedding"]],
            metadatas=[{
                "design_id":         meta.get("design_id", ""),
                "applicationNumber": meta.get("applicationNumber", ""),
                "LCCode":            meta.get("LCCode", ""),
                "articleName":       meta.get("articleName", ""),
                "imageNumber":       str(meta.get("imageNumber", "")),
                "admstStat":         meta.get("status", {}).get("admstStat", "")
                                     if isinstance(meta.get("status"), dict) else "",
                "imagePath":         meta.get("imagePath", ""),   # 로컬 경로
            }]
        )

    print(f"  ✅ ChromaDB 저장 완료: {collection.count()}개")
    return collection


# ─────────────────────────────────────────────
# 7. 임베딩 품질 검증
#    파인튜닝 전후 유사도 비교
# ─────────────────────────────────────────────
def validate_embeddings(results: list):
    """
    같은 출원번호 내 도면끼리(positive) vs 다른 출원번호(negative) 평균 유사도 출력.
    파인튜닝 효과 정량 확인용.
    """
    print("\n[4] 임베딩 품질 검증...")

    from collections import defaultdict
    by_app = defaultdict(list)
    for item in results:
        app_num = item["metadata"].get("applicationNumber", "")
        emb     = np.array(item["embedding"])
        by_app[app_num].append(emb)

    pos_sims, neg_sims = [], []
    app_list = list(by_app.keys())

    import random
    random.seed(42)

    for app_num, embs in by_app.items():
        # Positive: 같은 출원번호 내 도면 간
        for i in range(len(embs)):
            for j in range(i + 1, len(embs)):
                sim = float(np.dot(embs[i], embs[j]))
                pos_sims.append(sim)

        # Negative: 랜덤 다른 출원번호
        other_apps = [a for a in app_list if a != app_num]
        if other_apps:
            other_embs = by_app[random.choice(other_apps)]
            sim = float(np.dot(embs[0], other_embs[0]))
            neg_sims.append(sim)

    if pos_sims and neg_sims:
        avg_pos = np.mean(pos_sims)
        avg_neg = np.mean(neg_sims)
        gap     = avg_pos - avg_neg
        print(f"  같은 출원번호(positive) 평균 유사도: {avg_pos:.4f}")
        print(f"  다른 출원번호(negative) 평균 유사도: {avg_neg:.4f}")
        print(f"  Gap (pos - neg):                   {gap:+.4f}")
        if gap > 0:
            print(f"  ✅ 파인튜닝 효과 있음: positive가 negative보다 {gap:.4f} 더 가까움")
        else:
            print(f"  ⚠️  Gap이 음수 — 파인튜닝 효과 미흡 (추가 학습 필요)")


# ─────────────────────────────────────────────
# 8. 메인
# ─────────────────────────────────────────────
def main():
    print("=" * 60)
    print("Fine-tuned CLIP Inference & ChromaDB 재구축")
    print("=" * 60)

    # 파인튜닝 모델 로드
    model, preprocess = load_finetuned_clip(FINETUNED_MODEL_PATH)

    # 이미지 ↔ 메타데이터 매핑
    img_dict, meta_dict = build_mappings()
    print(f"\n  이미지 파일:   {len(img_dict)}개")
    print(f"  메타데이터:    {len(meta_dict)}개")

    # 전체 재임베딩
    results = reembed_all(model, preprocess, img_dict, meta_dict)

    # ChromaDB 재구축
    rebuild_chromadb(results)

    # 품질 검증
    validate_embeddings(results)

    print(f"\n{'=' * 60}")
    print("✅ 완료!")
    print(f"  새 임베딩 JSON: {NEW_EMB_DIR}")
    print(f"  새 ChromaDB:    {NEW_CHROMA_PATH}")
    print(f"\n  app.py 의 CHROMA_DB_PATH 를 아래로 변경하세요:")
    print(f"  CHROMA_DB_PATH = \"{NEW_CHROMA_PATH}\"")
    print(f"  FINETUNED_MODEL = \"{FINETUNED_MODEL_PATH}\"")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
