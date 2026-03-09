"""sLLM 출력 ID가 등록번호(regit_num)와 매칭되는지 확인"""
import chromadb

client = chromadb.PersistentClient(path="data/chroma-patent")
col = client.get_collection("patent_chunks")

# sLLM 리포트에서 나온 ID 샘플들
sllm_ids = [
    "1008298320000",   # 질의1 sLLM 출력
    "1018738960000",
    "1008053860000",   # 질의2
    "1007968170000",   # 질의6
    "1013425570000",   # 질의7
]

# 검색 결과(출원번호) 샘플
search_ids = [
    "1020060001051",   # 질의1 정답
    "1020060079021",   # 질의2 정답
    "1020060026281",   # 질의6 정답
    "1020110009279",   # 질의7 정답
]

print("=== sLLM 출력 ID → 등록번호에서 찾기 ===")
for sid in sllm_ids:
    # regit_num 형식: 10-0770953-0000 → 하이픈 제거하면 1007709530000
    # sLLM ID가 이 형식일 수 있음
    # where 조건으로 검색
    try:
        # regit_num에서 하이픈 제거한 것과 비교
        results = col.get(
            where={"regit_num": sid},
            limit=1,
            include=["metadatas"]
        )
        if results["ids"]:
            meta = results["metadatas"][0]
            print(f"  {sid} → regit_num 직접매칭 O: apply_num={meta['apply_num']}")
            continue
    except:
        pass

    # 하이픈 형식으로도 시도: 1008298320000 → 10-0829832-0000
    formatted = f"{sid[:2]}-{sid[2:9]}-{sid[9:]}"
    try:
        results = col.get(
            where={"regit_num": formatted},
            limit=1,
            include=["metadatas"]
        )
        if results["ids"]:
            meta = results["metadatas"][0]
            print(f"  {sid} → formatted({formatted}) O: apply_num={meta['apply_num']}")
            continue
    except:
        pass

    print(f"  {sid} → 매칭 실패")

print()
print("=== 정답 출원번호 → 등록번호 확인 ===")
for aid in search_ids:
    try:
        results = col.get(
            where={"apply_num": aid},
            limit=1,
            include=["metadatas"]
        )
        if results["ids"]:
            meta = results["metadatas"][0]
            regit = meta.get("regit_num", "N/A")
            regit_clean = regit.replace("-", "")
            print(f"  apply_num={aid} → regit_num={regit} (cleaned={regit_clean})")
        else:
            print(f"  apply_num={aid} → 없음")
    except Exception as e:
        print(f"  apply_num={aid} → 에러: {e}")
