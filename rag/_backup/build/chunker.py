"""특허 JSON → Dual-View 청크 생성 + claims_db.json 생성. (인덱싱 시 1회 실행)

하는 일 (청크 생성):
    특허 JSON 파일을 읽어서 독립항 단위로 청크를 만듭니다.
    각 청크는 3종류의 텍스트를 가집니다:
    - dense_text:  의미 검색용 (제목+IPC+요약+청구항, 자연어 보존)  → indexer.py Dense
    - sparse_text: 키워드 검색용 (법률 상용구 제거, 명사만 추출)   → indexer.py Sparse
    - full_text:   원본 보존 (sLLM 전달, 프론트 표시용)

하는 일 (claims_db):
    특허 JSON에서 청구항 정보를 구조화하여 claims_db.json으로 저장합니다.
    검색 후 필터링·보강 단계(search/filter.py)에서 사용됩니다.

청크 단위:
    독립항 1개 + 그에 딸린 종속항들 = 1 청크
    예) 독립항3개, 종속항7개인 특허 → 3개 청크

관계:
    - build/tokenizer.py의 extract_keywords_for_sparse()를 사용하여 sparse_text 생성
    - search/filter.py의 JsonClaimsDB가 claims_db.json을 로드
    - eval/build_index.py가 load_chunks_from_dir(), build_claims_db()를 호출
"""
import json
import re
from pathlib import Path

from .tokenizer import extract_keywords_for_sparse

# ── claim_type 분류 ──────────────────────────────────
_DEPENDENT_PATTERN = re.compile(r"제\s*(\d+)\s*항")


def classify_claim(claim: dict) -> tuple[str, list[int]]:
    """독립항/종속항 분류. claim_type 필드 우선, 없으면 텍스트 패턴."""
    if claim.get("claim_type"):
        return claim["claim_type"], claim.get("refers_to", [])

    text = claim.get("text", "")
    refs = [int(m) for m in _DEPENDENT_PATTERN.findall(text)]
    if refs:
        return "dependent", refs
    return "independent", []


def _safe_text(claim: dict) -> str | None:
    """삭제/빈/이미지 청구항 필터링."""
    if claim.get("change_code") == "D" or claim.get("change_type") == "삭제":
        return None
    text = (claim.get("text") or "").strip()
    if not text or "[이미지]" in text:
        return None
    return text


def _extract_metadata(data: dict) -> dict:
    """특허 JSON에서 메타데이터 추출."""
    biblio = (data.get("biblioSummaryInfoArray") or {}).get("biblioSummaryInfo", {})
    abstract_raw = (data.get("abstractInfoArray") or {}).get("abstractInfo", {}).get("astrtCont", "")
    abstract = re.sub(r"<[^>]+>", "", abstract_raw).strip()
    abstract = re.sub(r"\s+", " ", abstract)

    ipc_list = []
    ipc_arr = data.get("ipcInfoArray")
    if ipc_arr:
        for item in (ipc_arr.get("ipcInfo") or []):
            code = (item.get("ipcNumber") or "").strip()
            if code:
                ipc_list.append(code)

    return {
        "apply_num": (biblio.get("applicationNumber") or "").replace("-", ""),
        "regit_num": biblio.get("registerNumber", ""),
        "register_status": biblio.get("registerStatus", ""),
        "invention_title": biblio.get("inventionTitle", ""),
        "ipc": ipc_list,
        "abstract": abstract,
    }


def _group_claims(valid_claims: dict) -> dict[int, list[int]]:
    """독립항별 종속항 그룹핑."""
    groups: dict[int, list[int]] = {}

    for num, claim in valid_claims.items():
        ctype, refs = classify_claim(claim)

        if ctype == "independent":
            groups.setdefault(num, [])
        elif ctype == "dependent":
            parent = None
            for r in refs:
                if r in valid_claims:
                    rt, _ = classify_claim(valid_claims[r])
                    if rt == "independent":
                        parent = r
                        break
            if parent is None and refs:
                for gid in groups:
                    if refs[0] in groups[gid] or refs[0] == gid:
                        parent = gid
                        break
            if parent is None:
                for gid in sorted(groups.keys(), reverse=True):
                    if gid < num:
                        parent = gid
                        break
            if parent is not None:
                groups[parent].append(num)

    return groups


def _build_dense_text(
    title: str, ipc_list: list[str], abstract: str,
    indep_num: int, indep_text: str,
    dep_claims: list[tuple[int, str]],
) -> str:
    """Dense 임베딩용 텍스트."""
    parts = [f"[발명] {title}"]
    if ipc_list:
        parts.append(f"[분야] {', '.join(ipc_list)}")
    if abstract:
        parts.append(f"[요약] {abstract}")
    parts.append(f"[독립항 {indep_num}] {indep_text}")
    for dn, dt in dep_claims:
        parts.append(f"[종속항 {dn}] {dt}")
    text = "\n".join(parts)
    return re.sub(r"\s+", " ", text).strip()


def _build_dense_header(title: str, ipc_list: list[str], abstract: str) -> str:
    """dense_text의 헤더 부분 (제목+IPC+요약). 슬라이딩 윈도우에서 반복 사용."""
    parts = [f"[발명] {title}"]
    if ipc_list:
        parts.append(f"[분야] {', '.join(ipc_list)}")
    if abstract:
        parts.append(f"[요약] {abstract}")
    text = " ".join(parts)
    return re.sub(r"\s+", " ", text).strip()


def _sliding_window_dense_texts(
    title: str, ipc_list: list[str], abstract: str,
    indep_num: int, indep_text: str,
    max_chars: int, overlap_chars: int = 500,
) -> list[str]:
    """독립항 텍스트가 max_chars를 초과할 때 오버랩 슬라이딩 윈도우로 분할.

    각 윈도우에 헤더(제목+IPC+요약)를 반복 포함하여 컨텍스트 유지.
    """
    header = _build_dense_header(title, ipc_list, abstract)
    claim_prefix = f"[독립항 {indep_num}] "
    body = re.sub(r"\s+", " ", indep_text).strip()

    # 본문에 할당 가능한 글자수
    available = max_chars - len(header) - len(claim_prefix) - 1  # 1 for space
    if available <= 0:
        available = max_chars

    window_texts = []
    start = 0
    while start < len(body):
        end = start + available
        chunk_body = body[start:end]
        dense = f"{header} {claim_prefix}{chunk_body}"
        window_texts.append(dense)
        if end >= len(body):
            break
        start = end - overlap_chars

    return window_texts


def _build_sparse_text(
    title: str, abstract: str,
    indep_text: str, dep_claims: list[tuple[int, str]],
) -> str:
    """Sparse(BM25)용 텍스트."""
    raw = f"{title} {abstract} {indep_text}"
    for _, dt in dep_claims:
        raw += f" {dt}"
    return extract_keywords_for_sparse(raw)


def _build_full_text(
    indep_num: int, indep_text: str,
    dep_claims: list[tuple[int, str]],
) -> str:
    """원본 보존 텍스트."""
    parts = [f"[청구항 {indep_num}] {indep_text}"]
    for dn, dt in dep_claims:
        parts.append(f"[청구항 {dn}] {dt}")
    return "\n".join(parts)


def _build_claim_pub(first_version: dict | None) -> str:
    """출원 시점 청구항 텍스트 (금반언 비교용)."""
    if not first_version:
        return ""
    parts = []
    for c in first_version.get("claims", []):
        t = _safe_text(c)
        if t:
            parts.append(f"[청구항 {c.get('claim_number', '?')}] {t}")
    return "\n".join(parts)


def _split_dep_claims_for_dense(
    title: str, ipc_list: list[str], abstract: str,
    indep_num: int, indep_text: str,
    dep_claims: list[tuple[int, str]],
    max_chars: int,
) -> list[list[tuple[int, str]]]:
    """dense_text가 max_chars를 초과하면 종속항 경계에서 서브그룹으로 분할.

    각 서브그룹의 dense_text에는 독립항이 반복 포함되므로,
    독립항만으로 구성된 베이스 길이를 먼저 계산한 뒤 종속항을 하나씩 추가한다.
    """
    # 종속항 없으면 분할 불필요
    if not dep_claims:
        return [dep_claims]

    # 전체가 한계 이내면 분할 불필요
    full_dense = _build_dense_text(title, ipc_list, abstract, indep_num, indep_text, dep_claims)
    if len(full_dense) <= max_chars:
        return [dep_claims]

    # 독립항만 있는 베이스 길이
    base_len = len(_build_dense_text(title, ipc_list, abstract, indep_num, indep_text, []))

    sub_groups = []
    current_group = []
    current_len = base_len

    for dn, dt in dep_claims:
        added_len = len(f" [종속항 {dn}] {dt}")
        if current_group and current_len + added_len > max_chars:
            sub_groups.append(current_group)
            current_group = []
            current_len = base_len
        current_group.append((dn, dt))
        current_len += added_len

    if current_group:
        sub_groups.append(current_group)

    return sub_groups


def build_chunks_from_patent(data: dict, app_num: str = "") -> list[dict]:
    """특허 1개 JSON → Dual-View 청크 리스트.

    dense_text가 DENSE_MAX_CHARS를 초과하는 독립항 그룹은
    종속항 경계에서 서브청크로 분할하되, 독립항을 각 서브청크에 반복 포함한다.
    sparse_text, full_text는 토큰 한계가 없으므로 항상 전체 종속항을 포함한다.
    """
    from .. import config

    claims_section = data.get("claims", {})
    last_ver = claims_section.get("last_version")
    if not last_ver:
        return []

    meta = _extract_metadata(data)
    if not app_num:
        app_num = meta["apply_num"] or claims_section.get("application_number", "")
    claim_pub = _build_claim_pub(claims_section.get("first_version"))
    title = meta["invention_title"]

    valid_claims: dict[int, dict] = {}
    for c in last_ver.get("claims", []):
        t = _safe_text(c)
        if t:
            valid_claims[c["claim_number"]] = {**c, "text": t}

    if not valid_claims:
        return []

    groups = _group_claims(valid_claims)
    if not groups:
        return []

    chunks = []
    for indep_num, dep_nums in groups.items():
        indep_claim = valid_claims[indep_num]
        indep_text = indep_claim["text"]

        dep_claims = []
        for dn in sorted(dep_nums):
            if dn in valid_claims:
                dep_claims.append((dn, valid_claims[dn]["text"]))

        # sparse_text, full_text는 항상 전체 종속항 포함 (토큰 한계 없음)
        sparse_text = _build_sparse_text(
            title, meta["abstract"], indep_text, dep_claims,
        )
        full_text = _build_full_text(indep_num, indep_text, dep_claims)
        all_dep_nums = sorted(dep_nums)

        # 독립항만으로 구성된 dense_text 길이 확인
        base_dense = _build_dense_text(
            title, meta["ipc"], meta["abstract"],
            indep_num, indep_text, [],
        )

        dense_texts_with_ids = []
        if len(base_dense) > config.DENSE_MAX_CHARS:
            # 독립항 자체가 초과 → 슬라이딩 윈도우 (1회만)
            window_texts = _sliding_window_dense_texts(
                title, meta["ipc"], meta["abstract"],
                indep_num, indep_text,
                max_chars=config.DENSE_MAX_CHARS,
            )
            for win_idx, win_text in enumerate(window_texts):
                cid = f"{app_num}_claim_{indep_num}_win{win_idx}"
                dense_texts_with_ids.append((cid, win_text, []))
        else:
            # Step 1: 종속항 경계에서 서브청크 분할
            sub_groups = _split_dep_claims_for_dense(
                title, meta["ipc"], meta["abstract"],
                indep_num, indep_text, dep_claims,
                max_chars=config.DENSE_MAX_CHARS,
            )

            # Step 2: 각 서브그룹의 dense_text 생성
            for sub_idx, sub_deps in enumerate(sub_groups):
                dense_text = _build_dense_text(
                    title, meta["ipc"], meta["abstract"],
                    indep_num, indep_text, sub_deps,
                )

                if len(sub_groups) == 1:
                    cid = f"{app_num}_claim_{indep_num}"
                else:
                    cid = f"{app_num}_claim_{indep_num}_sub{sub_idx}"
                dense_texts_with_ids.append((cid, dense_text, [dn for dn, _ in sub_deps]))

        for chunk_id, dense_text, sub_dep_nums in dense_texts_with_ids:
            chunks.append({
                "chunk_id": chunk_id,
                "dense_text": dense_text,
                "sparse_text": sparse_text,
                "full_text": full_text,
                "metadata": {
                    **meta,
                    "claim_pub": claim_pub,
                    "indep_claim_num": indep_num,
                    "dep_claim_nums": all_dep_nums,
                    "sub_dep_nums": sub_dep_nums if sub_dep_nums else all_dep_nums,
                },
            })

    return chunks


def load_chunks_from_dir(data_dir: str | Path) -> list[dict]:
    """디렉토리 내 모든 특허 JSON → 청크 리스트."""
    data_dir = Path(data_dir)
    all_chunks = []

    for fp in sorted(data_dir.glob("*.json")):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            claims_section = data.get("claims", {})
            app_num = claims_section.get("application_number", "")
            if not app_num:
                app_num = re.sub(r"[^0-9]", "", fp.stem)

            chunks = build_chunks_from_patent(data, app_num)
            all_chunks.extend(chunks)
            print(f"  {fp.name}: {len(chunks)}개 청크")
        except Exception as e:
            print(f"  [WARN] {fp.name}: {e}")

    print(f"\n총 {len(all_chunks)}개 청크 생성")
    return all_chunks


# ══════════════════════════════════════════════════════
# claims_db.json 생성 (RDB 필터링용)
# ══════════════════════════════════════════════════════

def build_claims_db(data_dir: str | Path, output_path: str | Path) -> int:
    """특허 JSON 디렉토리 → claims_db.json 생성."""
    data_dir = Path(data_dir)
    output_path = Path(output_path)
    db: dict[str, dict] = {}

    for fp in sorted(data_dir.glob("*.json")):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            meta = _extract_metadata(data)
            claims_section = data.get("claims", {})
            app_num = claims_section.get("application_number", "")
            if not app_num:
                app_num = meta["apply_num"]
            if not app_num:
                continue

            last_claims = []
            estoppel_claims = []
            last_ver = claims_section.get("last_version", {})
            for c in last_ver.get("claims", []):
                claim_entry = {
                    "claim_number": c.get("claim_number"),
                    "claim_type": c.get("claim_type", ""),
                    "change_type": c.get("change_type", ""),
                    "text": (c.get("text") or "").strip(),
                }
                last_claims.append(claim_entry)
                if c.get("change_type") == "삭제" or c.get("change_code") == "D":
                    estoppel_claims.append(c.get("claim_number"))

            first_claims = []
            first_ver = claims_section.get("first_version", {})
            for c in first_ver.get("claims", []):
                t = _safe_text(c)
                if t:
                    first_claims.append({
                        "claim_number": c.get("claim_number"),
                        "claim_type": c.get("claim_type", ""),
                        "text": t,
                    })

            db[app_num] = {
                "metadata": meta,
                "last_claims": last_claims,
                "first_claims": first_claims,
                "estoppel_claim_numbers": estoppel_claims,
            }
        except Exception as e:
            print(f"  [WARN] {fp.name}: {e}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

    print(f"claims_db 생성: {len(db)}개 특허 → {output_path}")
    return len(db)
