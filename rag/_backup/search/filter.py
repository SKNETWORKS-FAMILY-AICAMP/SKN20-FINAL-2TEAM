"""RDB 필터링: 등록 상태 확인 + 금반언(Estoppel) 처리.

하는 일:
    검색 결과에 대해 후처리를 수행합니다:
    1. 등록 상태 필터: "등록" 상태가 아닌 특허 제거
    2. 금반언 표시: 출원→등록 과정에서 삭제된 청구항 번호를 결과에 첨부
    3. 데이터 보강: 전체 청구항 텍스트, 출원시 청구항 등 sLLM에 필요한 정보 추가

    데이터 소스는 2가지를 지원합니다:
    - JsonClaimsDB: claims_db.json 파일 (독립 실행용, build/chunker.py가 생성)
    - MySQLClaimsDB: backend MySQL 직접 조회 (백엔드 연동용, backend_adapter.py에 구현)

관계:
    - build/chunker.py의 build_claims_db()가 만든 claims_db.json을 JsonClaimsDB가 로드
    - pipeline.py가 search/engine.py의 patent_collapse() 결과를 받아 apply_rdb_filter() 호출
    - backend_adapter.py의 MySQLClaimsDB도 같은 ClaimsDBInterface를 구현
"""
import json
from pathlib import Path
from typing import Protocol, runtime_checkable

from .. import config


@runtime_checkable
class ClaimsDBInterface(Protocol):
    """청구항 DB 인터페이스."""

    def get_patent(self, apply_num: str) -> dict | None: ...
    def is_registered(self, apply_num: str) -> bool: ...
    def get_estoppel_claims(self, apply_num: str) -> list[int]: ...


class JsonClaimsDB:
    """claims_db.json 기반 구현."""

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


def apply_rdb_filter(
    collapsed_results: list[dict],
    claims_db: ClaimsDBInterface,
) -> list[dict]:
    """Patent Collapse 결과에 RDB 필터링 적용."""
    filtered = []

    for result in collapsed_results:
        patent_id = result["patent_id"]
        patent_data = claims_db.get_patent(patent_id)

        if config.REGISTERED_ONLY:
            if not claims_db.is_registered(patent_id):
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
            entry["claims"] = {
                "last_claims": patent_data.get("last_claims", []),
                "first_claims": patent_data.get("first_claims", []),
            }

            if config.ESTOPPEL_ENABLED:
                entry["estoppel_claim_numbers"] = claims_db.get_estoppel_claims(patent_id)

            if "metadata" in patent_data:
                for k, v in patent_data["metadata"].items():
                    if k not in entry["metadata"]:
                        entry["metadata"][k] = v

        filtered.append(entry)

    return filtered
