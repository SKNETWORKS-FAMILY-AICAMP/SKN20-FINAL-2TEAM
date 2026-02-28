"""ChromaDB HNSW 인덱스 재빌드 (Linux→Windows 호환 문제 해결).

기존 컬렉션에서 데이터를 배치로 읽어서 새 컬렉션에 넣고,
새 컬렉션 이름을 원래 이름으로 교체.
"""
import chromadb
from chromadb.config import Settings
import time
import sys

DB_PATH = "rag/index/chroma_db"
OLD_NAME = "patent_chunks"
TEMP_NAME = "patent_chunks_rebuild"
BATCH_SIZE = 5000

client = chromadb.PersistentClient(path=DB_PATH, settings=Settings(anonymized_telemetry=False))

old_col = client.get_collection(OLD_NAME)
total = old_col.count()
print(f"총 문서: {total:,}건")
print(f"배치 크기: {BATCH_SIZE:,}")
print(f"예상 배치 수: {(total // BATCH_SIZE) + 1}")
print()

# 기존 temp 컬렉션 삭제
try:
    client.delete_collection(TEMP_NAME)
except Exception:
    pass

new_col = client.get_or_create_collection(
    name=TEMP_NAME,
    metadata={"hnsw:space": "cosine"},
)

start = time.time()
offset = 0

while offset < total:
    batch = old_col.get(
        limit=BATCH_SIZE,
        offset=offset,
        include=["embeddings", "metadatas", "documents"],
    )

    ids = batch["ids"]
    if not ids:
        break

    kwargs = {"ids": ids}
    if batch["embeddings"] is not None:
        kwargs["embeddings"] = batch["embeddings"]
    if batch["metadatas"] is not None:
        kwargs["metadatas"] = batch["metadatas"]
    if batch["documents"] is not None:
        kwargs["documents"] = batch["documents"]

    new_col.add(**kwargs)

    offset += len(ids)
    elapsed = time.time() - start
    speed = offset / elapsed if elapsed > 0 else 0
    pct = offset / total * 100
    print(f"  {offset:>8,} / {total:,} ({pct:.1f}%) | {elapsed:.0f}s ({speed:,.0f}/s)", end="\r")
    sys.stdout.flush()

elapsed = time.time() - start
print(f"\n\n복사 완료: {new_col.count():,}건 ({elapsed:.1f}s)")

# 이름 교체: old → backup, new → old
print("컬렉션 이름 교체 중...")
try:
    client.delete_collection("patent_chunks_backup")
except Exception:
    pass

# old 삭제 → new 이름 변경은 chromadb에서 직접 지원 안 하므로
# old를 백업으로 남기고 new를 사용하도록 config 수정
print(f"\n완료! 새 컬렉션: {TEMP_NAME} ({new_col.count():,}건)")
print(f"원본 컬렉션: {OLD_NAME} (백업으로 유지)")
print()
print("테스트하려면 config.py에서 CHROMA_COLLECTION을 변경하세요:")
print(f'  CHROMA_COLLECTION = "{TEMP_NAME}"')
