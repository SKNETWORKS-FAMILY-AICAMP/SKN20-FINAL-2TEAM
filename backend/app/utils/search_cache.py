"""검색 결과 임시 캐시.

search → analyze-patent 호출 사이에 검색 결과를 유지하기 위한
in-memory 캐시. TTL 10분, thread-safe.
"""

import time
from threading import Lock

_cache: dict[str, dict] = {}
_lock = Lock()
_TTL = 600  # 10분


def store(key: str, data: dict) -> None:
    with _lock:
        _cache[key] = {"data": data, "ts": time.time()}
        expired = [k for k, v in _cache.items() if time.time() - v["ts"] > _TTL]
        for k in expired:
            del _cache[k]


def get(key: str) -> dict | None:
    with _lock:
        entry = _cache.get(key)
        if entry and time.time() - entry["ts"] < _TTL:
            return entry["data"]
        return None


def delete(key: str) -> None:
    with _lock:
        _cache.pop(key, None)
