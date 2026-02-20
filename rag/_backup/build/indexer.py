"""Dense/Sparse 인덱스 빌드. (인덱싱 시 1회 실행)

하는 일:
    - build_dense_index(): 청크의 dense_text를 KURE-v1(1024차원)으로 임베딩 → ChromaDB 저장
    - build_sparse_index(): 청크의 sparse_text를 kiwipiepy로 토크나이징 → BM25 pickle 저장

관계:
    - build/chunker.py가 만든 청크를 입력으로 받음
    - index/tokenizer.py의 morpheme_tokenize()로 BM25 토크나이징
    - search/retriever.py가 빌드된 인덱스를 로드하여 검색
    - eval/build_index.py가 build_dense_index(), build_sparse_index()를 호출
"""
import json
import pickle

import chromadb
from chromadb.config import Settings
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

import importlib.util

from .. import config

# tokenizer.py는 index/ 폴더에 bm25.pkl과 함께 배포됨
_tokenizer_path = config.INDEX_DIR / "tokenizer.py"
_spec = importlib.util.spec_from_file_location("tokenizer", _tokenizer_path)
_tokenizer_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_tokenizer_mod)
morpheme_tokenize = _tokenizer_mod.morpheme_tokenize

# ── 모델/DB 싱글톤 ──────────────────────────────────

_model: SentenceTransformer | None = None
_client: chromadb.ClientAPI | None = None
_collection: chromadb.Collection | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(config.EMBED_MODEL)
    return _model


def _get_collection() -> chromadb.Collection:
    global _client, _collection
    if _collection is None:
        _client = chromadb.PersistentClient(
            path=str(config.CHROMA_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
        _collection = _client.get_or_create_collection(
            name=config.CHROMA_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


# ── Dense 인덱스 빌드 ────────────────────────────────

def build_dense_index(chunks: list[dict], force: bool = False) -> int:
    """청크의 dense_text를 KURE-v1로 임베딩하여 ChromaDB에 저장.

    Returns:
        저장된 문서 수.
    """
    if config.CHROMA_DIR.exists() and not force:
        col = _get_collection()
        count = col.count()
        if count > 0:
            print(f"ChromaDB 이미 존재: {count}개 문서")
            return count

    model = _get_model()
    col = _get_collection()

    if force and _client is not None:
        try:
            _client.delete_collection(config.CHROMA_COLLECTION)
        except Exception:
            pass
        global _collection
        _collection = _client.get_or_create_collection(
            name=config.CHROMA_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        col = _collection

    texts = [c["dense_text"] for c in chunks]
    ids = [c["chunk_id"] for c in chunks]
    metadatas = []
    for c in chunks:
        meta = {k: v for k, v in c["metadata"].items() if isinstance(v, (str, int, float, bool))}
        meta["ipc"] = ", ".join(c["metadata"].get("ipc", []))
        meta["dep_claim_nums"] = json.dumps(c["metadata"].get("dep_claim_nums", []))
        metadatas.append(meta)

    # 길이순 정렬 → 적응형 배치 사이즈로 인코딩
    sorted_indices = sorted(range(len(texts)), key=lambda i: len(texts[i]))
    sorted_texts = [texts[i] for i in sorted_indices]

    import torch
    all_sorted_embeddings = []
    i = 0
    print(f"KURE-v1 임베딩 중... ({len(sorted_texts)}개, 적응형 배치)")
    pbar = tqdm(total=len(sorted_texts), desc="Encoding")
    while i < len(sorted_texts):
        max_len = len(sorted_texts[min(i + config.EMBED_BATCH_SIZE - 1, len(sorted_texts) - 1)])
        if max_len > 2000:
            bs = 8
        elif max_len > 1000:
            bs = 16
        else:
            bs = config.EMBED_BATCH_SIZE
        batch = sorted_texts[i:i + bs]
        embs = model.encode(batch, batch_size=bs, device="cuda", normalize_embeddings=False)
        all_sorted_embeddings.extend(embs.tolist())
        pbar.update(len(batch))
        i += bs
        torch.cuda.empty_cache()
    pbar.close()

    # 원래 순서로 복원
    all_embeddings = [None] * len(texts)
    for new_idx, orig_idx in enumerate(sorted_indices):
        all_embeddings[orig_idx] = all_sorted_embeddings[new_idx]

    print(f"ChromaDB 저장 중... ({len(all_embeddings)}개)")
    chroma_batch = 5000
    for i in tqdm(range(0, len(all_embeddings), chroma_batch), desc="ChromaDB Insert"):
        end = min(i + chroma_batch, len(all_embeddings))
        col.add(
            ids=ids[i:end],
            embeddings=all_embeddings[i:end],
            metadatas=metadatas[i:end],
            documents=texts[i:end],
        )

    count = col.count()
    print(f"ChromaDB 저장 완료: {count}개 문서")
    return count


# ── Sparse 인덱스 빌드 ───────────────────────────────

def build_sparse_index(chunks: list[dict], force: bool = False) -> int:
    """청크의 sparse_text를 토크나이징하여 BM25 인덱스 생성 후 pickle 저장.

    Returns:
        인덱싱된 문서 수.
    """
    if config.BM25_PATH.exists() and not force:
        data = pickle.loads(config.BM25_PATH.read_bytes())
        count = len(data["chunk_ids"])
        print(f"BM25 인덱스 이미 존재: {count}개 문서")
        return count

    print(f"BM25 인덱싱 중... ({len(chunks)}개)")
    tokenized = []
    chunk_ids = []
    for c in chunks:
        tokens = morpheme_tokenize(c["sparse_text"])
        tokenized.append(tokens)
        chunk_ids.append(c["chunk_id"])

    bm25 = BM25Okapi(tokenized, k1=config.BM25_K1, b=config.BM25_B)

    config.BM25_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(config.BM25_PATH, "wb") as f:
        pickle.dump({
            "bm25": bm25,
            "chunk_ids": chunk_ids,
        }, f)

    print(f"BM25 저장 완료: {len(chunk_ids)}개 문서 → {config.BM25_PATH}")
    return len(chunk_ids)
