"""리트리버 — GPT/RunPod 버전.

원본: retriever.py
변경: dense_search()에서 KURE-v1 로컬 로드 대신 RunPod Serverless API 호출.
     나머지 함수(sparse_search, reciprocal_rank_fusion, patent_collapse)는 원본 그대로 사용.
"""
import os
import time
import requests

from .. import config
from .retriever import (
    sparse_search,
    reciprocal_rank_fusion,
    patent_collapse,
    _get_collection,
)

# ══════════════════════════════════════════════════════
# Dense 검색 (RunPod Serverless KURE-v1)
# ══════════════════════════════════════════════════════

_RUNPOD_API_KEY = os.environ.get("RUNPOD_API_KEY", "")
_RUNPOD_ENDPOINT_ID = os.environ.get("RUNPOD_ENDPOINT_ID", "")
_RUNPOD_BASE_URL = f"https://api.runpod.ai/v2/{_RUNPOD_ENDPOINT_ID}"
_HEADERS = {
    "Authorization": f"Bearer {_RUNPOD_API_KEY}",
    "Content-Type": "application/json",
}


def _get_embedding_from_runpod(text: str) -> list[float]:
    """RunPod Serverless로 KURE-v1 임베딩 요청. 콜드스타트 시 폴링."""
    if not _RUNPOD_API_KEY or not _RUNPOD_ENDPOINT_ID:
        raise RuntimeError(
            "RUNPOD_API_KEY 또는 RUNPOD_ENDPOINT_ID가 .env에 설정되지 않았습니다."
        )

    # 1) 비동기 요청 (/run)
    resp = requests.post(
        f"{_RUNPOD_BASE_URL}/run",
        headers=_HEADERS,
        json={"input": {"text": text}},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    job_id = data.get("id")

    if not job_id:
        raise RuntimeError(f"RunPod job ID 없음: {data}")

    # 2) 결과 폴링 (최대 5분)
    print(f"  [RunPod] 요청 전송 (job: {job_id}), 워커 대기 중...")
    for i in range(60):  # 5초 × 60 = 최대 300초
        time.sleep(5)
        status_resp = requests.get(
            f"{_RUNPOD_BASE_URL}/status/{job_id}",
            headers=_HEADERS,
            timeout=30,
        )
        status_resp.raise_for_status()
        status_data = status_resp.json()
        status = status_data.get("status")

        if status == "COMPLETED":
            output = status_data.get("output", {})
            embedding = output.get("embedding")
            if embedding is None:
                raise RuntimeError(f"RunPod 응답에 embedding 없음: {status_data}")
            print(f"  [RunPod] 임베딩 완료 ({(i+1)*5}초)")
            return embedding
        elif status == "FAILED":
            raise RuntimeError(f"RunPod 작업 실패: {status_data}")
        elif status in ("IN_QUEUE", "IN_PROGRESS"):
            if i % 6 == 0:  # 30초마다 상태 출력
                print(f"  [RunPod] 상태: {status} ({(i+1)*5}초 경과)")
            continue
        else:
            raise RuntimeError(f"RunPod 알 수 없는 상태: {status_data}")

    raise RuntimeError("RunPod 응답 타임아웃 (5분 초과)")


def dense_search(
    query: str,
    top_k: int = None,
    allowed_chunk_ids: list[str] = None,
) -> list[tuple[str, float, dict]]:
    """Dense 검색. RunPod KURE-v1로 임베딩 후 ChromaDB에서 검색.

    원본 retriever.py와 동일한 인터페이스.
    """
    top_k = top_k or config.DENSE_TOP_K
    col = _get_collection()

    print(f"  [ChromaDB] 컬렉션: {config.CHROMA_COLLECTION}, 문서 수: {col.count():,}")

    # RunPod API로 쿼리 임베딩
    query_embedding = _get_embedding_from_runpod(query)

    # 사전필터링: allowed_chunk_ids가 있으면 해당 청크만 검색
    where_filter = None
    if allowed_chunk_ids is not None:
        patent_ids = list(set(
            cid.split("_claim_")[0] for cid in allowed_chunk_ids
        ))
        print(f"  [ChromaDB] where 필터: {len(patent_ids)}개 특허")
        where_filter = {"apply_num": {"$in": patent_ids}}

    n_results = min(top_k, col.count())
    if n_results <= 0:
        print("  [ChromaDB] n_results=0, 빈 결과 반환")
        return []

    # ChromaDB에서 cosine distance 기준 top-k 검색
    results = col.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        include=["distances", "metadatas"],
        where=where_filter,
    )

    # (chunk_id, distance, metadata) 튜플 리스트로 변환
    pairs = []
    for cid, dist, meta in zip(
        results["ids"][0], results["distances"][0], results["metadatas"][0]
    ):
        pairs.append((cid, dist, meta))
    return pairs
