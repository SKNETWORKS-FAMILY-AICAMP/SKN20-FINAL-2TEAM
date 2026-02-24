"""RDB 필터링: 등록 상태 확인 + 금반언(Estoppel) 처리.

하는 일:
    검색 결과에 대해 후처리를 수행합니다:
    1. 등록 상태 필터: "등록" 상태가 아닌 특허 제거
    2. 금반언 표시: 출원→등록 과정에서 삭제된 청구항 번호를 결과에 첨부
    3. 데이터 보강: 전체 청구항 텍스트, 출원시 청구항 등 sLLM에 필요한 정보 추가

    데이터 소스 3가지:
    - SQLiteClaimsDB: claims_db.sqlite (현재 활성 — 테스트용, 78,587건 완전 데이터)
    - MySQLClaimsDB:  백엔드 MySQL 직접 조회 (비활성 — 추후 RDB 구축 완료 시 활성화)
    - JsonClaimsDB:   claims_db.json (레거시, 메모리 1.6GB 필요)

    ┌──────────────────────────────────────────────────────────────────┐
    │  전환 가이드 (실제 MySQL RDB 완성 시)                              │
    │                                                                    │
    │  Step 1. 이 파일(filter.py)에서:                                   │
    │    - MySQLClaimsDB.__init__의 기본값을 실제 RDB 연결 정보로 변경   │
    │      (host, port, user, password, database)                        │
    │    - SQLiteClaimsDB 클래스 전체 삭제 (class ~ get_estoppel_claims) │
    │                                                                    │
    │  Step 2. pipeline.py에서:                                          │
    │    - 26행: SQLiteClaimsDB → MySQLClaimsDB 로 변경                  │
    │      before: from .search.filter import ..., SQLiteClaimsDB        │
    │      after:  from .search.filter import ..., MySQLClaimsDB         │
    │    - 133행: SQLiteClaimsDB() → MySQLClaimsDB() 로 변경            │
    │                                                                    │
    │  Step 3. eval/profile.py, eval/rrf_sweep.py에서:                   │
    │    - import와 인스턴스 생성을 동일하게 SQLite → MySQL 교체         │
    │                                                                    │
    │  Step 4. config.py에서:                                            │
    │    - CLAIMS_SQLITE_PATH 줄 삭제                                    │
    │                                                                    │
    │  Step 5. (선택) index/claims_db.sqlite 파일 삭제 (1.7GB)           │
    └──────────────────────────────────────────────────────────────────┘

관계:
    - pipeline.py가 search/retriever.py의 patent_collapse() 결과를 받아 apply_rdb_filter() 호출
"""
import json
import re
import sqlite3
from pathlib import Path
from typing import Protocol, runtime_checkable

from .. import config


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
# RDB 사전필터링 (CSV 기반 — 임시)
#
# ※ 현재 claim_keywords_full.csv를 임시 데이터로 사용.
#    추후 DB 구축 완료 시 DB 조회로 교체 예정.
#    CSV 컬럼: patent_id, chunk_id, keyword
# ══════════════════════════════════════════════════════

_prefilter_df = None              # CSV 캐시 (최초 1회 로드)
_unique_csv_keywords = None       # 유니크 키워드 캐시 (최초 1회)


def _load_prefilter_csv() -> "pd.DataFrame":
    """사전필터링용 CSV 로드. 최초 호출 시 1회. 유니크 키워드도 함께 캐싱."""
    global _prefilter_df, _unique_csv_keywords
    if _prefilter_df is None:
        import pandas as pd
        csv_path = config.INDEX_DIR / "claim_keywords_full.csv"
        _prefilter_df = pd.read_csv(csv_path, dtype=str)
        # 유니크 키워드를 로드 시점에 1회만 계산 (매 쿼리마다 dropna().unique() 반복 방지)
        _unique_csv_keywords = set(
            kw for kw in _prefilter_df["keyword"].dropna().unique()
            if len(kw) >= 2
        )
    return _prefilter_df


def prefilter_by_keywords(
    extracted_keywords: list[str],
) -> tuple[list[str], list[str]] | None:
    """정규화 키워드로 CSV 조회 → 매칭된 patent_id, chunk_id 반환.

    Args:
        extracted_keywords: extract_keywords()로 추출된 정규화 키워드 목록.
            CSV와 동일한 전처리이므로 매칭 보장.

    Returns:
        (patent_ids, chunk_ids) — 리트리버에 전달할 allowed 목록
        매칭 결과 없으면 None (전체 검색 fallback)
    """
    if not extracted_keywords:
        return None

    df = _load_prefilter_csv()

    all_keywords = list(set(extracted_keywords))

    if not all_keywords:
        return None

    matched = df[df["keyword"].isin(all_keywords)]

    if matched.empty:
        return None

    # 청크별 매칭 키워드 수로 정렬, 상위 N개만 반환
    chunk_scores = matched.groupby("chunk_id").size().sort_values(ascending=False)
    top_chunks = chunk_scores.head(config.PREFILTER_MAX_CHUNKS)
    chunk_ids = top_chunks.index.tolist()

    # chunk_id에서 patent_id 추출
    patent_ids = matched[matched["chunk_id"].isin(chunk_ids)]["patent_id"].unique().tolist()

    return patent_ids, chunk_ids


# ══════════════════════════════════════════════════════
# ClaimsDB 인터페이스 (Protocol)
# ══════════════════════════════════════════════════════

@runtime_checkable
class ClaimsDBInterface(Protocol):
    """청구항 DB 인터페이스."""

    def get_patent(self, apply_num: str) -> dict | None: ...
    def is_registered(self, apply_num: str) -> bool: ...
    def get_estoppel_claims(self, apply_num: str) -> list[int]: ...



# ══════════════════════════════════════════════════════
# [활성] SQLite 기반 구현 (claims_db.sqlite — 테스트용)
#
# claims_db.json(1.6GB)을 SQLite로 변환한 파일 사용.
# 78,587건 완전 데이터. 메모리 부담 없이 쿼리 기반 조회.
# 변환 스크립트: eval/json_to_sqlite.py
#
# ※ 임시 코드: 실제 MySQL RDB 구축 완료 시 MySQLClaimsDB로 교체 후 삭제
# ══════════════════════════════════════════════════════

class SQLiteClaimsDB:
    """claims_db.sqlite 기반 구현 (테스트용 활성 코드)."""

    def __init__(self, db_path: str | Path = None):
        db_path = Path(db_path) if db_path else config.CLAIMS_SQLITE_PATH
        if not db_path.exists():
            raise FileNotFoundError(
                f"SQLite DB 없음: {db_path}\n"
                "  → python -m rag.eval.json_to_sqlite 로 생성하세요."
            )
        self._db_path = str(db_path)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row

    def get_patent(self, apply_num: str) -> dict | None:
        """출원번호로 특허 메타데이터 + 청구항 + 금반언 정보 조회."""
        cur = self._conn.cursor()

        # 특허 기본 정보
        cur.execute(
            "SELECT apply_num, regit_num, register_status, invention_title, abstract "
            "FROM patents WHERE apply_num = ?", (apply_num,)
        )
        row = cur.fetchone()
        if not row:
            return None

        # IPC 코드
        cur.execute(
            "SELECT ipc_code FROM patent_ipc WHERE apply_num = ?", (apply_num,)
        )
        ipc = [r["ipc_code"] for r in cur.fetchall()]

        metadata = {
            "apply_num": row["apply_num"],
            "regit_num": row["regit_num"],
            "register_status": row["register_status"],
            "invention_title": row["invention_title"],
            "ipc": ipc,
            "abstract": row["abstract"],
        }

        result = {"metadata": metadata, "last_claims": [], "first_claims": [], "estoppel_claim_numbers": []}

        # 청구항 조회
        cur.execute(
            "SELECT claim_number, claim_type, change_type, text, version "
            "FROM claims WHERE apply_num = ?", (apply_num,)
        )
        for c in cur.fetchall():
            entry = {"claim_number": c["claim_number"], "claim_type": c["claim_type"], "text": c["text"]}
            if c["version"] == "last":
                entry["change_type"] = c["change_type"]
                result["last_claims"].append(entry)
            else:
                result["first_claims"].append(entry)

        # 금반언: 출원 시 존재했으나 최종에서 삭제된 청구항
        first_nums = {c["claim_number"] for c in result["first_claims"]}
        last_nums = {c["claim_number"] for c in result["last_claims"]}
        result["estoppel_claim_numbers"] = sorted(first_nums - last_nums)

        return result

    def is_registered(self, apply_num: str) -> bool:
        """등록 상태 확인."""
        cur = self._conn.cursor()
        cur.execute(
            "SELECT register_status FROM patents WHERE apply_num = ?", (apply_num,)
        )
        row = cur.fetchone()
        return row is not None and row["register_status"] == "등록"

    def get_estoppel_claims(self, apply_num: str) -> list[int]:
        """금반언 대상 청구항 번호 목록 (출원 시 있었으나 최종에서 삭제된 것)."""
        cur = self._conn.cursor()
        cur.execute("""
            SELECT DISTINCT f.claim_number
            FROM claims f
            WHERE f.apply_num = ? AND f.version = 'first'
              AND f.claim_number NOT IN (
                  SELECT l.claim_number FROM claims l
                  WHERE l.apply_num = ? AND l.version = 'last'
              )
            ORDER BY f.claim_number
        """, (apply_num, apply_num))
        return [r["claim_number"] for r in cur.fetchall()]



# ══════════════════════════════════════════════════════
# [비활성] MySQL 기반 구현 (실제 백엔드 RDB용)
#
# 백엔드의 MySQL fto DB에 직접 연결하는 프로덕션 코드.
# 현재 RDB가 미완성(3,271건)이므로 비활성 상태.
#
# ┌─ 활성화 방법 ─────────────────────────────────────────────────┐
# │ 위 docstring의 "전환 가이드" 참고.                             │
# │                                                                │
# │ 핵심: __init__의 기본 연결 정보를 실제 RDB에 맞게 수정하고,   │
# │ pipeline.py / eval 스크립트에서 SQLiteClaimsDB → 이 클래스로  │
# │ 교체하면 됩니다.                                               │
# │                                                                │
# │ 주의: 현재 RDB의 claims 테이블에 version 컬럼(first/last)이   │
# │ 있는지 확인 필요. 없으면 get_patent() 쿼리를 RDB 스키마에     │
# │ 맞게 수정해야 합니다.                                          │
# │                                                                │
# │ pymysql 설치 필요: pip install pymysql                         │
# └────────────────────────────────────────────────────────────────┘
# ══════════════════════════════════════════════════════

class MySQLClaimsDB:
    """MySQL 기반 구현 (프로덕션용 — 현재 비활성).

    RDB 구축 완료 후 활성화. 연결 정보는 backend/.env 참고.
    """

    def __init__(self, host="localhost", port=3306, user="root",
                 password="newpassword123", database="fto"):
        import pymysql
        self._pymysql = pymysql
        self._conn_params = dict(
            host=host, port=port, user=user,
            password=password, database=database,
            charset="utf8mb4",
        )
        self._conn = pymysql.connect(**self._conn_params)

    def _ensure_conn(self):
        """연결이 끊어졌으면 재연결."""
        if not self._conn.open:
            self._conn = self._pymysql.connect(**self._conn_params)

    def get_patent(self, apply_num: str) -> dict | None:
        """출원번호로 특허 메타데이터 + 청구항 + 금반언 정보 조회."""
        self._ensure_conn()
        cur = self._conn.cursor(self._pymysql.cursors.DictCursor)

        # 특허 기본 정보
        cur.execute(
            "SELECT apply_num, regit_num, register_status, invention_title, ipc, abstract "
            "FROM patents WHERE apply_num = %s", (apply_num,)
        )
        row = cur.fetchone()
        if not row:
            return None

        ipc = row["ipc"] if isinstance(row["ipc"], list) else json.loads(row["ipc"] or "[]")
        metadata = {
            "apply_num": row["apply_num"],
            "regit_num": row["regit_num"],
            "register_status": row["register_status"],
            "invention_title": row["invention_title"],
            "ipc": ipc,
            "abstract": row["abstract"],
        }

        result = {"metadata": metadata, "last_claims": [], "first_claims": [], "estoppel_claim_numbers": []}

        # 청구항 조회
        cur.execute(
            "SELECT claim_number, claim_type, change_type, text, version "
            "FROM claims WHERE apply_num = %s", (apply_num,)
        )
        for c in cur.fetchall():
            entry = {"claim_number": c["claim_number"], "claim_type": c["claim_type"], "text": c["text"]}
            if c["version"] == "last":
                entry["change_type"] = c["change_type"]
                result["last_claims"].append(entry)
            else:
                result["first_claims"].append(entry)

        # 금반언: 출원 시 존재했으나 최종에서 삭제된 청구항
        first_nums = {c["claim_number"] for c in result["first_claims"]}
        last_nums = {c["claim_number"] for c in result["last_claims"]}
        result["estoppel_claim_numbers"] = sorted(first_nums - last_nums)

        return result

    def is_registered(self, apply_num: str) -> bool:
        """등록 상태 확인."""
        self._ensure_conn()
        cur = self._conn.cursor()
        cur.execute(
            "SELECT register_status FROM patents WHERE apply_num = %s", (apply_num,)
        )
        row = cur.fetchone()
        return row is not None and row[0] == "등록"

    def get_estoppel_claims(self, apply_num: str) -> list[int]:
        """금반언 대상 청구항 번호 목록."""
        self._ensure_conn()
        cur = self._conn.cursor()
        # claims 테이블에서 직접 계산 (first에 있고 last에 없는 것)
        cur.execute("""
            SELECT DISTINCT f.claim_number
            FROM claims f
            WHERE f.apply_num = %s AND f.version = 'first'
              AND f.claim_number NOT IN (
                  SELECT l.claim_number FROM claims l
                  WHERE l.apply_num = %s AND l.version = 'last'
              )
            ORDER BY f.claim_number
        """, (apply_num, apply_num))
        return [r[0] for r in cur.fetchall()]



# ══════════════════════════════════════════════════════
# JSON 파일 기반 구현 (레거시 — 메모리 1.6GB 필요)
# ══════════════════════════════════════════════════════

class JsonClaimsDB:
    """claims_db.json 기반 구현 (레거시)."""

    def __init__(self, db_path: str | Path = None):
        db_path = Path(db_path) if db_path else config.CLAIMS_DB_PATH
        with open(db_path, "r", encoding="utf-8") as f:
            self._db: dict[str, dict] = json.load(f)

    def get_patent(self, apply_num: str) -> dict | None:
        return self._db.get(apply_num)

    def is_registered(self, apply_num: str) -> bool:
        patent = self._db.get(apply_num)
        if not patent:
            return False
        return patent.get("metadata", {}).get("register_status") == "등록"

    def get_estoppel_claims(self, apply_num: str) -> list[int]:
        patent = self._db.get(apply_num)
        if not patent:
            return []
        return patent.get("estoppel_claim_numbers", [])



# ══════════════════════════════════════════════════════
# 부모 DB (parent.db) — 특허 단위 원문서 데이터
#
# 자식 청크(검색용)와 분리된 부모 데이터를 제공합니다:
# - 메타데이터: 출원일, 등록일, 출원인 등
# - 원문 청구항: claim_pub(공개), claim_regit(등록)
# - 청크 구조: chunk_ids, claim_groups
# ══════════════════════════════════════════════════════

class ParentDB:
    """부모 DB(parent.db) 조회."""

    def __init__(self, db_path: str | Path = None):
        db_path = Path(db_path) if db_path else config.PARENT_DB_PATH
        if not db_path.exists():
            raise FileNotFoundError(f"부모 DB 없음: {db_path}")
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row

    def get_parent(self, apply_num: str) -> dict | None:
        """출원번호로 부모 데이터 전체 조회."""
        row = self._conn.execute(
            "SELECT * FROM parent WHERE apply_num = ?", (apply_num,)
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


# ══════════════════════════════════════════════════════
# RDB 필터 적용 (등록 필터 + 금반언 + 데이터 보강)
# ══════════════════════════════════════════════════════

def apply_rdb_filter(
    collapsed_results: list[dict],
    claims_db: ClaimsDBInterface,
) -> list[dict]:
    """Patent Collapse 결과에 RDB 필터링 적용."""
    filtered = []

    for result in collapsed_results:
        patent_id = result["patent_id"]
        patent_data = claims_db.get_patent(patent_id)

        # 허용 행정상태 필터 (소멸/거절/취하 등 제외)
        if config.ALLOWED_STATUSES:
            status = (patent_data or {}).get("metadata", {}).get("register_status", "")
            if status not in config.ALLOWED_STATUSES:
                continue

        entry = {
            "patent_id": patent_id,
            "score": result["score"],
            "matched_claim_num": result["matched_claim_num"],
            "metadata": result["metadata"],
            "claims": {},
            "estoppel_claim_numbers": [],
            "source": "rag",
        }

        if patent_data:
            # 청구항 텍스트 보강 (sLLM 분석 및 프론트엔드 표시용)
            entry["claims"] = {
                "last_claims": patent_data.get("last_claims", []),
                "first_claims": patent_data.get("first_claims", []),
            }

            # 금반언 청구항 번호 첨부 (삭제된 청구항 = 침해 주장 불가)
            if config.ESTOPPEL_ENABLED:
                entry["estoppel_claim_numbers"] = claims_db.get_estoppel_claims(patent_id)

            # ChromaDB 메타데이터에 없는 필드를 RDB에서 보충
            if "metadata" in patent_data:
                for k, v in patent_data["metadata"].items():
                    if k not in entry["metadata"]:
                        entry["metadata"][k] = v

        filtered.append(entry)

    return filtered
