"""RAG 인덱싱 모듈.

MySQL의 청구항 데이터를 ChromaDB + BM25로 인덱싱합니다.

사용법:
    python -m rag.indexer

    # 또는 코드에서
    from rag.indexer import build_index
    build_index()
"""
import pickle
from tqdm import tqdm

import chromadb
from chromadb.config import Settings
from kiwipiepy import Kiwi
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer
from sqlalchemy import create_engine, text

from . import config


def get_claims_from_mysql() -> list[dict]:
    """MySQL에서 등록된 특허의 청구항 조회."""
    engine = create_engine(config.DATABASE_URL)

    with engine.connect() as conn:
        # 등록된 특허의 독립항만 조회
        rows = conn.execute(text("""
            SELECT
                p.application_num,
                p.title,
                c.claim_number,
                c.claim_text
            FROM patents p
            JOIN claims c ON p.id = c.patent_id
            WHERE p.register_status = '등록'
              AND c.version_type = 'last'
              AND c.claim_type = 'independent'
              AND c.change_type != '삭제'
              AND c.claim_text IS NOT NULL
              AND c.claim_text != '[삭제됨]'
            ORDER BY p.application_num, c.claim_number
        """)).fetchall()

    claims = []
    for row in rows:
        claims.append({
            "patent_id": row[0],
            "title": row[1],
            "claim_number": row[2],
            "claim_text": row[3],
        })

    return claims


def create_chunks(claims: list[dict]) -> list[dict]:
    """청구항을 검색용 청크로 변환."""
    chunks = []

    for claim in claims:
        chunk_id = f"{claim['patent_id']}_claim_{claim['claim_number']}"

        # 검색용 텍스트: 제목 + 청구항
        search_text = f"{claim['title']}\n\n{claim['claim_text']}"

        chunks.append({
            "chunk_id": chunk_id,
            "text": search_text,
            "patent_id": claim["patent_id"],
            "claim_number": claim["claim_number"],
        })

    return chunks


def build_chroma_index(chunks: list[dict], batch_size: int = 32):
    """ChromaDB 벡터 인덱스 생성."""
    print("임베딩 모델 로딩...")
    model = SentenceTransformer(config.EMBED_MODEL)

    print("ChromaDB 초기화...")
    config.CHROMA_DIR.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(
        path=str(config.CHROMA_DIR),
        settings=Settings(anonymized_telemetry=False),
    )

    # 기존 컬렉션 삭제 후 재생성
    try:
        client.delete_collection(config.CHROMA_COLLECTION)
    except:
        pass

    collection = client.create_collection(
        name=config.CHROMA_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )

    print(f"임베딩 생성 및 저장 ({len(chunks)}개 청크)...")

    for i in tqdm(range(0, len(chunks), batch_size), desc="인덱싱"):
        batch = chunks[i:i + batch_size]

        ids = [c["chunk_id"] for c in batch]
        texts = [c["text"] for c in batch]
        metadatas = [{"patent_id": c["patent_id"], "claim_number": c["claim_number"]} for c in batch]

        # 임베딩 생성
        embeddings = model.encode(texts, show_progress_bar=False).tolist()

        # ChromaDB에 저장
        collection.add(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=texts,
        )

    print(f"ChromaDB 인덱싱 완료: {collection.count()}개")


def build_bm25_index(chunks: list[dict]):
    """BM25 스파스 인덱스 생성."""
    print("BM25 인덱스 생성...")

    kiwi = Kiwi()

    # 토큰화
    tokenized = []
    chunk_ids = []

    for chunk in tqdm(chunks, desc="토큰화"):
        tokens = [t.form for t in kiwi.tokenize(chunk["text"]) if t.tag.startswith("NN")]
        tokenized.append(tokens)
        chunk_ids.append(chunk["chunk_id"])

    # BM25 모델 생성
    bm25 = BM25Okapi(tokenized)

    # 저장
    config.INDEX_DIR.mkdir(parents=True, exist_ok=True)
    with open(config.BM25_PATH, "wb") as f:
        pickle.dump({"bm25": bm25, "chunk_ids": chunk_ids}, f)

    print(f"BM25 인덱싱 완료: {len(chunk_ids)}개")


def build_index():
    """전체 인덱스 빌드."""
    print("=" * 60)
    print("RAG 인덱스 빌드 시작")
    print("=" * 60)

    # 1. MySQL에서 데이터 로드
    print("\n[1/4] MySQL에서 청구항 로드...")
    claims = get_claims_from_mysql()
    print(f"로드된 청구항: {len(claims)}개")

    if not claims:
        print("청구항이 없습니다. 종료합니다.")
        return

    # 2. 청크 생성
    print("\n[2/4] 청크 생성...")
    chunks = create_chunks(claims)
    print(f"생성된 청크: {len(chunks)}개")

    # 3. ChromaDB 인덱싱
    print("\n[3/4] ChromaDB 인덱싱...")
    build_chroma_index(chunks)

    # 4. BM25 인덱싱
    print("\n[4/4] BM25 인덱싱...")
    build_bm25_index(chunks)

    print("\n" + "=" * 60)
    print("인덱스 빌드 완료!")
    print("=" * 60)


if __name__ == "__main__":
    build_index()
