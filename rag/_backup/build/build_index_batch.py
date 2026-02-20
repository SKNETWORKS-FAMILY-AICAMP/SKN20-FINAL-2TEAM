"""대규모 데이터용 배치 인덱스 빌더.

78k+ 파일을 배치 단위로 처리하여 메모리 안정성을 확보합니다.

Phase 1: 청크 생성 (배치 → JSONL 스트리밍 저장)
Phase 2: claims_db 생성
Phase 3: Dense 인덱스 (JSONL에서 배치 읽기 → 임베딩 → ChromaDB)
Phase 4: Sparse 인덱스 (JSONL에서 sparse_text만 읽기 → BM25)

Usage:
    # rag 폴더의 상위 디렉토리에서 실행
    python -m rag.build.build_index_batch --data-dir "/workspace/json's"
"""
import argparse
import gc
import json
import os
import pickle
from pathlib import Path

import numpy as np

from .. import config

CHUNK_BATCH = 5000          # 파일 N개씩 청크 생성
EMBED_BATCH = 2000          # 청크 N개씩 임베딩
CHROMA_INSERT_BATCH = 5000  # ChromaDB 삽입 배치
JSONL_PATH = config.INDEX_DIR / "chunks.jsonl"


# ── Phase 1: 청크 생성 (배치 스트리밍) ─────────────────

def phase1_chunks(data_dir: Path):
    """파일을 배치로 나눠 청크 생성 → JSONL로 스트리밍 저장."""
    from .chunker import build_chunks_from_patent
    import re

    files = sorted(data_dir.glob("*.json"))
    total = len(files)
    print(f"[Phase 1] 청크 생성: {total}개 파일 → {JSONL_PATH}")

    config.INDEX_DIR.mkdir(parents=True, exist_ok=True)
    chunk_count = 0
    warn_count = 0

    # 파일을 순회하며 청크를 JSONL로 스트리밍 저장 (메모리에 전체를 올리지 않음)
    with open(JSONL_PATH, "w", encoding="utf-8") as out:
        for i, fp in enumerate(files):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                claims_section = data.get("claims", {})
                app_num = claims_section.get("application_number", "")
                if not app_num:
                    # 파일명에서 숫자만 추출하여 출원번호로 사용
                    app_num = re.sub(r"[^0-9]", "", fp.stem)

                chunks = build_chunks_from_patent(data, app_num)
                for c in chunks:
                    out.write(json.dumps(c, ensure_ascii=False) + "\n")
                chunk_count += len(chunks)
            except Exception as e:
                warn_count += 1
                if warn_count <= 10:
                    print(f"  [WARN] {fp.name}: {e}")

            # 배치 단위마다 플러시 + GC로 메모리 안정화
            if (i + 1) % CHUNK_BATCH == 0:
                out.flush()
                gc.collect()
                print(f"  {i+1}/{total} 파일 처리 ({chunk_count}개 청크)")

    # JSONL → chunks.json 변환 (다른 모듈 호환용)
    print(f"\n  총 {chunk_count}개 청크 생성 (경고 {warn_count}건)")
    print(f"  chunks.json 변환 중...")
    chunks_list = []
    with open(JSONL_PATH, "r", encoding="utf-8") as f:
        for line in f:
            chunks_list.append(json.loads(line))
    with open(config.CHUNKS_PATH, "w", encoding="utf-8") as f:
        json.dump(chunks_list, f, ensure_ascii=False, indent=2)
    del chunks_list
    gc.collect()
    print(f"  chunks.json 저장 완료: {chunk_count}개")
    return chunk_count


# ── Phase 2: claims_db 생성 ────────────────────────────

def phase2_claims_db(data_dir: Path):
    """claims_db.json 생성 (kiwipiepy 미사용, 안전)."""
    from .chunker import build_claims_db
    print(f"\n[Phase 2] claims_db 생성...")
    n = build_claims_db(data_dir, config.CLAIMS_DB_PATH)
    return n


# ── Phase 3 헬퍼: 리소스 관리 ──────────────────────────

def _load_checkpoint() -> dict | None:
    """체크포인트 JSON 로드. 없거나 유효하지 않으면 None. (Phase 3 이어쓰기용)"""
    cp = config.CHECKPOINT_PATH
    if not cp.exists():
        return None
    try:
        with open(cp, "r") as f:
            data = json.load(f)
        if "next_line" in data and "embedded_count" in data:
            return data
    except Exception as e:
        print(f"  [WARN] 체크포인트 로드 실패: {e}")
    return None


def _save_checkpoint(next_line: int, embedded_count: int,
                     pending_ids: list[str] | None = None,
                     batch_start_line: int = 0):
    """체크포인트 원자적 저장 (tmp → rename). 중단 후 재시작 시 복원 지점."""
    cp = config.CHECKPOINT_PATH
    tmp = cp.with_suffix(".json.tmp")
    data = {
        "next_line": next_line,
        "embedded_count": embedded_count,
        "batch_start_line": batch_start_line,
    }
    if pending_ids:
        data["pending_ids"] = pending_ids
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(str(tmp), str(cp))


def _get_vram_usage() -> tuple[float, float, float]:
    """(사용GB, 여유GB, 전체GB) 반환."""
    import torch
    free, total = torch.cuda.mem_get_info()
    free_gb = free / (1024 ** 3)
    total_gb = total / (1024 ** 3)
    used_gb = total_gb - free_gb
    return used_gb, free_gb, total_gb


def _adjust_batch_size_by_vram(base_bs: int, max_text_len: int) -> int:
    """VRAM 사용률 기반 배치 사이즈 동적 조절."""
    used_gb, free_gb, total_gb = _get_vram_usage()
    usage = used_gb / total_gb if total_gb > 0 else 0

    bs = base_bs
    if usage > config.VRAM_DANGER_USAGE:
        bs = max(config.EMBED_BS_MIN, base_bs // 2)
    elif usage < 0.70:
        bs = min(config.EMBED_BS_MAX, int(base_bs * 1.5))

    # 초장문 안전장치
    if max_text_len > 3000:
        bs = min(bs, 32)
    elif max_text_len > 2000:
        bs = min(bs, 64)

    return max(config.EMBED_BS_MIN, bs)


def _safe_encode(model, texts: list[str], batch_size: int):
    """OOM 방어 인코딩. 실패 시 배치 절반 → 최후 CPU 폴백."""
    import torch

    bs = batch_size
    while bs >= config.EMBED_BS_MIN:
        try:
            return model.encode(texts, batch_size=bs, device="cuda",
                                normalize_embeddings=False)
        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache()
            gc.collect()
            old_bs = bs
            bs = max(config.EMBED_BS_MIN, bs // 2)
            print(f"  [OOM] batch_size {old_bs} → {bs}")
            if bs == old_bs:
                break

    # 최후: 1개씩, GPU 실패 시 CPU
    print(f"  [OOM] 단건 인코딩 폴백")
    results = []
    for text in texts:
        try:
            emb = model.encode([text], batch_size=1, device="cuda",
                               normalize_embeddings=False)
            results.append(emb[0])
        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache()
            gc.collect()
            print(f"  [OOM] CPU 폴백 (len={len(text)})")
            emb = model.encode([text], batch_size=1, device="cpu",
                               normalize_embeddings=False)
            results.append(emb[0])
    return np.array(results)


def _check_ram_and_gc():
    """시스템 RAM 위험 시 GC 실행."""
    try:
        with open("/proc/meminfo", "r") as f:
            info = {}
            for line in f:
                parts = line.split()
                if parts[0] in ("MemTotal:", "MemAvailable:"):
                    info[parts[0]] = int(parts[1])
        total = info.get("MemTotal:", 0)
        avail = info.get("MemAvailable:", 0)
        if total > 0:
            usage = 1.0 - (avail / total)
            if usage > config.RAM_DANGER_USAGE:
                print(f"  [RAM] {usage:.0%} 사용 → GC 실행")
                gc.collect()
    except Exception:
        pass


# ── Phase 3: Dense 인덱스 (배치 임베딩) ────────────────

def phase3_dense():
    """JSONL에서 배치로 읽어 임베딩 → ChromaDB 저장. 체크포인트 이어쓰기 지원."""
    import torch
    import chromadb
    from chromadb.config import Settings
    from sentence_transformers import SentenceTransformer
    from tqdm import tqdm

    print(f"\n[Phase 3] Dense 인덱스 (KURE-v1 → ChromaDB)")

    model = SentenceTransformer(config.EMBED_MODEL)
    client = chromadb.PersistentClient(
        path=str(config.CHROMA_DIR),
        settings=Settings(anonymized_telemetry=False),
    )

    # ── 체크포인트 로드 ──
    checkpoint = _load_checkpoint()
    start_line = 0

    if checkpoint is not None:
        start_line = checkpoint["next_line"]
        expected_count = checkpoint["embedded_count"]
        collection = client.get_or_create_collection(
            name=config.CHROMA_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        actual_count = collection.count()
        print(f"  [RESUME] 체크포인트: line {start_line}, "
              f"DB {actual_count}개 (expected {expected_count})")

        # 부분 삽입 복구
        if checkpoint.get("pending_ids") and actual_count < expected_count:
            print(f"  [RESUME] 부분 삽입 감지 → 롤백")
            try:
                collection.delete(ids=checkpoint["pending_ids"])
            except Exception:
                pass
            start_line = checkpoint.get("batch_start_line", start_line)
            print(f"  [RESUME] line {start_line}부터 재처리")
    else:
        # 새로 시작: 컬렉션 삭제 후 재생성
        try:
            client.delete_collection(config.CHROMA_COLLECTION)
        except Exception:
            pass
        collection = client.get_or_create_collection(
            name=config.CHROMA_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        print(f"  새 인덱스 생성")

    # JSONL 줄 수 카운트
    total_lines = 0
    with open(JSONL_PATH, "r", encoding="utf-8") as f:
        for _ in f:
            total_lines += 1
    remaining = total_lines - start_line
    print(f"  총 {total_lines}개 중 {remaining}개 임베딩 예정 (skip {start_line})")

    batch_texts = []
    batch_ids = []
    batch_metas = []
    inserted = collection.count()
    batch_start_line = start_line

    pbar = tqdm(total=remaining, desc="Embedding+Insert")

    with open(JSONL_PATH, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f):
            if line_no < start_line:
                continue

            chunk = json.loads(line)
            batch_texts.append(chunk["dense_text"])
            batch_ids.append(chunk["chunk_id"])
            meta = {k: v for k, v in chunk["metadata"].items()
                    if isinstance(v, (str, int, float, bool))}
            meta["ipc"] = ", ".join(chunk["metadata"].get("ipc", []))
            meta["dep_claim_nums"] = json.dumps(
                chunk["metadata"].get("dep_claim_nums", []))
            batch_metas.append(meta)

            if len(batch_texts) >= EMBED_BATCH:
                # 삽입 전 체크포인트 (pending_ids 포함)
                _save_checkpoint(
                    next_line=batch_start_line,
                    embedded_count=inserted,
                    pending_ids=batch_ids[:],
                    batch_start_line=batch_start_line,
                )

                _embed_and_insert(model, collection,
                                  batch_texts, batch_ids, batch_metas)
                inserted += len(batch_texts)
                pbar.update(len(batch_texts))

                # 삽입 후 체크포인트 (완료 확정)
                next_line = line_no + 1
                _save_checkpoint(
                    next_line=next_line,
                    embedded_count=inserted,
                    batch_start_line=next_line,
                )
                batch_start_line = next_line

                batch_texts, batch_ids, batch_metas = [], [], []
                _check_ram_and_gc()
                torch.cuda.empty_cache()
                gc.collect()

                # 리소스 현황 로그
                used, free, total = _get_vram_usage()
                print(f"  [{inserted}/{total_lines}] "
                      f"VRAM {used:.1f}/{total:.1f}GB ({used/total:.0%})")

    # 남은 배치 처리
    if batch_texts:
        _embed_and_insert(model, collection,
                          batch_texts, batch_ids, batch_metas)
        inserted += len(batch_texts)
        pbar.update(len(batch_texts))

    pbar.close()

    # 최종 체크포인트
    _save_checkpoint(
        next_line=total_lines,
        embedded_count=inserted,
        batch_start_line=total_lines,
    )

    count = collection.count()
    print(f"  ChromaDB 저장 완료: {count}개 문서")
    del model
    torch.cuda.empty_cache()
    gc.collect()
    return count


def _embed_and_insert(model, collection, texts, ids, metas):
    """배치 임베딩 후 ChromaDB 삽입. 동적 배치 + OOM 방어."""
    import torch

    # 텍스트 길이순 정렬 → 비슷한 길이끼리 배치하여 패딩 낭비 최소화
    sorted_indices = sorted(range(len(texts)), key=lambda i: len(texts[i]))
    sorted_texts = [texts[i] for i in sorted_indices]

    all_sorted_embs = []
    i = 0
    while i < len(sorted_texts):
        max_len = len(sorted_texts[min(i + config.EMBED_BATCH_SIZE - 1,
                                       len(sorted_texts) - 1)])
        # 텍스트 길이별 배치 사이즈 휴리스틱 (RTX 5090 32GB 기준)
        if max_len > 3000:
            bs = 32
        elif max_len > 2000:
            bs = 64
        elif max_len > 1000:
            bs = 128
        else:
            bs = 256

        # 실시간 VRAM 사용률 기반 동적 조절
        bs = _adjust_batch_size_by_vram(bs, max_len)
        bs = min(bs, len(sorted_texts) - i)

        batch = sorted_texts[i:i + bs]
        embs = _safe_encode(model, batch, bs)
        all_sorted_embs.extend(embs.tolist())
        i += bs
        torch.cuda.empty_cache()

    # 정렬된 임베딩을 원래 청크 순서로 복원
    all_embs = [None] * len(texts)
    for new_idx, orig_idx in enumerate(sorted_indices):
        all_embs[orig_idx] = all_sorted_embs[new_idx]

    # ChromaDB에 배치 upsert (이미 존재하면 덮어쓰기)
    for ci in range(0, len(all_embs), CHROMA_INSERT_BATCH):
        end = min(ci + CHROMA_INSERT_BATCH, len(all_embs))
        collection.upsert(
            ids=ids[ci:end],
            embeddings=all_embs[ci:end],
            metadatas=metas[ci:end],
            documents=texts[ci:end],
        )


# ── Phase 4: Sparse 인덱스 (BM25) ─────────────────────

def phase4_sparse():
    """JSONL에서 sparse_text만 읽어 BM25 빌드."""
    from rank_bm25 import BM25Okapi
    from ..search.retriever import morpheme_tokenize

    print(f"\n[Phase 4] Sparse 인덱스 (BM25)")

    chunk_ids = []
    tokenized = []
    count = 0

    with open(JSONL_PATH, "r", encoding="utf-8") as f:
        for line in f:
            chunk = json.loads(line)
            chunk_ids.append(chunk["chunk_id"])
            tokens = morpheme_tokenize(chunk["sparse_text"])
            tokenized.append(tokens)
            count += 1
            if count % 10000 == 0:
                print(f"  {count}개 토크나이징 완료")

    print(f"  총 {count}개 토크나이징 → BM25 빌드 중...")
    bm25 = BM25Okapi(tokenized, k1=config.BM25_K1, b=config.BM25_B)

    config.BM25_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(config.BM25_PATH, "wb") as f:
        pickle.dump({"bm25": bm25, "chunk_ids": chunk_ids}, f)

    print(f"  BM25 저장 완료: {count}개 문서 → {config.BM25_PATH}")
    return count


# ── 증분 업데이트 (Incremental) ────────────────────────

def _load_processed_files() -> set[str]:
    """처리 완료된 파일명 set 로드. 없으면 JSONL에서 자동 생성."""
    cp = config.PROCESSED_FILES_PATH
    if cp.exists():
        with open(cp, "r") as f:
            return set(json.load(f))

    # 최초: 기존 JSONL에서 apply_num 기반 파일명 추출
    processed = set()
    if JSONL_PATH.exists():
        with open(JSONL_PATH, "r", encoding="utf-8") as f:
            for line in f:
                chunk = json.loads(line)
                app_num = chunk["metadata"].get("apply_num", "")
                if app_num:
                    processed.add(app_num)
        # 저장
        _save_processed_files(processed)
        print(f"  [증분] 기존 JSONL에서 {len(processed)}개 파일 ID 추출 → processed_files.json 생성")
    return processed


def _save_processed_files(processed: set[str]):
    """처리 완료 파일 목록 저장."""
    cp = config.PROCESSED_FILES_PATH
    tmp = cp.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(sorted(processed), f)
    os.replace(str(tmp), str(cp))


def incremental_update(data_dir: Path):
    """증분 업데이트: 새 파일만 감지 → 청킹 → 임베딩 → DB 추가 → BM25 전체 재빌드."""
    import re
    import torch
    import chromadb
    from chromadb.config import Settings
    from sentence_transformers import SentenceTransformer
    from tqdm import tqdm
    from .chunker import build_chunks_from_patent, build_claims_db

    print(f"\n{'='*60}")
    print(f"증분 업데이트 (Incremental)")
    print(f"  데이터: {data_dir}")
    print(f"{'='*60}\n")

    # 1. 처리 완료 목록 로드
    processed = _load_processed_files()
    print(f"  기존 처리 완료: {len(processed)}개 파일")

    # 2. 새 파일 필터링
    all_files = sorted(data_dir.glob("*.json"))
    new_files = []
    for fp in all_files:
        app_num = re.sub(r"[^0-9]", "", fp.stem)
        if app_num not in processed:
            new_files.append((fp, app_num))

    if not new_files:
        print(f"  새 파일 없음. 증분 업데이트 불필요.")
        return 0

    print(f"  새 파일 발견: {len(new_files)}개")

    # 3. 청킹 → JSONL append
    new_chunks = []
    warn_count = 0
    with open(JSONL_PATH, "a", encoding="utf-8") as out:
        for fp, app_num in new_files:
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                claims_section = data.get("claims", {})
                file_app_num = claims_section.get("application_number", "")
                if not file_app_num:
                    file_app_num = app_num

                chunks = build_chunks_from_patent(data, file_app_num)
                for c in chunks:
                    out.write(json.dumps(c, ensure_ascii=False) + "\n")
                    new_chunks.append(c)
            except Exception as e:
                warn_count += 1
                if warn_count <= 10:
                    print(f"  [WARN] {fp.name}: {e}")

    print(f"  {len(new_chunks)}개 새 청크 생성 (경고 {warn_count}건)")

    if not new_chunks:
        print(f"  새 청크 없음.")
        return 0

    # 4. Dense 임베딩 → ChromaDB upsert
    print(f"\n  Dense 임베딩 중...")
    model = SentenceTransformer(config.EMBED_MODEL)
    client = chromadb.PersistentClient(
        path=str(config.CHROMA_DIR),
        settings=Settings(anonymized_telemetry=False),
    )
    collection = client.get_or_create_collection(
        name=config.CHROMA_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )

    # 배치 처리
    batch_texts, batch_ids, batch_metas = [], [], []
    inserted = 0
    pbar = tqdm(total=len(new_chunks), desc="Incremental Embed")

    for chunk in new_chunks:
        batch_texts.append(chunk["dense_text"])
        batch_ids.append(chunk["chunk_id"])
        meta = {k: v for k, v in chunk["metadata"].items()
                if isinstance(v, (str, int, float, bool))}
        meta["ipc"] = ", ".join(chunk["metadata"].get("ipc", []))
        meta["dep_claim_nums"] = json.dumps(
            chunk["metadata"].get("dep_claim_nums", []))
        batch_metas.append(meta)

        if len(batch_texts) >= EMBED_BATCH:
            _embed_and_insert(model, collection,
                              batch_texts, batch_ids, batch_metas)
            inserted += len(batch_texts)
            pbar.update(len(batch_texts))
            batch_texts, batch_ids, batch_metas = [], [], []
            _check_ram_and_gc()
            torch.cuda.empty_cache()
            gc.collect()

    if batch_texts:
        _embed_and_insert(model, collection,
                          batch_texts, batch_ids, batch_metas)
        inserted += len(batch_texts)
        pbar.update(len(batch_texts))

    pbar.close()
    del model
    torch.cuda.empty_cache()
    gc.collect()

    print(f"  ChromaDB: {collection.count()}개 문서 (신규 {inserted}개)")

    # 5. claims_db 갱신
    print(f"\n  claims_db 갱신 중...")
    build_claims_db(data_dir, config.CLAIMS_DB_PATH)

    # 6. BM25 전체 재빌드
    print(f"\n  BM25 재빌드 중...")
    phase4_sparse()

    # 7. processed_files 갱신
    for _, app_num in new_files:
        processed.add(app_num)
    _save_processed_files(processed)

    print(f"\n{'='*60}")
    print(f"증분 업데이트 완료!")
    print(f"  신규 파일: {len(new_files)}개")
    print(f"  신규 청크: {inserted}개")
    print(f"  전체 DB: {collection.count()}개")
    print(f"{'='*60}")
    return inserted


# ── Main ───────────────────────────────────────────────

def main():
    """CLI 진입점. Phase 1~4 순차 실행 또는 증분 모드 선택."""
    parser = argparse.ArgumentParser(description="대규모 배치 인덱스 빌더")
    parser.add_argument("--data-dir", type=str, required=True)
    parser.add_argument("--skip-chunks", action="store_true", help="Phase 1 스킵 (JSONL 이미 있을 때)")
    parser.add_argument("--skip-claims", action="store_true", help="Phase 2 스킵")
    parser.add_argument("--skip-dense", action="store_true", help="Phase 3 스킵")
    parser.add_argument("--skip-sparse", action="store_true", help="Phase 4 스킵")
    parser.add_argument("--fresh-dense", action="store_true",
                        help="Phase 3 체크포인트 삭제 후 처음부터")
    parser.add_argument("--incremental", action="store_true",
                        help="증분 모드 (새 파일만 처리)")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.is_absolute():
        data_dir = config.PROJECT_DIR / data_dir

    # 증분 모드
    if args.incremental:
        incremental_update(data_dir)
        return

    print(f"{'='*60}")
    print(f"대규모 배치 인덱스 빌드")
    print(f"  데이터: {data_dir}")
    print(f"  인덱스: {config.INDEX_DIR}")
    print(f"  JSONL: {JSONL_PATH}")
    print(f"{'='*60}\n")

    n_chunks = 0
    n_patents = 0
    n_dense = 0
    n_sparse = 0

    if not args.skip_chunks:
        n_chunks = phase1_chunks(data_dir)
    else:
        print("[Phase 1] 스킵")

    if not args.skip_claims:
        n_patents = phase2_claims_db(data_dir)
    else:
        print("[Phase 2] 스킵")

    if not args.skip_dense:
        if args.fresh_dense:
            if config.CHECKPOINT_PATH.exists():
                config.CHECKPOINT_PATH.unlink()
                print("  체크포인트 삭제됨 → 처음부터 시작")
        n_dense = phase3_dense()
    else:
        print("[Phase 3] 스킵")

    if not args.skip_sparse:
        n_sparse = phase4_sparse()
    else:
        print("[Phase 4] 스킵")

    print(f"\n{'='*60}")
    print(f"빌드 완료!")
    print(f"  청크: {n_chunks}")
    print(f"  특허(claims_db): {n_patents}")
    print(f"  Dense: {n_dense}")
    print(f"  Sparse: {n_sparse}")
    print(f"{'='*60}")

    # JSONL 정리
    if JSONL_PATH.exists():
        print(f"  (JSONL 보존: {JSONL_PATH})")


if __name__ == "__main__":
    main()
