import os
import json
import chromadb
from datetime import datetime
from pathlib import Path
import torch.nn.functional as F
import torch

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ─────────────────────────────────────────────
# 0. 경로 설정
# ─────────────────────────────────────────────
CHROMA_DB_PATH = str(PROJECT_ROOT / "data/evaldata/chroma_db_train_v2")
COLLECTION_NAME = "design"

IMAGE_DIR = str(PROJECT_ROOT / "data/evaldata/images_reject_v2")

EMBEDDING_DIRS = [
    str(PROJECT_ROOT / "data/evaldata/embeddings_reject_v2"),
]

error_log_path = str(PROJECT_ROOT / "data/evaldata/imgEmbedding_vectorDB_v2.txt")

# ─────────────────────────────────────────────
# 1. 로컬 이미지 경로 자동 매핑 딕셔너리 구축
#
# 이미지 파일명 패턴: {applicationNum}-reject-{imgIdx}_{number}.jpg
# 임베딩 ID 패턴:    {applicationNum}-reject-{imgIdx}-IMG-{imgIdx}
# 공통 키:           {applicationNum}-reject-{imgIdx}
# ─────────────────────────────────────────────
def build_img_dict(image_dir: str) -> dict:
    """
    images_reject_v2 폴더의 파일명에서 공통 키를 추출해
    {공통키: 로컬절대경로} 딕셔너리를 반환.

    예:
      '3020140047287-reject-0_11.jpg'
          → 키: '3020140047287-reject-0'
          → 값: '/Users/.../images_reject_v2/3020140047287-reject-0_11.jpg'
    """
    img_dict = {}
    if not os.path.exists(image_dir):
        print(f"⚠️  이미지 폴더 없음: {image_dir}")
        return img_dict

    for fname in os.listdir(image_dir):
        if fname.startswith("."):
            continue
        stem = fname.rsplit(".", 1)[0]       # 확장자 제거: '3020140047287-reject-0_11'
        key  = stem.rsplit("_", 1)[0]        # 번호 제거:  '3020140047287-reject-0'
        img_dict[key] = os.path.join(image_dir, fname)

    print(f"✅ 이미지 딕셔너리 구축 완료: {len(img_dict)}개")
    return img_dict


def emb_id_to_key(emb_id: str) -> str:
    """
    임베딩 ID에서 공통 키 추출.

    예: '3020140047287-reject-0-IMG-0' → '3020140047287-reject-0'
    """
    return emb_id.rsplit("-IMG-", 1)[0]


def normalize_embedding(raw_emb: list) -> list:
    """
    JSON에서 읽은 raw 임베딩 리스트를 L2 정규화(unit vector)하여 반환.

    embeddings_v2.py 생성 시 F.normalize가 미적용(norm ≈ 11)되어 있으므로
    ChromaDB 저장 전 여기서 정규화.
    """
    tensor    = torch.tensor(raw_emb, dtype=torch.float32).unsqueeze(0)  # (1, 512)
    normed    = F.normalize(tensor, dim=-1)                               # unit vector
    return normed.squeeze(0).tolist()                                     # list[float] 512개


# ─────────────────────────────────────────────
# 2. ChromaDB 재구축 (기존 컬렉션 삭제 후 새로 생성)
# ─────────────────────────────────────────────
print("\n🔄 ChromaDB 재구축 시작...")
chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

# 기존 컬렉션 삭제 (클린 재구축)
try:
    chroma_client.delete_collection(name=COLLECTION_NAME)
    print(f"🗑️  기존 컬렉션 '{COLLECTION_NAME}' 삭제 완료")
except Exception:
    print(f"ℹ️  기존 컬렉션 없음 — 새로 생성합니다")

image_collection = chroma_client.get_or_create_collection(
    name=COLLECTION_NAME,
    metadata={"hnsw:space": "cosine"}   # 코사인 거리 사용
)
print(f"✅ 컬렉션 '{COLLECTION_NAME}' 생성 완료")

# ─────────────────────────────────────────────
# 3. 이미지 딕셔너리 구축
# ─────────────────────────────────────────────
img_dict = build_img_dict(IMAGE_DIR)

# ─────────────────────────────────────────────
# 4. 임베딩 JSON → 정규화 → ChromaDB 저장
# ─────────────────────────────────────────────
error_logs   = []
count        = 0
error_count  = 0
no_img_count = 0   # 로컬 이미지 매핑 실패 수

for embedding_dir in EMBEDDING_DIRS:
    print(f"\n📁 처리 중: {embedding_dir}")

    if not os.path.exists(embedding_dir):
        msg = f"경로 없음: {embedding_dir}\n"
        print(f"⚠️  {msg}")
        error_logs.append(msg)
        continue

    for filename in sorted(os.listdir(embedding_dir)):
        if not filename.endswith("_embedding.json"):
            continue

        filepath = os.path.join(embedding_dir, filename)

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            # ── 임베딩 벡터 확인 ──
            if "embedding" not in data:
                msg = f"Embedding 없음: {filepath}\n"
                print(f"⚠️  {msg}")
                error_logs.append(msg)
                error_count += 1
                continue

            emb_id = data.get("id")
            meta   = data.get("metadata", {})

            # ── [핵심 수정 1] F.normalize로 unit vector 변환 ──
            raw_emb    = data["embedding"]
            normed_emb = normalize_embedding(raw_emb)

            # ── [핵심 수정 2] 로컬 이미지 경로 자동 매핑 ──
            key        = emb_id_to_key(emb_id)          # '3020140047287-reject-0'
            local_path = img_dict.get(key, "")           # 로컬 절대경로
            if not local_path:
                print(f"  ⚠️  이미지 매핑 실패: {emb_id} (key={key})")
                no_img_count += 1

            # ── ChromaDB에 저장 ──
            image_collection.add(
                ids=[emb_id],
                embeddings=[normed_emb],                 # ← 정규화된 unit vector
                metadatas=[{
                    "design_id":         meta.get("design_id", ""),
                    "applicationNumber": meta.get("applicationNumber", ""),
                    "LCCode":            meta.get("LCCode", ""),
                    "articleName":       meta.get("articleName", ""),
                    "imageNumber":       str(meta.get("imageNumber", "")),
                    "admstStat":         meta.get("status", {}).get("admstStat", "")
                                        if isinstance(meta.get("status"), dict)
                                        else "",
                    "imagePath":         local_path,     # ← 로컬 경로 (URL 아님)
                }]
            )

            count += 1
            print(f"  ✓ [{count}] {emb_id}  →  {os.path.basename(local_path) or '이미지없음'}")

        except Exception as e:
            msg = f"파일: {filepath}\n에러: {str(e)}\n{'-'*60}\n"
            print(f"❌ 에러 ({filename}): {e}")
            error_logs.append(msg)
            error_count += 1

# ─────────────────────────────────────────────
# 5. 에러 로그 저장
# ─────────────────────────────────────────────
if error_logs:
    with open(error_log_path, "w", encoding="utf-8") as f:
        f.write(f"에러 발생 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"총 에러 수: {error_count}\n")
        f.write("="*60 + "\n\n")
        f.writelines(error_logs)
    print(f"\n📝 에러 로그 저장: {error_log_path}")

# ─────────────────────────────────────────────
# 6. 결과 요약
# ─────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"✅ ChromaDB 저장 완료: {count}개")
print(f"⚠️  에러 발생:          {error_count}개")
print(f"🖼️  이미지 매핑 실패:   {no_img_count}개")
print(f"📦 최종 컬렉션 크기:   {image_collection.count()}개")
print(f"{'='*60}")
