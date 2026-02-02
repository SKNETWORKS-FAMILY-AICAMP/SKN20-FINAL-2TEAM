# vegan_demo/main3_claude.py
"""
LangGraph 기반 비건 분석 시스템

이미지(음식 사진 또는 원재료명 사진)를 분석하여 비건 7단계를 판정하는 시스템
fashion/demo.py 스타일로 구현
"""

import sys
import io
import os
import base64
import json
from typing import TypedDict, List, Dict, Any, Optional, Literal

from openai import OpenAI
from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END


# ===== 전역 변수 =====
_client: OpenAI = None
_graph = None


# ===== GraphState 정의 =====
class GraphState(TypedDict):
    """LangGraph 상태 관리"""
    image_path: str           # 이미지 파일 경로
    image_type: str           # 'food' or 'ingredients' or 'error'
    extracted_ingredients: str # 원재료명 리스트
    food_name: str            # 음식 이름
    estimated_ingredients: str # 예상 재료 리스트
    analysis_result: Optional[Dict[str, Any]]  # 비건 분석 결과
    final_result: str         # 최종 답변


# ===== Helper Functions =====
def encode_image(image_path: str) -> Optional[str]:
    """이미지 파일을 Base64로 인코딩합니다."""
    try:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except FileNotFoundError:
        print(f"[ERROR] 이미지 파일을 찾을 수 없습니다: {image_path}")
        return None


# ===== Node Functions =====
def detect_image_type_node(state: GraphState) -> dict:
    """노드 1: 이미지 타입 판별 (음식 vs 원재료명)"""
    print("\n" + "=" * 60)
    print("[NODE: detect_image_type] 이미지 타입 판별")
    print("=" * 60)

    global _client
    image_path = state["image_path"]

    base64_image = encode_image(image_path)
    if not base64_image:
        print("[detect_image_type] 이미지 인코딩 실패")
        return {"image_type": "error"}

    try:
        response = _client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "You are an image classifier. Determine if the image primarily shows a prepared food dish, or a text-heavy ingredient list. Your response must be a single word: 'food' or 'ingredients'."
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                },
            ],
            max_tokens=10,
        )
        image_type = response.choices[0].message.content.lower().strip()
        print(f"[detect_image_type] 판별 결과: {image_type}")
        return {"image_type": image_type}

    except Exception as e:
        print(f"[detect_image_type] Error: {e}")
        return {"image_type": "error"}


def extract_ingredients_node(state: GraphState) -> dict:
    """노드 2a: 원재료명 이미지에서 텍스트 추출"""
    print("\n" + "=" * 60)
    print("[NODE: extract_ingredients] 원재료명 추출")
    print("=" * 60)

    global _client
    image_path = state["image_path"]

    base64_image = encode_image(image_path)
    if not base64_image:
        return {"extracted_ingredients": ""}

    try:
        response = _client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "이 이미지는 제품의 '원재료명' 부분입니다. 이미지에서 원재료명에 해당하는 텍스트만 모두 추출해서, 쉼표(,)로 구분된 하나의 문자열로 만들어주세요. 다른 설명이나 줄바꿈 없이 텍스트만 응답해주세요."
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                        },
                    ]
                }
            ],
            max_tokens=1000,
        )
        ingredients = response.choices[0].message.content
        print(f"[extract_ingredients] 추출 완료: {len(ingredients)} 글자")
        return {"extracted_ingredients": ingredients}

    except Exception as e:
        print(f"[extract_ingredients] Error: {e}")
        return {"extracted_ingredients": ""}


def recognize_food_node(state: GraphState) -> dict:
    """노드 2b: 음식 이미지에서 음식명 및 예상 재료 분석"""
    print("\n" + "=" * 60)
    print("[NODE: recognize_food] 음식 인식 및 재료 추정")
    print("=" * 60)

    global _client
    image_path = state["image_path"]

    base64_image = encode_image(image_path)
    if not base64_image:
        return {"food_name": "알 수 없음", "estimated_ingredients": ""}

    try:
        response = _client.chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "You are a food expert. Analyze the food in the image. Your response must be a JSON object with two keys: 'food_name' (the name of the dish) and 'estimated_ingredients' (a comma-separated string of likely main ingredients)."
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }
            ]
        )
        food_info = json.loads(response.choices[0].message.content)
        food_name = food_info.get("food_name", "음식")
        estimated_ingredients = food_info.get("estimated_ingredients", "")

        print(f"[recognize_food] 음식명: {food_name}")
        print(f"[recognize_food] 예상 재료: {estimated_ingredients[:50]}...")

        return {
            "food_name": food_name,
            "estimated_ingredients": estimated_ingredients
        }

    except Exception as e:
        print(f"[recognize_food] Error: {e}")
        return {"food_name": "알 수 없음", "estimated_ingredients": ""}


def analyze_vegan_level_node(state: GraphState) -> dict:
    """노드 3: 비건 7단계 분석"""
    print("\n" + "=" * 60)
    print("[NODE: analyze_vegan_level] 비건 단계 분석")
    print("=" * 60)

    global _client
    image_type = state["image_type"]

    # 분석할 재료 결정
    if image_type == "ingredients":
        ingredients_to_analyze = state.get("extracted_ingredients", "")
    else:
        ingredients_to_analyze = state.get("estimated_ingredients", "")

    if not ingredients_to_analyze:
        print("[analyze_vegan_level] 분석할 재료 없음")
        return {"analysis_result": None}

    system_prompt = """
당신은 음식 성분을 분석하여 비건 및 베지테리언 7단계에 따라 분류하는 전문가입니다.
주어진 원재료명 리스트를 분석하여, 어떤 단계까지 허용되는 제품인지 판단합니다.
가장 엄격한 단계부터 검사하여 해당하는 가장 낮은 숫자(가장 엄격한)의 단계를 찾아냅니다.

[분류 기준]
1. 비건 (Vegan): 완전 채식.
2. 락토 베지테리언 (Lacto Vegetarian): 유제품 O, 달걀 X
3. 오보 베지테리언 (Ovo Vegetarian): 달걀 O, 유제품 X
4. 락토-오보 베지테리언 (Lacto-Ovo Vegetarian): 유제품 O, 달걀 O
5. 페스코 베지테리언 (Pesco / Pescatarian): 생선/해산물 O
6. 폴로 베지테리언 (Pollo Vegetarian): 닭고기 O
7. 플렉시테리언 (Flexitarian): 주로 채식, 때때로 육류 섭취. (이 단계는 식습관이므로 제품 분류에는 사용하지 않습니다.)

[분석 규칙]
- 붉은 고기(소, 돼지), 젤라틴, 카민 등 명백한 동물성 재료가 있으면 '채식주의자에게 적합하지 않음'으로 분류합니다.
- 그 외에는 1~6단계 중 해당하는 가장 엄격한 단계를 판정합니다.

[응답 형식]
응답은 반드시 JSON 형식이어야 하며, 다음 3개의 키를 포함해야 합니다.
1. "classification_name": 단계의 이름 (e.g., "1단계: 비건 (Vegan)", "채식주의자에게 적합하지 않음").
2. "reason": 왜 그렇게 분류되었는지, 판단의 근거가 된 주요 성분을 명시하여 상세히 설명하는 문자열.
3. "contains_ingredients": 판단의 근거가 된 성분 리스트 (e.g., ["탈지분유", "유당"])
"""

    try:
        response = _client.chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"다음은 제품의 원재료명 리스트입니다. 분석해주세요: {ingredients_to_analyze}"}
            ]
        )
        analysis_result = json.loads(response.choices[0].message.content)
        print(f"[analyze_vegan_level] 판정: {analysis_result.get('classification_name', 'N/A')}")
        return {"analysis_result": analysis_result}

    except Exception as e:
        print(f"[analyze_vegan_level] Error: {e}")
        return {"analysis_result": None}


def format_result_node(state: GraphState) -> dict:
    """노드 4: 최종 결과 포맷팅"""
    print("\n" + "=" * 60)
    print("[NODE: format_result] 결과 포맷팅")
    print("=" * 60)

    image_type = state["image_type"]
    analysis_result = state.get("analysis_result")

    if image_type == "ingredients":
        result_string = f"""
[이미지 종류: 원재료명]
추출된 원재료명 전체:
---
{state.get('extracted_ingredients', 'N/A')}
---
====================
"""
        if analysis_result:
            name = analysis_result.get("classification_name", "분류 불가")
            reason = analysis_result.get("reason", "이유를 파악할 수 없습니다.")
            contains = analysis_result.get("contains_ingredients", [])
            result_string += f"""판정: {name}
분류 근거:
  - {reason}
"""
            if contains:
                result_string += f"  - 주요 성분: {', '.join(contains)}\n"
        else:
            result_string += "성분 분석에 실패했습니다."

    elif image_type == "food":
        result_string = f"""
[이미지 종류: 음식 사진]
음식 이름: {state.get('food_name', '이름 모를 음식')}
예상 재료: {state.get('estimated_ingredients', '')}
---
"""
        if not state.get('estimated_ingredients'):
            result_string += "재료를 예상할 수 없어, 비건 단계 분석을 생략합니다."
        elif analysis_result:
            name = analysis_result.get("classification_name", "분류 불가")
            reason = analysis_result.get("reason", "이유를 파악할 수 없습니다.")
            result_string += f"""
====================
예상 비건 단계 판정: {name}
분류 근거:
  - {reason}
(※ 예상 재료 기반의 분석이므로 실제와 다를 수 있습니다.)
"""
        else:
            result_string += "예상 재료에 대한 비건 단계 분석에 실패했습니다."

    else:
        result_string = f"이미지 종류를 판별할 수 없습니다: {state['image_path']}"

    print(f"[format_result] 포맷팅 완료")
    return {"final_result": result_string}


# ===== Conditional Edge Functions =====
def route_by_image_type(state: GraphState) -> Literal["extract_ingredients", "recognize_food", "format_result"]:
    """이미지 타입에 따라 다음 노드 결정"""
    image_type = state.get("image_type", "")

    print(f"\n[ROUTING] image_type='{image_type}' → ", end="")

    if image_type == "ingredients":
        print("extract_ingredients")
        return "extract_ingredients"
    elif image_type == "food":
        print("recognize_food")
        return "recognize_food"
    else:
        print("format_result (error)")
        return "format_result"


# ===== Graph Builder =====
def build_vegan_analyzer_graph():
    """LangGraph 비건 분석기 구축"""
    print("\n" + "=" * 60)
    print("[GRAPH BUILD] LangGraph 비건 분석기 구축")
    print("=" * 60)

    graph = StateGraph(GraphState)

    # 노드 추가
    graph.add_node("detect_image_type", detect_image_type_node)
    graph.add_node("extract_ingredients", extract_ingredients_node)
    graph.add_node("recognize_food", recognize_food_node)
    graph.add_node("analyze_vegan_level", analyze_vegan_level_node)
    graph.add_node("format_result", format_result_node)

    print("[GRAPH] 5개 노드 추가 완료")

    # 엣지 추가
    graph.add_edge(START, "detect_image_type")

    # 조건부 엣지: 이미지 타입에 따라 분기
    graph.add_conditional_edges(
        "detect_image_type",
        route_by_image_type,
        {
            "extract_ingredients": "extract_ingredients",
            "recognize_food": "recognize_food",
            "format_result": "format_result"  # error 케이스
        }
    )

    graph.add_edge("extract_ingredients", "analyze_vegan_level")
    graph.add_edge("recognize_food", "analyze_vegan_level")
    graph.add_edge("analyze_vegan_level", "format_result")
    graph.add_edge("format_result", END)

    print("[GRAPH] 엣지 추가 완료")

    compiled_graph = graph.compile()
    print("[GRAPH] 컴파일 완료")

    return compiled_graph


# ===== External API Functions =====
def initialize_vegan_system() -> dict:
    """비건 분석 시스템 초기화"""
    global _client, _graph

    try:
        print("\n[INIT] 비건 분석 시스템 초기화 중...")

        # .env 파일 로드
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(current_dir))
        env_path = os.path.join(project_root, '.env')

        if not load_dotenv(dotenv_path=env_path):
            print(f"[WARN] .env 파일을 찾을 수 없습니다: {env_path}")

        # OpenAI 클라이언트 생성
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key or api_key == "YOUR_OPENAI_API_KEY":
            raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다.")

        _client = OpenAI(api_key=api_key)
        print("[INIT] OpenAI 클라이언트 생성 완료")

        # LangGraph 컴파일
        _graph = build_vegan_analyzer_graph()

        print("[SUCCESS] 초기화 완료!\n")
        return {"status": "success", "message": "Initialized successfully"}

    except Exception as e:
        print(f"[ERROR] 초기화 실패: {e}")
        return {"status": "error", "message": str(e)}


def analyze_image(image_path: str, verbose: bool = True) -> dict:
    """이미지 분석 실행"""
    global _client, _graph

    if _graph is None:
        return {"success": False, "error": "시스템이 초기화되지 않았습니다."}

    try:
        if verbose:
            print(f"\n[ANALYZE] 이미지 분석 시작: {image_path}")

        # 초기 상태
        initial_state = {
            "image_path": image_path,
            "image_type": "",
            "extracted_ingredients": "",
            "food_name": "",
            "estimated_ingredients": "",
            "analysis_result": None,
            "final_result": "",
        }

        # 그래프 실행
        result = _graph.invoke(initial_state)

        if verbose:
            print("\n[ANALYZE] 분석 완료")

        return {
            "success": True,
            "image_path": image_path,
            "image_type": result.get("image_type", ""),
            "result": result.get("final_result", ""),
            "analysis": result.get("analysis_result"),
            "metadata": {
                "food_name": result.get("food_name", ""),
                "extracted_ingredients": result.get("extracted_ingredients", ""),
                "estimated_ingredients": result.get("estimated_ingredients", ""),
            }
        }

    except Exception as e:
        print(f"[ERROR] 분석 오류: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


def get_system_status() -> dict:
    """시스템 상태 조회"""
    return {
        "initialized": _graph is not None,
        "client_loaded": _client is not None,
    }


# ===== Main Execution =====
if __name__ == "__main__":
    # 터미널 한글 깨짐 방지
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

    # 시스템 초기화
    init_result = initialize_vegan_system()
    if init_result["status"] != "success":
        print(f"[ERROR] 초기화 실패: {init_result['message']}")
        sys.exit(1)

    # 시스템 상태 확인
    status = get_system_status()
    print("\n[시스템 상태]")
    for key, value in status.items():
        print(f"  {key}: {'✅' if value else '❌'}")

    # 테스트 이미지 경로
    current_dir = os.path.dirname(os.path.abspath(__file__))
    test_image_dir = os.path.join(current_dir, "test_image")


    images_to_test = [
        os.path.join(test_image_dir, "IMG_8393.jpg"),  # 원재료명 이미지
        os.path.join(test_image_dir, "test1.png"),     # 음식 사진 이미지
        os.path.join(test_image_dir, "test3.jpg")      # 음식 사진 이미지
    ]

    # 분석 실행
    final_output = ""
    for image in images_to_test:
        result = analyze_image(image, verbose=True)

        if result["success"]:
            final_output += f"===== {image} 분석 결과 =====\n{result['result']}\n\n"
        else:
            final_output += f"===== {image} 분석 결과 =====\n에러: {result['error']}\n\n"

    # 결과 저장
    result_path = os.path.join(current_dir, "result.txt")
    with open(result_path, "w", encoding="utf-8") as f:
        f.write(final_output)

    print(f"\n\n{'=' * 60}")
    print(f"분석이 완료되었습니다. '{result_path}' 파일을 확인하세요.")
    print(f"{'=' * 60}")
