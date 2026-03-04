"""RDB 필터링: 등록 상태 확인 + 데이터 보강.

하는 일:
    검색 결과에 대해 후처리를 수행합니다:
    1. 등록 상태 필터: 허용 상태가 아닌 특허 제거
    2. 데이터 보강: 메타데이터 + 청구항 원문 + 청크 구조 정보 추가

    데이터 소스:
    - ParentDB: parents.sqlite (78,520건 — 메타데이터 + 청구항 원문 통합)

관계:
    - pipeline.py가 search/retriever.py의 patent_collapse() 결과를 받아 apply_rdb_filter() 호출
"""
import json
import re
import sqlite3
from pathlib import Path

from .. import config

try:
    from app.logger import logger as _logger
except ImportError:
    import logging as _logging
    _logger = _logging.getLogger(__name__)


# ── config에서 단어사전 로드 → compile ──────
_JOSA_1 = re.compile(config.JOSA_PATTERN)
_EOMI_2 = re.compile(config.EOMI_PATTERN)
_SPECIAL_CHARS = re.compile(config.SPECIAL_CHARS_PATTERN)
_CLAIM_PREFIX_PATTERNS = [re.compile(p) for p in config.CLAIM_PREFIX_PATTERNS]
_NOISE_PATTERNS = [re.compile(p) for p in config.NOISE_PATTERNS]
_STOPWORDS = config.STOPWORDS


def _remove_claim_prefixes(text: str) -> str:
    """청구항 형식 문구 제거."""
    for pat in _CLAIM_PREFIX_PATTERNS:
        text = pat.sub(" ", text)
    return text


def _remove_josa(word: str) -> str:
    """단어 끝 조사/어미 단계적 제거."""
    prev = None
    while prev != word:
        prev = word
        word = _EOMI_2.sub("", word)
    word = _JOSA_1.sub("", word)
    return word


def _is_noise(token: str) -> bool:
    """노이즈 패턴 매칭."""
    return any(p.match(token) for p in _NOISE_PATTERNS)


def extract_keywords(text: str) -> list[str]:
    """텍스트 → 키워드 리스트 (중복 제거, 순서 유지).

    CSV 인덱스 구축과 동일한 전처리:
    청구항 접두사 제거 → 특수문자 제거 → 조사/어미 제거 → 불용어/노이즈 필터.
    """
    text = _remove_claim_prefixes(text)
    text = _SPECIAL_CHARS.sub(" ", text)
    # v3 추가: "및" 앞뒤 공백 삽입 (붙어버린 토큰 분리)
    text = re.sub(r"및", " 및 ", text)
    words = re.split(r"\s+", text)

    result = []
    seen = set()
    for w in words:
        cleaned = _remove_josa(w.strip())
        if not cleaned:
            continue
        if len(cleaned) < 2:
            continue
        if cleaned in _STOPWORDS:
            continue
        if _is_noise(cleaned):
            continue
        if cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


# ══════════════════════════════════════════════════════
# RDB 사전필터링 (SQLite 로컬 / MySQL RDS 자동 선택)
#
# 우선순위:
#   1. MYSQL_HOST 환경변수 설정 + 연결 성공 → MySQL claim_keywords 테이블
#   2. 그 외 → claim_keywords.sqlite (INDEX_DIR 내 로컬 파일)
#
# 자동 감지는 최초 1회만 수행됩니다.
# ══════════════════════════════════════════════════════

import os as _os

_prefilter_backend = None        # "mysql" | "sqlite" | "" (실패)
_prefilter_mysql_conn = None
_prefilter_sqlite_conn = None


def _try_mysql_prefilter():
    """MySQL 연결 시도. 성공하면 connection, 실패하면 None."""
    host = _os.environ.get("MYSQL_HOST", "")
    if not host:
        return None
    try:
        import pymysql
        conn = pymysql.connect(
            host=host,
            port=int(_os.environ.get("MYSQL_PORT", 3306)),
            user=_os.environ.get("MYSQL_USER", "root"),
            password=_os.environ.get("MYSQL_PASSWORD", ""),
            database=_os.environ.get("MYSQL_DATABASE", "fto"),
            charset="utf8mb4",
            connect_timeout=30,
            read_timeout=300,
            write_timeout=300,
        )
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM claim_keywords LIMIT 1")
        cur.fetchone()
        cur.close()
        return conn
    except Exception:
        return None


def _try_sqlite_prefilter():
    """SQLite 연결 시도. 성공하면 connection, 실패하면 None."""
    db_path = config.CLAIM_KEYWORDS_SQLITE_PATH
    if not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM claim_keywords LIMIT 1")
        cur.fetchone()
        cur.close()
        return conn
    except Exception:
        return None


def _init_prefilter_backend():
    """사전필터링 백엔드 초기화 (최초 1회)."""
    global _prefilter_backend, _prefilter_mysql_conn, _prefilter_sqlite_conn
    if _prefilter_backend is not None:
        return

    mysql_conn = _try_mysql_prefilter()
    if mysql_conn is not None:
        _prefilter_backend = "mysql"
        _prefilter_mysql_conn = mysql_conn
        _logger.info("[사전필터] MySQL 백엔드 활성")
        return

    sqlite_conn = _try_sqlite_prefilter()
    if sqlite_conn is not None:
        _prefilter_backend = "sqlite"
        _prefilter_sqlite_conn = sqlite_conn
        _logger.info("[사전필터] SQLite 백엔드 활성")
        return

    _prefilter_backend = ""
    _logger.info("[사전필터] 백엔드 없음 — 전체 검색 fallback")


def _prefilter_via_mysql(keywords: list[str]) -> tuple[list[str], list[str]] | None:
    """MySQL claim_keywords 테이블에서 사전필터링."""
    global _prefilter_mysql_conn
    import pymysql

    if not _prefilter_mysql_conn.open:
        _prefilter_mysql_conn = pymysql.connect(
            host=_os.environ["MYSQL_HOST"],
            port=int(_os.environ.get("MYSQL_PORT", 3306)),
            user=_os.environ.get("MYSQL_USER", "root"),
            password=_os.environ.get("MYSQL_PASSWORD", ""),
            database=_os.environ.get("MYSQL_DATABASE", "fto"),
            charset="utf8mb4",
            read_timeout=300,
            write_timeout=300,
            connect_timeout=30,
        )

    import time as _time

    placeholders = ", ".join(["%s"] * len(keywords))
    sql = (
        f"SELECT chunk_id, patent_id, COUNT(*) as cnt "
        f"FROM claim_keywords WHERE keyword IN ({placeholders}) "
        f"GROUP BY chunk_id, patent_id ORDER BY cnt DESC "
        f"LIMIT {config.PREFILTER_MAX_CHUNKS}"
    )
    _logger.info(f"[사전필터] MySQL 쿼리 시작: 키워드 {len(keywords)}개")
    t0 = _time.time()
    cur = _prefilter_mysql_conn.cursor()
    cur.execute(sql, keywords)
    rows = cur.fetchall()
    cur.close()
    elapsed = _time.time() - t0
    _logger.info(f"[사전필터] MySQL 쿼리 완료: {len(rows)}건, {elapsed:.2f}s")

    if not rows:
        return None

    chunk_ids = [r[0] for r in rows]
    patent_ids = list({r[1] for r in rows})
    return patent_ids, chunk_ids


def _prefilter_via_sqlite(keywords: list[str]) -> tuple[list[str], list[str]] | None:
    """SQLite claim_keywords.sqlite에서 사전필터링."""
    placeholders = ", ".join(["?"] * len(keywords))
    sql = (
        f"SELECT chunk_id, patent_id, COUNT(*) as cnt "
        f"FROM claim_keywords WHERE keyword IN ({placeholders}) "
        f"GROUP BY chunk_id, patent_id ORDER BY cnt DESC "
        f"LIMIT {config.PREFILTER_MAX_CHUNKS}"
    )
    cur = _prefilter_sqlite_conn.cursor()
    cur.execute(sql, keywords)
    rows = cur.fetchall()
    cur.close()

    if not rows:
        return None

    chunk_ids = [r[0] for r in rows]
    patent_ids = list({r[1] for r in rows})
    return patent_ids, chunk_ids


def prefilter_by_keywords(
    extracted_keywords: list[str],
) -> tuple[list[str], list[str]] | None:
    """정규화 키워드로 DB 조회 → 매칭된 patent_id, chunk_id 반환.

    Args:
        extracted_keywords: extract_keywords()로 추출된 정규화 키워드 목록.

    Returns:
        (patent_ids, chunk_ids) — 리트리버에 전달할 allowed 목록
        매칭 결과 없으면 None (전체 검색 fallback)
    """
    if not extracted_keywords:
        return None

    _init_prefilter_backend()

    all_keywords = list(set(extracted_keywords))
    if not all_keywords:
        return None

    if _prefilter_backend == "mysql":
        return _prefilter_via_mysql(all_keywords)
    elif _prefilter_backend == "sqlite":
        return _prefilter_via_sqlite(all_keywords)
    else:
        return None


# ══════════════════════════════════════════════════════
# ParentDB — 특허 단위 통합 데이터 (parents.sqlite)
#
# 메타데이터 + 청구항 원문 + 청크 구조를 한 테이블에서 제공:
# - 메타데이터: 출원일, 등록일, 출원인, IPC, 행정상태 등
# - 원문 청구항: claim_pub(공개), claim_regit(등록)
# - 청크 구조: chunk_ids, claim_groups
# ══════════════════════════════════════════════════════

class ParentDB:
    """parents.sqlite 기반 통합 DB 조회."""

    def __init__(self, db_path: str | Path = None):
        db_path = Path(db_path) if db_path else config.PARENT_DB_PATH
        if not db_path.exists():
            raise FileNotFoundError(f"ParentDB 없음: {db_path}")
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        try:
            self._conn.execute("SELECT 1 FROM parents LIMIT 1")
        except sqlite3.OperationalError:
            self._conn.close()
            raise FileNotFoundError(f"parents 테이블 없음 (빈 DB): {db_path}")

    def get_parent(self, apply_num: str) -> dict | None:
        """출원번호로 특허 데이터 전체 조회."""
        row = self._conn.execute(
            "SELECT * FROM parents WHERE apply_num = ?", (apply_num,)
        ).fetchone()
        if not row:
            return None

        def _json(val, default):
            if not val:
                return default
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return default

        return {
            "apply_num": row["apply_num"],
            "invention_title": row["invention_title"],
            "invention_title_eng": row["invention_title_eng"],
            "ipc": _json(row["ipc"], []),
            "register_status": row["register_status"],
            "regit_num": row["regit_num"],
            "application_date": row["application_date"],
            "open_date": row["open_date"],
            "register_date": row["register_date"],
            "applicant": row["applicant"],
            "abstract": row["abstract"],
            "claim_pub": row["claim_pub"],
            "claim_regit": row["claim_regit"],
            "chunk_ids": _json(row["chunk_ids"], []),
            "claim_groups": _json(row["claim_groups"], {}),
        }


class MySQLParentDB:
    """RDS MySQL patents 테이블 기반 ParentDB 대체.

    parents.sqlite가 없는 환경에서 RDS에서 직접 조회합니다.
    ParentDB와 동일한 dict 포맷을 반환합니다.
    """

    def __init__(self):
        import pymysql
        self._conn = pymysql.connect(
            host=_os.environ.get("MYSQL_HOST", ""),
            port=int(_os.environ.get("MYSQL_PORT", 3306)),
            user=_os.environ.get("MYSQL_USER", "root"),
            password=_os.environ.get("MYSQL_PASSWORD", ""),
            database=_os.environ.get("MYSQL_DATABASE", "fto"),
            charset="utf8mb4",
            connect_timeout=30,
            read_timeout=300,
            write_timeout=300,
            cursorclass=pymysql.cursors.DictCursor,
        )

    def get_parent(self, apply_num: str) -> dict | None:
        """출원번호로 특허 데이터 전체 조회."""
        if not self._conn.open:
            self._conn.ping(reconnect=True)

        cur = self._conn.cursor()
        cur.execute("SELECT * FROM patents WHERE apply_num = %s", (apply_num,))
        row = cur.fetchone()
        cur.close()

        if not row:
            return None

        def _json(val, default):
            if not val:
                return default
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return default

        return {
            "apply_num": row.get("apply_num", ""),
            "invention_title": row.get("invention_title", ""),
            "invention_title_eng": row.get("invention_title_eng", ""),
            "ipc": _json(row.get("ipc"), []),
            "register_status": row.get("register_status", ""),
            "regit_num": row.get("regit_num", ""),
            "application_date": row.get("application_date", ""),
            "open_date": row.get("open_date", ""),
            "register_date": row.get("register_date", ""),
            "applicant": row.get("applicant", ""),
            "abstract": row.get("abstract", ""),
            "claim_pub": row.get("claim_pub", ""),
            "claim_regit": row.get("claim_regit", ""),
            "chunk_ids": _json(row.get("chunk_ids"), []),
            "claim_groups": _json(row.get("claim_groups"), {}),
        }


# ══════════════════════════════════════════════════════
# claim_components 배치 조회
# ══════════════════════════════════════════════════════

def fetch_components_batch(patent_ids: list[str]) -> dict[str, list[dict]]:
    """claim_components 테이블에서 patent_id 목록으로 배치 조회.

    Args:
        patent_ids: 조회할 출원번호 목록.

    Returns:
        {patent_id: [{"chunk_id": ..., "components": ..., "note": ...}, ...]}
    """
    if not patent_ids:
        return {}

    _init_prefilter_backend()

    if _prefilter_backend == "mysql":
        return _fetch_components_mysql(patent_ids)
    elif _prefilter_backend == "sqlite":
        return _fetch_components_sqlite(patent_ids)
    return {}


def _fetch_components_mysql(patent_ids: list[str]) -> dict[str, list[dict]]:
    """MySQL claim_components 배치 조회."""
    global _prefilter_mysql_conn
    import pymysql

    if not _prefilter_mysql_conn or not _prefilter_mysql_conn.open:
        _prefilter_mysql_conn = pymysql.connect(
            host=_os.environ["MYSQL_HOST"],
            port=int(_os.environ.get("MYSQL_PORT", 3306)),
            user=_os.environ.get("MYSQL_USER", "root"),
            password=_os.environ.get("MYSQL_PASSWORD", ""),
            database=_os.environ.get("MYSQL_DATABASE", "fto"),
            charset="utf8mb4",
            read_timeout=300,
            write_timeout=300,
            connect_timeout=30,
        )

    placeholders = ", ".join(["%s"] * len(patent_ids))
    sql = (
        f"SELECT patent_id, chunk_id, components, note "
        f"FROM claim_components WHERE patent_id IN ({placeholders})"
    )
    try:
        cur = _prefilter_mysql_conn.cursor()
        cur.execute(sql, patent_ids)
        rows = cur.fetchall()
        cur.close()
    except Exception as e:
        _logger.warning(f"[구성요소] MySQL 조회 실패: {e}")
        return {}

    result: dict[str, list[dict]] = {}
    for patent_id, chunk_id, components, note in rows:
        result.setdefault(patent_id, []).append({
            "chunk_id": chunk_id,
            "components": components or "",
            "note": note or "",
        })
    return result


def _fetch_components_sqlite(patent_ids: list[str]) -> dict[str, list[dict]]:
    """SQLite claim_components 배치 조회 (로컬 환경 fallback)."""
    placeholders = ", ".join(["?"] * len(patent_ids))
    sql = (
        f"SELECT patent_id, chunk_id, components, note "
        f"FROM claim_components WHERE patent_id IN ({placeholders})"
    )
    try:
        cur = _prefilter_sqlite_conn.cursor()
        cur.execute(sql, patent_ids)
        rows = cur.fetchall()
        cur.close()
    except Exception as e:
        _logger.warning(f"[구성요소] SQLite 조회 실패: {e}")
        return {}

    result: dict[str, list[dict]] = {}
    for patent_id, chunk_id, components, note in rows:
        result.setdefault(patent_id, []).append({
            "chunk_id": chunk_id,
            "components": components or "",
            "note": note or "",
        })
    return result


# ══════════════════════════════════════════════════════
# RDB 필터 적용 (등록 상태 필터 + 데이터 보강)
# ══════════════════════════════════════════════════════

def apply_rdb_filter(
    collapsed_results: list[dict],
    parent_db: ParentDB,
) -> list[dict]:
    """Patent Collapse 결과에 ParentDB 필터링 + 보강 적용."""
    filtered = []

    # 구성요소 배치 조회 (N+1 방지)
    all_patent_ids = [r["patent_id"] for r in collapsed_results]
    components_map = fetch_components_batch(all_patent_ids)

    for result in collapsed_results:
        patent_id = result["patent_id"]
        parent = parent_db.get_parent(patent_id)

        # 허용 행정상태 필터 (소멸/거절/취하 등 제외)
        if config.ALLOWED_STATUSES:
            status = (parent or {}).get("register_status", "")
            if status not in config.ALLOWED_STATUSES:
                continue

        meta = dict(result["metadata"])

        # ParentDB 메타데이터로 보강
        if parent:
            for key in ("invention_title", "abstract", "regit_num", "register_status"):
                if not meta.get(key) and parent.get(key):
                    meta[key] = parent[key]
            if not meta.get("ipc") and parent.get("ipc"):
                meta["ipc"] = parent["ipc"]
            for key in ("invention_title_eng", "application_date", "open_date",
                         "register_date", "applicant"):
                if parent.get(key):
                    meta[key] = parent[key]

        entry = {
            "patent_id": patent_id,
            "score": result["score"],
            "matched_claim_num": result["matched_claim_num"],
            "metadata": meta,
            "claims": {
                "claim_regit_text": (parent or {}).get("claim_regit", ""),
                "claim_pub_text": (parent or {}).get("claim_pub", ""),
            },
            "estoppel_claim_numbers": [],
            "chunk_ids": (parent or {}).get("chunk_ids", []),
            "claim_groups": (parent or {}).get("claim_groups", {}),
            "components": components_map.get(patent_id, []),
            "source": "rag",
        }

        filtered.append(entry)

    return filtered
