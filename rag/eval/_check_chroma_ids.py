"""ChromaDB에서 출원번호/등록번호 매핑 확인"""
import chromadb

client = chromadb.PersistentClient(path="data/chroma-patent")
cols = client.list_collections()

for c in cols:
    print(f"{c.name}: {c.count()} docs")
    sample = c.peek(3)
    for i, meta in enumerate(sample["metadatas"]):
        print(f"  [{i}] apply_num={meta.get('apply_num','N/A')}, regit_num={meta.get('regit_num','N/A')}")
        print(f"       keys={list(meta.keys())}")
