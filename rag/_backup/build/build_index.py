"""원커맨드 인덱스 빌더. 특허 JSON → 검색 인덱스 전체를 한번에 생성합니다.

순서:
    [1] build/chunker.py → 특허 JSON을 청크로 변환 → chunks.json 저장
    [2] build/chunker.py → 필터링용 claims_db.json 생성
    [3] build/indexer.py → KURE-v1 임베딩 → ChromaDB 저장
    [4] build/indexer.py → BM25 인덱스 → bm25.pkl 저장

Usage:
    # rag 폴더의 상위 디렉토리에서 실행
    python -m rag.build.build_index --data-dir temp_json_samples
    python -m rag.build.build_index --data-dir temp_json_samples --force
"""
import argparse
import json
import sys
from pathlib import Path

from .. import config
from .chunker import load_chunks_from_dir, build_claims_db
from .indexer import build_dense_index, build_sparse_index


def main():
    """CLI 진입점. 4단계(청크→claims_db→Dense→Sparse) 순차 실행."""
    parser = argparse.ArgumentParser(description="RAG 인덱스 빌더")
    parser.add_argument(
        "--data-dir",
        type=str,
        default=str(config.DATA_DIR),
        help="특허 JSON 디렉토리 경로",
    )
    parser.add_argument("--force", action="store_true", help="기존 인덱스 강제 재빌드")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.is_absolute():
        data_dir = config.PROJECT_DIR / data_dir

    if not data_dir.exists():
        print(f"데이터 디렉토리 없음: {data_dir}")
        sys.exit(1)

    print(f"{'='*60}")
    print(f"RAG 인덱스 빌드")
    print(f"  데이터: {data_dir}")
    print(f"  인덱스: {config.INDEX_DIR}")
    print(f"  강제 재빌드: {args.force}")
    print(f"{'='*60}\n")

    # 1. 청크 생성
    print("[1/4] 청크 생성...")
    chunks = load_chunks_from_dir(data_dir)
    if not chunks:
        print("청크가 0개입니다. 데이터를 확인하세요.")
        sys.exit(1)

    config.INDEX_DIR.mkdir(parents=True, exist_ok=True)
    with open(config.CHUNKS_PATH, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)
    print(f"  chunks.json 저장: {len(chunks)}개\n")

    # 2. claims_db 생성
    print("[2/4] claims_db 생성...")
    n_patents = build_claims_db(data_dir, config.CLAIMS_DB_PATH)
    print()

    # 3. Dense 인덱스
    print("[3/4] Dense 인덱스 (KURE-v1 + ChromaDB)...")
    n_dense = build_dense_index(chunks, force=args.force)
    print()

    # 4. Sparse 인덱스
    print("[4/4] Sparse 인덱스 (BM25)...")
    n_sparse = build_sparse_index(chunks, force=args.force)
    print()

    print(f"{'='*60}")
    print(f"빌드 완료!")
    print(f"  청크: {len(chunks)}개")
    print(f"  특허(claims_db): {n_patents}개")
    print(f"  Dense 인덱스: {n_dense}개")
    print(f"  Sparse 인덱스: {n_sparse}개")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
