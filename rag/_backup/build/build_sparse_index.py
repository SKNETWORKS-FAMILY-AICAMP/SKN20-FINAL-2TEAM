"""BM25 Inverted Index 빌더. chunks.jsonl → bm25_index/ (5개 파일)

기존 bm25.pkl (rank_bm25 라이브러리, 전체 순회)을 대체하는
inverted index 기반 BM25 인덱스를 빌드합니다.

하는 일:
    1. chunks.jsonl을 한 줄씩 스트리밍 (8GB 전체를 메모리에 올리지 않음)
    2. 각 chunk의 sparse_text를 morpheme_tokenize()로 토크나이징
    3. inverted index 생성: postings[term] = [(doc_id, tf), ...]
    4. idf 계산: log((N - df + 0.5) / (df + 0.5)) -전체 corpus 기준
    5. doc_len, doc_map, meta 저장

산출물:
    index/bm25_index/
     ├─ postings.pkl      # dict[str, list[tuple[int, int]]]
     ├─ idf.pkl           # dict[str, float]
     ├─ doc_len.pkl        # dict[int, int]
     ├─ doc_map.pkl        # dict[int, str]
     └─ meta.json         # {"N": ..., "avg_doc_len": ..., "k1": ..., "b": ...}

사용법:
    # 프로젝트 루트에서
    python -m rag.build.build_sparse_index

    # 또는 강제 재빌드
    python -m rag.build.build_sparse_index --force

관계:
    - index/tokenizer.py의 morpheme_tokenize()로 토크나이징 (기존과 동일)
    - search/retriever.py가 빌드된 인덱스를 로드하여 BM25 검색
    - 기존 build/indexer.py의 build_sparse_index()와 동일 토크나이징
"""
import json
import math
import pickle
import sys
import time
from collections import defaultdict
from pathlib import Path

# ── 경로 설정 ──────────────────────────────────────────
# 이 파일 위치: rag/build/build_sparse_index.py
_this_dir = Path(__file__).parent
_rag_dir = _this_dir.parent

# config에서 경로/파라미터 로드
sys.path.insert(0, str(_rag_dir.parent))
from rag import config

# NOTE: tokenizer.py (kiwipiepy)는 인덱싱 시 불필요.
# sparse_text가 이미 extract_keywords_for_sparse()에서 토크나이징된 결과이므로
# split()만으로 충분. 검색 시 쿼리 토크나이징은 retriever.py에서 수행.


# ══════════════════════════════════════════════════════
# 인덱싱 메인
# ══════════════════════════════════════════════════════

def build(force: bool = False) -> None:
    """BM25 inverted index 빌드.

    chunks.jsonl을 스트리밍으로 읽으며:
    1. 각 chunk를 토크나이징
    2. postings (inverted index) 구축
    3. idf, doc_len, doc_map, meta 계산/저장
    """
    output_dir = config.SPARSE_INDEX_DIR
    chunks_path = config.INDEX_DIR / "chunks.jsonl"

    # 이미 존재하면 스킵 (force=True면 무시)
    if not force and output_dir.exists() and (output_dir / "meta.json").exists():
        with open(output_dir / "meta.json", "r") as f:
            meta = json.load(f)
        print(f"[SKIP] BM25 inverted index 이미 존재: {meta['N']}개 문서 → {output_dir}")
        return

    if not chunks_path.exists():
        print(f"[ERROR] chunks.jsonl 없음: {chunks_path}")
        sys.exit(1)

    print(f"[START] BM25 inverted index 빌드")
    print(f"  입력: {chunks_path}")
    print(f"  출력: {output_dir}")
    t0 = time.time()

    # ── Pass 1: 스트리밍으로 postings, doc_len, doc_map 구축 ──
    # postings: term → [(doc_id, tf), ...]
    postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
    doc_len: dict[int, int] = {}    # doc_id → 토큰 수
    doc_map: dict[int, str] = {}    # doc_id → chunk_id
    doc_id = 0

    print("  [1/3] chunks.jsonl 스트리밍 + 토크나이징...")
    with open(chunks_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f):
            line = line.strip()
            if not line:
                continue

            chunk = json.loads(line)
            chunk_id = chunk["chunk_id"]
            sparse_text = chunk.get("sparse_text", "")

            # sparse_text는 이미 extract_keywords_for_sparse()에서
            # kiwipiepy 토크나이징 + 중복 제거된 결과 → split()으로 충분
            tokens = sparse_text.split()

            # tf 계산 (토큰별 빈도)
            tf_map: dict[str, int] = defaultdict(int)
            for token in tokens:
                tf_map[token] += 1

            # postings에 추가
            for term, tf in tf_map.items():
                postings[term].append((doc_id, tf))

            # doc_len, doc_map 저장
            doc_len[doc_id] = len(tokens)
            doc_map[doc_id] = chunk_id

            doc_id += 1

            # 진행 로그 (10만 건마다)
            if (line_num + 1) % 100_000 == 0:
                elapsed = time.time() - t0
                print(f"    {line_num + 1:,}건 처리 ({elapsed:.0f}s, terms: {len(postings):,})")

    N = doc_id
    total_tokens = sum(doc_len.values())
    avg_doc_len = total_tokens / N if N > 0 else 0

    print(f"    완료: {N:,}개 문서, {len(postings):,}개 고유 term, avg_doc_len={avg_doc_len:.1f}")

    # ── Pass 2: idf 계산 (전체 corpus 기준) ──
    print("  [2/3] idf 계산 (전체 corpus 기준)...")
    idf: dict[str, float] = {}
    for term, posting_list in postings.items():
        df = len(posting_list)  # document frequency
        # BM25 Okapi idf: log((N - df + 0.5) / (df + 0.5))
        # rank_bm25 라이브러리와 동일한 공식
        idf_val = math.log((N - df + 0.5) / (df + 0.5))
        # 음수 idf 처리: df > N/2인 초고빈도 term은 0으로 (rank_bm25 동일)
        if idf_val < 0:
            idf_val = 0.0
        idf[term] = idf_val

    print(f"    완료: {len(idf):,}개 term idf 계산")

    # ── 저장 ──
    print("  [3/3] 파일 저장...")
    output_dir.mkdir(parents=True, exist_ok=True)

    # postings: 가장 큰 파일 → pickle (빠른 직렬화)
    with open(output_dir / "postings.pkl", "wb") as f:
        pickle.dump(dict(postings), f, protocol=pickle.HIGHEST_PROTOCOL)

    # idf: pickle (term 수가 많아 json보다 pkl이 효율적)
    with open(output_dir / "idf.pkl", "wb") as f:
        pickle.dump(idf, f, protocol=pickle.HIGHEST_PROTOCOL)

    # doc_len: pickle
    with open(output_dir / "doc_len.pkl", "wb") as f:
        pickle.dump(doc_len, f, protocol=pickle.HIGHEST_PROTOCOL)

    # doc_map: pickle
    with open(output_dir / "doc_map.pkl", "wb") as f:
        pickle.dump(doc_map, f, protocol=pickle.HIGHEST_PROTOCOL)

    # meta: JSON (사람이 읽을 수 있게)
    meta = {
        "N": N,
        "avg_doc_len": avg_doc_len,
        "total_tokens": total_tokens,
        "unique_terms": len(postings),
        "k1": config.BM25_K1,
        "b": config.BM25_B,
        "source": str(chunks_path),
        "build_time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(output_dir / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    elapsed = time.time() - t0
    print(f"[DONE] {elapsed:.0f}s -{output_dir}")
    print(f"  문서: {N:,}개")
    print(f"  고유 term: {len(postings):,}개")
    print(f"  avg_doc_len: {avg_doc_len:.1f}")

    # 파일 크기 출력
    for p in sorted(output_dir.iterdir()):
        size_mb = p.stat().st_size / 1024 / 1024
        print(f"  {p.name}: {size_mb:.1f}MB")


# ══════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════

if __name__ == "__main__":
    force = "--force" in sys.argv
    build(force=force)
