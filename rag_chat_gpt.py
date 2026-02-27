"""RAG FTO 분석 터미널 챗봇 (GPT 버전)

사용법: python rag_chat_gpt.py
"""
from rag.backend_adapter_gpt import analyze_product

print("=" * 50)
print("FTO 특허 침해 분석 챗봇 (GPT 버전)")
print("종료: quit 또는 exit")
print("=" * 50)

while True:
    query = input("\n제품 설명 > ").strip()
    if not query or query in ("quit", "exit", "q"):
        print("종료합니다.")
        break

    print("\n분석 중... (1~2분 소요)")
    try:
        result = analyze_product(query, verbose=True)
        fto = result.get("fto_result", {})
        opinion = fto.get("fto_opinion", "")
        patents = fto.get("patent_analyses", [])

        print("\n" + "=" * 50)
        print("FTO 분석 결과")
        print("=" * 50)

        if patents:
            for p in patents:
                print(f"\n[{p.get('label', '?')}] {p.get('patent_id', '?')} - {p.get('invention_title', '?')}")
                print(f"  점수: {p.get('score', '?')}")

        print("\n--- 종합 의견 ---")
        print(opinion if opinion else "분석 결과 없음")
        print("=" * 50)
    except Exception as e:
        print(f"오류: {e}")
