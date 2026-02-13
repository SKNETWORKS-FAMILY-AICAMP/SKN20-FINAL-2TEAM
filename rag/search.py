"""RAG 검색 모듈.

사용법:
    from rag.search import search
    results = search("헤스페리딘이 포함된 화장료", top_k=10)

    # MySQL 세션 주입 (백엔드 연동)
    from rag.search import search, set_db_session
    set_db_session(db_session)
    results = search("헤스페리딘 화장료")
"""
import pickle
from typing import Optional

import chromadb
from chromadb.config import Settings
from kiwipiepy import Kiwi
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from . import config

# ============================================================
# 글로벌 객체 (lazy loading)
# ============================================================
_embed_model: Optional[SentenceTransformer] = None
_chroma_collection: Optional[chromadb.Collection] = None
_bm25: Optional[BM25Okapi] = None
_bm25_chunk_ids: Optional[list] = None
_kiwi: Optional[Kiwi] = None
_db_session: Optional[Session] = None


def _get_embed_model() -> SentenceTransformer:
    global _embed_model
    if _embed_model is None:
        _embed_model = SentenceTransformer(config.EMBED_MODEL)
    return _embed_model


def _get_chroma() -> chromadb.Collection:
    global _chroma_collection
    if _chroma_collection is None:
        client = chromadb.PersistentClient(
            path=str(config.CHROMA_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
        _chroma_collection = client.get_or_create_collection(
            name=config.CHROMA_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
    return _chroma_collection


def _get_bm25() -> tuple[BM25Okapi, list]:
    global _bm25, _bm25_chunk_ids
    if _bm25 is None:
        with open(config.BM25_PATH, "rb") as f:
            data = pickle.load(f)
            _bm25 = data["bm25"]
            _bm25_chunk_ids = data["chunk_ids"]
    return _bm25, _bm25_chunk_ids


def _get_kiwi() -> Kiwi:
    global _kiwi
    if _kiwi is None:
        _kiwi = Kiwi()
    return _kiwi


def _get_db_session() -> Session:
    global _db_session
    if _db_session is None:
        engine = create_engine(config.DATABASE_URL)
        SessionLocal = sessionmaker(bind=engine)
        _db_session = SessionLocal()
    return _db_session


def set_db_session(session: Session):
    """외부에서 DB 세션 주입 (백엔드 연동용)."""
    global _db_session
    _db_session = session


# ============================================================
# 검색 함수
# ============================================================
def _dense_search(query: str, top_k: int) -> list[tuple[str, float]]:
    """Dense 검색 (KURE-v1 + ChromaDB)."""
    model = _get_embed_model()
    col = _get_chroma()

    query_emb = model.encode([query])[0].tolist()
    results = col.query(
        query_embeddings=[query_emb],
        n_results=min(top_k, col.count()),
    )

    pairs = []
    for cid, dist in zip(results["ids"][0], results["distances"][0]):
        pairs.append((cid, dist))
    return pairs


def _sparse_search(query: str, top_k: int) -> list[tuple[str, float]]:
    """Sparse 검색 (BM25)."""
    bm25, chunk_ids = _get_bm25()
    kiwi = _get_kiwi()

    # 형태소 분석으로 토큰화
    tokens = [t.form for t in kiwi.tokenize(query) if t.tag.startswith("NN")]
    if not tokens:
        tokens = query.split()

    scores = bm25.get_scores(tokens)

    # 상위 top_k 추출
    top_indices = scores.argsort()[-top_k:][::-1]
    pairs = [(chunk_ids[i], float(scores[i])) for i in top_indices if scores[i] > 0]
    return pairs


def _rrf_fusion(
    dense_results: list[tuple[str, float]],
    sparse_results: list[tuple[str, float]],
) -> list[tuple[str, float]]:
    """RRF (Reciprocal Rank Fusion) 점수 합산."""
    k = config.RRF_K
    w_dense = config.RRF_WEIGHT_DENSE
    w_sparse = config.RRF_WEIGHT_SPARSE

    scores = {}

    # Dense 점수 (distance 낮을수록 좋음 → 순위 역순)
    for rank, (cid, _) in enumerate(sorted(dense_results, key=lambda x: x[1])):
        scores[cid] = scores.get(cid, 0) + w_dense / (k + rank + 1)

    # Sparse 점수 (score 높을수록 좋음)
    for rank, (cid, _) in enumerate(sorted(sparse_results, key=lambda x: -x[1])):
        scores[cid] = scores.get(cid, 0) + w_sparse / (k + rank + 1)

    return sorted(scores.items(), key=lambda x: -x[1])


def _patent_collapse(rrf_results: list[tuple[str, float]], top_k: int) -> list[dict]:
    """같은 특허의 여러 청크 중 최고 점수 1개만 유지."""
    best = {}

    for cid, score in rrf_results:
        # chunk_id 형식: "1020210104313_claim_1"
        patent_id = cid.split("_claim_")[0] if "_claim_" in cid else cid

        if patent_id not in best or score > best[patent_id]["score"]:
            best[patent_id] = {
                "patent_id": patent_id,
                "chunk_id": cid,
                "score": score,
            }

    collapsed = sorted(best.values(), key=lambda x: -x["score"])
    return collapsed[:top_k]


def _get_patent_info(patent_id: str) -> Optional[dict]:
    """MySQL에서 특허 정보 조회."""
    session = _get_db_session()

    # 특허 기본 정보
    row = session.execute(
        text("""
            SELECT id, application_num, register_num, title, register_status
            FROM patents WHERE application_num = :num
        """),
        {"num": patent_id},
    ).fetchone()

    if not row:
        return None

    db_patent_id = row[0]

    # 청구항 조회
    last_claims = session.execute(
        text("""
            SELECT claim_number, claim_type, change_type, claim_text
            FROM claims
            WHERE patent_id = :pid AND version_type = 'last'
            ORDER BY claim_number
        """),
        {"pid": db_patent_id},
    ).fetchall()

    # 금반언 청구항 (삭제된 것)
    estoppel_claims = [c[0] for c in last_claims if c[2] == "삭제"]

    return {
        "patent_id": patent_id,
        "register_num": row[2] or "",
        "title": row[3] or "",
        "register_status": row[4] or "",
        "claims": [
            {
                "claim_number": c[0],
                "claim_type": c[1],
                "change_type": c[2],
                "text": c[3],
            }
            for c in last_claims
        ],
        "estoppel_claim_numbers": estoppel_claims,
    }


def _apply_filter(collapsed: list[dict]) -> list[dict]:
    """등록 상태 필터 + 메타데이터 보강."""
    results = []

    for item in collapsed:
        patent_id = item["patent_id"]
        patent_info = _get_patent_info(patent_id)

        # 특허 정보 없으면 스킵
        if not patent_info:
            continue

        # 등록 필터
        if config.REGISTERED_ONLY and patent_info["register_status"] != "등록":
            continue

        results.append({
            "patent_id": patent_id,
            "score": item["score"],
            "title": patent_info["title"],
            "register_status": patent_info["register_status"],
            "claims": patent_info["claims"],
            "estoppel_claim_numbers": patent_info["estoppel_claim_numbers"] if config.ESTOPPEL_ENABLED else [],
        })

    return results


# ============================================================
# 메인 검색 함수
# ============================================================
def search(
    query: str,
    top_k: int = None,
    use_sparse: bool = True,
) -> list[dict]:
    """RAG 검색.

    Args:
        query: 검색 쿼리
        top_k: 반환할 결과 수 (기본: config.FINAL_TOP_K)
        use_sparse: BM25 스파스 검색 사용 여부

    Returns:
        [
            {
                "patent_id": "1020210104313",
                "score": 0.0234,
                "title": "특허 제목",
                "register_status": "등록",
                "claims": [...],
                "estoppel_claim_numbers": [5, 11],
            },
            ...
        ]
    """
    top_k = top_k or config.FINAL_TOP_K

    # 1. Dense 검색
    dense_results = _dense_search(query, config.DENSE_TOP_K)

    # 2. Sparse 검색 (선택적)
    if use_sparse and config.BM25_PATH.exists():
        sparse_results = _sparse_search(query, config.SPARSE_TOP_K)
        # 3. RRF 합산
        fused = _rrf_fusion(dense_results, sparse_results)
    else:
        # Dense만 사용
        fused = [(cid, 1.0 / (config.RRF_K + rank + 1))
                 for rank, (cid, _) in enumerate(sorted(dense_results, key=lambda x: x[1]))]

    # 4. Patent Collapse
    collapsed = _patent_collapse(fused, top_k * 3)  # 필터링 고려해 여유있게

    # 5. MySQL 필터 + 메타데이터 보강
    results = _apply_filter(collapsed)

    return results[:top_k]


def search_simple(query: str, top_k: int = 10) -> list[dict]:
    """간단한 Dense 검색 (필터링 없음).

    MySQL 연결 없이 ChromaDB만으로 검색.
    """
    dense_results = _dense_search(query, top_k)

    results = []
    for cid, distance in dense_results:
        patent_id = cid.split("_claim_")[0] if "_claim_" in cid else cid
        results.append({
            "patent_id": patent_id,
            "chunk_id": cid,
            "distance": distance,
        })

    return results
