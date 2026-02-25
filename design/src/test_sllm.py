"""
Qwen2.5-VL-7B-Instruct sLLM 테스트
실행: langchain 환경에서 design/src/ 위치에서 실행

  python test_sllm.py              # TC-2,3,4 (텍스트)
  python test_sllm.py --all        # TC-1 포함 (이미지, 시간 오래 걸림)
"""
import sys
import os
import time
import argparse

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from design_chatbot import graph, GraphState
from langgraph.types import Command

# 이미지 경로 — 본인 환경에 맞게 수정
IMAGE_PATH = r"C:\Users\playdata2\Desktop\SKN_AI_20\SKN20-FINAL-2TEAM(vb2)\design\data\images_v2\3019810003379-api_xml-1_001.JPG"

PASS = "✅ 통과"
WARN = "⚠️ 미흡"
FAIL = "❌ 실패"

results_summary = []  # [(tc, 항목, 판정)]


def judge(condition):
    return PASS if condition else FAIL


def sep(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def _base_state(**overrides):
    state = {
        "input_type": "", "image_path": "", "text_query": "",
        "user_query": "", "base64_image": "",
        "input_analysis": "", "search_results": {},
        "comparison_results": [], "selected_index": 0,
        "detailed_comparison": "", "final_report": "",
        "general_answer": "", "messages": [],
    }
    state.update(overrides)
    return state


# ============================================================
# TC-2: 일반 질문 (Tool 없이 직접 답변)
# ============================================================
def test_tc2():
    sep("TC-2: 일반 질문 — 디자인 특허 출원 절차")

    config = {"configurable": {"thread_id": "test-tc2"}}
    state  = _base_state(text_query="디자인 특허 출원 절차가 뭐야?")

    start  = time.time()
    result = graph.invoke(state, config)
    elapsed = time.time() - start

    answer = result.get('general_answer', '')
    print(f"\n[응답]\n{answer}")

    r1 = judge(len(answer) > 50)
    r2 = judge(any(kw in answer for kw in ['출원', '심사', '등록', '절차']))

    print(f"\n[평가]")
    print(f"  응답 생성 여부         : {r1}  ({len(answer)}자 / GPT-4o: ~500자)")
    print(f"  출원 절차 키워드 포함  : {r2}")
    print(f"  응답 시간              : {elapsed:.1f}초")

    results_summary.append(("TC-2", "응답 생성", r1))
    results_summary.append(("TC-2", "절차 키워드", r2))


# ============================================================
# TC-3: DB 검색 Tool 호출
# ============================================================
def test_tc3():
    sep("TC-3: DB 검색 Tool — 펌프형 용기 디자인")

    config = {"configurable": {"thread_id": "test-tc3"}}
    state  = _base_state(text_query="펌프형 용기 디자인 찾아줘")

    start  = time.time()
    result = graph.invoke(state, config)
    elapsed = time.time() - start

    answer = result.get('general_answer', '')
    print(f"\n[응답]\n{answer}")

    # 출원번호 형식(302...) 포함 여부로 DB tool 호출 간접 확인
    r1 = judge(len(answer) > 30)
    r2 = judge('출원번호' in answer or '302' in answer)

    print(f"\n[평가]")
    print(f"  응답 생성 여부         : {r1}")
    print(f"  DB 검색 결과 포함      : {r2}  (출원번호 언급 여부)")
    print(f"  응답 시간              : {elapsed:.1f}초")

    results_summary.append(("TC-3", "응답 생성", r1))
    results_summary.append(("TC-3", "DB 결과 포함", r2))


# ============================================================
# TC-4: 웹 검색 Tool 호출
# ============================================================
def test_tc4():
    sep("TC-4: 웹 검색 Tool — 2024 디자인 특허 통계")

    config = {"configurable": {"thread_id": "test-tc4"}}
    state  = _base_state(text_query="2024년 디자인 특허 출원 통계 알려줘")

    start  = time.time()
    result = graph.invoke(state, config)
    elapsed = time.time() - start

    answer = result.get('general_answer', '')
    print(f"\n[응답]\n{answer}")

    r1 = judge(len(answer) > 30)
    r2 = judge(any(kw in answer for kw in ['건', '%', '증가', '출원', '2024']))

    print(f"\n[평가]")
    print(f"  응답 생성 여부         : {r1}")
    print(f"  통계 수치/키워드 포함  : {r2}")
    print(f"  응답 시간              : {elapsed:.1f}초")

    results_summary.append(("TC-4", "응답 생성", r1))
    results_summary.append(("TC-4", "통계 정보", r2))


# ============================================================
# TC-1: 이미지 → 유사 검색 → 상세 비교 → FTO 리포트
# ============================================================
def test_tc1():
    sep("TC-1: 이미지 입력 → 유사 검색 → 상세 비교 → FTO 리포트")

    if not os.path.exists(IMAGE_PATH):
        print(f"❌ 이미지 파일 없음: {IMAGE_PATH}")
        print("   IMAGE_PATH 변수를 실제 경로로 수정하세요.")
        results_summary.append(("TC-1", "이미지 파일", FAIL))
        return

    config = {"configurable": {"thread_id": "test-tc1"}}
    state  = _base_state(
        image_path=IMAGE_PATH,
        user_query="FTO 리포트를 작성해줘",
    )

    # 1단계: interrupt 직전까지 실행 (VLM 분석 + 유사 검색)
    start  = time.time()
    result = graph.invoke(state, config)

    analysis          = result.get('input_analysis', '')
    comparison_results = result.get('comparison_results', [])

    print(f"\n[이미지 분석 결과 ({len(analysis)}자)]\n{analysis}")
    print(f"\n[유사 디자인 {len(comparison_results)}개 발견]")
    for c in comparison_results:
        print(f"  [{c['index']}] {c['application_number']} / {c['article_name']} / {c['admst_stat']}")

    # 2단계: 2번 자동 선택 후 상세 비교 + 리포트 생성
    print("\n  → 2번 자동 선택 후 상세 비교 진행...")
    result  = graph.invoke(Command(resume="2"), config)
    elapsed = time.time() - start

    report = result.get('final_report', '')
    print(f"\n[FTO 리포트]\n{report}")

    # 평가
    r1 = judge(len(analysis) > 50)
    r2 = judge(len(comparison_results) > 0)
    r3 = judge(all(kw in report for kw in ['유사', '차이', 'FTO', '출원번호']))

    print(f"\n[평가]")
    print(f"  이미지 분석 품질       : {r1}  ({len(analysis)}자 / GPT-4o: 211자)")
    print(f"  유사 디자인 검색       : {r2}  ({len(comparison_results)}개 / GPT-4o: 8개)")
    print(f"  리포트 핵심 섹션 포함  : {r3}  (유사·차이·FTO·출원번호)")
    print(f"  전체 응답 시간         : {elapsed:.1f}초")

    results_summary.append(("TC-1", "이미지 분석", r1))
    results_summary.append(("TC-1", "유사 검색", r2))
    results_summary.append(("TC-1", "리포트 완성도", r3))


# ============================================================
# 결과 요약 출력
# ============================================================
def print_summary():
    sep("전체 테스트 결과 요약")
    print(f"  {'TC':<6} {'항목':<20} {'판정'}")
    print(f"  {'-'*6} {'-'*20} {'-'*8}")
    for tc, item, verdict in results_summary:
        print(f"  {tc:<6} {item:<20} {verdict}")

    total  = len(results_summary)
    passed = sum(1 for _, _, v in results_summary if v == PASS)
    print(f"\n  통과: {passed}/{total}")


# ============================================================
# 메인
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="TC-1(이미지) 포함 전체 실행")
    args = parser.parse_args()

    print("=" * 60)
    print("  Qwen2.5-VL-7B-Instruct sLLM 테스트")
    print(f"  모델: {os.getenv('VLLM_MODEL', '(env 없음)')}")
    print(f"  서버: {os.getenv('VLLM_API_BASE', '(env 없음)')}")
    print("=" * 60)

    test_tc2()
    test_tc3()
    test_tc4()

    if args.all:
        test_tc1()

    print_summary()
