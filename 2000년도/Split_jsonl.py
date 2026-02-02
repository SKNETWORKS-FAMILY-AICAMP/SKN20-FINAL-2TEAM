from __future__ import annotations

import argparse
import json
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd

# -------------------------
# Logging 설정
# -------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# -------------------------
# Type Aliases
# -------------------------
JsonDict = Dict[str, Any]
Embedding = List[float]


# -------------------------
# Helpers
# -------------------------
def _safe_json_loads(s: Any) -> Any:
    """metadata/document가 문자열 JSON으로 들어온 경우도 안전하게 처리."""
    if not isinstance(s, str):
        return s
    ss = s.strip()
    if not (ss.startswith("{") or ss.startswith("[")):
        return s
    try:
        return json.loads(ss)
    except json.JSONDecodeError:
        return s


def _pick_id(obj: JsonDict, line_num: int) -> Tuple[str, bool]:
    """
    ID를 추출하거나 생성합니다.
    
    Returns:
        Tuple[str, bool]: (id값, 자동생성여부)
    """
    # 직접 키에서 찾기
    for k in ("id", "image_id", "doc_id", "design_id"):
        v = obj.get(k)
        if v is not None:
            return str(v), False
    
    # metadata 내부에서 찾기
    m = obj.get("metadata")
    if isinstance(m, dict):
        for k in ("id", "image_id", "doc_id", "design_id"):
            v = m.get(k)
            if v is not None:
                return str(v), False
    
    # ID 없으면 자동 생성 (line number + short uuid)
    generated_id = f"auto_{line_num}_{uuid.uuid4().hex[:8]}"
    return generated_id, True


def _flatten_metadata(meta: JsonDict, prefix: str = "") -> JsonDict:
    """metadata를 1-depth 컬럼으로 평탄화 (XGBoost/Pandas 친화)."""
    out: JsonDict = {}
    for k, v in meta.items():
        kk = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(_flatten_metadata(v, kk))
        else:
            out[kk] = v
    return out


def _validate_embedding(emb: Any) -> Optional[Embedding]:
    """
    embedding이 유효한 float 리스트인지 검증합니다.
    
    Returns:
        Optional[Embedding]: 유효하면 리스트, 아니면 None
    """
    if emb is None:
        return None
    
    if not isinstance(emb, list):
        return None
    
    if len(emb) == 0:
        return None
    
    # 첫 번째와 마지막 요소만 체크 (성능상)
    if not all(isinstance(x, (int, float)) for x in [emb[0], emb[-1]]):
        return None
    
    return emb


def split_one_record(
    rec: JsonDict,
    line_num: int
) -> Tuple[
    Optional[JsonDict],
    Optional[JsonDict],
    Optional[JsonDict],
    bool  # ID 자동생성 여부
]:
    """
    단일 레코드를 document, metadata, embedding으로 분리합니다.
    
    Args:
        rec: 원본 JSON 레코드
        line_num: 라인 번호 (ID 자동생성 시 사용)
    
    Returns:
        Tuple of (doc_row, meta_row, emb_row, id_was_generated)
    """
    rid, id_generated = _pick_id(rec, line_num)

    document = _safe_json_loads(rec.get("document"))
    metadata = _safe_json_loads(rec.get("metadata"))
    raw_embedding = rec.get("embedding") or rec.get("embeddings")
    embedding = _validate_embedding(raw_embedding)

    doc_row: Optional[JsonDict] = None
    if document is not None:
        doc_row = {"id": rid, "document": document}

    meta_row: Optional[JsonDict] = None
    if isinstance(metadata, dict):
        flat = _flatten_metadata(metadata)
        flat["id"] = rid
        meta_row = flat

    emb_row: Optional[JsonDict] = None
    if embedding is not None:
        emb_row = {"id": rid, "embedding": embedding}

    return doc_row, meta_row, emb_row, id_generated


class ProgressTracker:
    """진행 상황 추적 및 출력"""
    
    def __init__(self, log_interval: int = 10000):
        self.log_interval = log_interval
        self.n_total = 0
        self.n_doc = 0
        self.n_meta = 0
        self.n_emb = 0
        self.n_id_generated = 0
        self.n_parse_errors = 0
        self.n_invalid_embeddings = 0
    
    def update(
        self,
        has_doc: bool = False,
        has_meta: bool = False,
        has_emb: bool = False,
        id_generated: bool = False
    ) -> None:
        self.n_total += 1
        if has_doc:
            self.n_doc += 1
        if has_meta:
            self.n_meta += 1
        if has_emb:
            self.n_emb += 1
        if id_generated:
            self.n_id_generated += 1
        
        # 진행 상황 로깅
        if self.n_total % self.log_interval == 0:
            self._log_progress()
    
    def record_parse_error(self) -> None:
        self.n_parse_errors += 1
        self.n_total += 1
    
    def record_invalid_embedding(self) -> None:
        self.n_invalid_embeddings += 1
    
    def _log_progress(self) -> None:
        logger.info(
            f"Progress: {self.n_total:,} lines processed | "
            f"docs: {self.n_doc:,}, meta: {self.n_meta:,}, emb: {self.n_emb:,}"
        )
    
    def summary(self) -> str:
        lines = [
            "=" * 50,
            "Processing Summary",
            "=" * 50,
            f"Total lines processed : {self.n_total:,}",
            f"  - Documents         : {self.n_doc:,}",
            f"  - Metadata          : {self.n_meta:,}",
            f"  - Embeddings        : {self.n_emb:,}",
            "-" * 50,
            f"Auto-generated IDs    : {self.n_id_generated:,}",
            f"Parse errors (skipped): {self.n_parse_errors:,}",
            f"Invalid embeddings    : {self.n_invalid_embeddings:,}",
            "=" * 50,
        ]
        return "\n".join(lines)


def process_jsonl(
    in_path: Path,
    out_dir: Path,
    save_csv: bool = False,
    log_interval: int = 10000
) -> ProgressTracker:
    """
    JSONL 파일을 처리하여 document, metadata, embedding으로 분리합니다.
    
    Args:
        in_path: 입력 JSONL 파일 경로
        out_dir: 출력 디렉토리
        save_csv: metadata를 CSV로도 저장할지 여부
        log_interval: 진행 상황 로깅 간격
    
    Returns:
        ProgressTracker: 처리 통계
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    docs_path = out_dir / "documents.jsonl"
    meta_parquet_path = out_dir / "metadata.parquet"
    meta_csv_path = out_dir / "metadata.csv"

    tracker = ProgressTracker(log_interval=log_interval)
    meta_rows: List[JsonDict] = []

    logger.info(f"Starting processing: {in_path}")
    logger.info(f"Output directory: {out_dir}")

    with (
        in_path.open("r", encoding="utf-8") as fin,
        docs_path.open("w", encoding="utf-8") as fdoc
    ):
        for line_num, line in enumerate(fin, start=1):
            line = line.strip()
            if not line:
                continue
            
            # JSON 파싱 에러 처리
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                logger.warning(f"Line {line_num}: JSON parse error - {e}")
                tracker.record_parse_error()
                continue

            doc_row, meta_row, emb_row, id_generated = split_one_record(rec, line_num)
            
            # embedding 유효성 체크 로깅
            raw_emb = rec.get("embedding") or rec.get("embeddings")
            if raw_emb is not None and emb_row is None:
                logger.debug(f"Line {line_num}: Invalid embedding format")
                tracker.record_invalid_embedding()

            if doc_row is not None:
                fdoc.write(json.dumps(doc_row, ensure_ascii=False) + "\n")

            if meta_row is not None:
                meta_rows.append(meta_row)

            tracker.update(
                has_doc=doc_row is not None,
                has_meta=meta_row is not None,
                has_emb=emb_row is not None,
                id_generated=id_generated
            )

    # metadata 저장
    if meta_rows:
        df = pd.DataFrame(meta_rows)
        df.to_parquet(meta_parquet_path, index=False)
        logger.info(f"Saved metadata to: {meta_parquet_path}")
        
        if save_csv:
            df.to_csv(meta_csv_path, index=False, encoding="utf-8-sig")
            logger.info(f"Saved metadata CSV to: {meta_csv_path}")

    return tracker


def main() -> None:
    ap = argparse.ArgumentParser(
        description="JSONL 파일에서 document, metadata, embedding을 분리합니다."
    )
    ap.add_argument("--in_jsonl", type=str, required=True, help="입력 JSONL 파일 경로")
    ap.add_argument("--out_dir", type=str, required=True, help="출력 디렉토리")
    ap.add_argument("--save_csv", action="store_true", help="metadata를 CSV로도 저장")
    ap.add_argument(
        "--log_interval",
        type=int,
        default=10000,
        help="진행 상황 로깅 간격 (기본: 10000)"
    )
    ap.add_argument(
        "--verbose",
        action="store_true",
        help="상세 로깅 (DEBUG 레벨)"
    )
    args = ap.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    in_path = Path(args.in_jsonl)
    out_dir = Path(args.out_dir)

    if not in_path.exists():
        logger.error(f"Input file not found: {in_path}")
        return

    tracker = process_jsonl(
        in_path=in_path,
        out_dir=out_dir,
        save_csv=args.save_csv,
        log_interval=args.log_interval
    )

    print(tracker.summary())


if __name__ == "__main__":
    main()