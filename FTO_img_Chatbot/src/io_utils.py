from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

import numpy as np


def read_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    """JSONL 파일을 한 줄씩 읽어 dict로 yield."""
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def build_index_by_key(jsonl_path: Path, key_field: str) -> Dict[str, Dict[str, Any]]:
    """JSONL을 읽어 key_field 기준 dict 인덱스 생성."""
    idx: Dict[str, Dict[str, Any]] = {}
    for obj in read_jsonl(jsonl_path):
        k = obj.get(key_field)
        if k is not None:
            idx[str(k)] = obj
    return idx


def load_embeddings_npz(npz_path: Path) -> Tuple[np.ndarray, np.ndarray]:
    """
    NPZ에서 ids와 embeddings 로드.
    기대 형식:
    - ids: (N,) string or bytes
    - embeddings: (N, D) float32/float16 (키: 'embeddings' 또는 'image_embeddings')
    """
    data = np.load(npz_path, allow_pickle=True)

    if "ids" not in data:
        raise KeyError("NPZ must contain key: 'ids'")
    
    # embeddings 키 호환성 처리 (embeddings 또는 image_embeddings)
    if "embeddings" in data:
        emb = data["embeddings"]
    elif "image_embeddings" in data:
        emb = data["image_embeddings"]
    else:
        raise KeyError("NPZ must contain key: 'embeddings' or 'image_embeddings'")

    ids = data["ids"]

    # bytes -> str 변환
    if ids.dtype.kind in ("S", "O"):
        ids = np.array(
            [x.decode("utf-8") if isinstance(x, (bytes, bytearray)) else str(x) for x in ids],
            dtype=object,
        )

    emb = emb.astype(np.float32, copy=False)
    return ids, emb