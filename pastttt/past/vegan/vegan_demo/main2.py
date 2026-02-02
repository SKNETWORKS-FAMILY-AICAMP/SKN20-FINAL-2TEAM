# vegan_demo/main2.py
# LangGraph + 공식 OpenAI SDK 버전

import sys
import io
import os
import base64
import json
from typing import TypedDict, Any
from openai import OpenAI
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END


# --- 상태 정의 ---
class AgentState(TypedDict):
    image_path: str   # 이미지 파일 경로
    image_type: str  # 'food' or 'ingredients'
    extracted_ingredients: str # 원재료명 리스트
    food_name: str # 음식 이름
    estimated_ingredients: str # 예상 재료 리스트
    analysis_result: dict # 비건 분석 결과
    final_result: str # 최종 답변
    client: OpenAI


# --- 도우미 함수 ---
def encode_image(image_path: str):
    """이미지 파일을 Base64로 인코딩합니다."""
    try:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except FileNotFoundError:
        return None


# --- 노드 ---

# 들어온 이미지가 음식 사진인지 성분표인지 판단
def detect_image_type(state: AgentState) -> AgentState:
    base64_image = encode_image(state['image_path'])

    response = state['client'].chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "이미지를 음식 사진인지, 원재료명 리스트가 적힌 글자 사진인지 분류해라. "
                                           "음식 사진이면 'food', 원재료명 리스트이면 'ingredients'로 대답해라."},
            {"role": "user", "content": [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}]},
        ],
        max_tokens=5,
    )
    state['image_type'] = response.choices[0].message.content.lower().strip()
    print(f"[detect_image_type] 판별 결과: {state['image_type']}")

    return state


# 성분표 이미지 -> 원재료명 추출
def extract_ingredients(state: AgentState) -> AgentState:
    base64_image = encode_image(state['image_path'])

    response = state['client'].chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "user", "content": [
                {"type": "text", "text": "이미지에서 원재료명에 해당하는 텍스트만 모두 추출해서, 쉼표(,)로 구분된 하나의 문자열로 만들어라."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
            ]}
        ],
        max_tokens=1000,
    )
    state['extracted_ingredients'] = response.choices[0].message.content
    print(f"[extract_ingredients] 성분 추출 완료")

    return state


# 음식 이미지 -> 이름&예상 재료 분석
def recognize_food(state: AgentState) -> AgentState:
    base64_image = encode_image(state['image_path'])

    response = state['client'].chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "음식 이름과 추정 재료를 JSON으로 반환해라. 형식: {\"food_name\": \"...\", \"estimated_ingredients\": \"...\"}"},
            {"role": "user", "content": [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}]}
        ]
    )
    food_info = json.loads(response.choices[0].message.content)
    state['food_name'] = food_info.get("food_name", "음식")
    state['estimated_ingredients'] = food_info.get("estimated_ingredients", "")

    return state


# 추출한 원재료명을 보고 비건 7단계중 어디에 해당하는지 분석
def analyze_ingredients(state: AgentState) -> AgentState:
    """추출된 성분 텍스트를 비건 7단계에 따라 분석하고 분류합니다."""
    print(f"[analyze_ingredients] 성분 분석 시작")

    # 분석할 성분 텍스트 결정
    ingredients_to_analyze = None
    if state['image_type'] == 'ingredients' and state.get('extracted_ingredients'):
        ingredients_to_analyze = state['extracted_ingredients']
    elif state['image_type'] == 'food' and state.get('estimated_ingredients'):
        ingredients_to_analyze = state['estimated_ingredients']

    if not ingredients_to_analyze:
        state['analysis_result'] = None
        return state

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
    1. \"classification_name\": 단계의 이름 (e.g., \"1단계: 비건 (Vegan)\", \"채식주의자에게 적합하지 않음\").
    2. \"reason\": 왜 그렇게 분류되었는지, 판단의 근거가 된 주요 성분을 명시하여 상세히 설명하는 문자열.
    3. \"contains_ingredients\": 판단의 근거가 된 성분 리스트 (e.g., [\"탈지분유\", \"유당\"])
    """

    try:
        response = state['client'].chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"다음은 제품의 원재료명 리스트입니다. 분석해주세요: {ingredients_to_analyze}"}
            ]
        )
        state['analysis_result'] = json.loads(response.choices[0].message.content)
        print(f"[analyze_ingredients] 성분 분석 완료")
    except Exception as e:
        print(f"[analyze_ingredients] Error: {e}")
        state['analysis_result'] = None

    return state


# 답변 포맷팅
def format_result(state: AgentState) -> AgentState:
    """분석 결과를 최종 형식으로 포맷합니다."""
    print(f"[format_result] 결과 포맷팅 시작")

    if state['image_type'] == 'ingredients':
        result_string = f"""
[이미지 종류: 원재료명]
추출된 원재료명 전체:
---
{state.get('extracted_ingredients', 'N/A')}
---
====================
"""
        if state['analysis_result']:
            name = state['analysis_result'].get("classification_name", "분류 불가")
            reason = state['analysis_result'].get("reason", "이유를 파악할 수 없습니다.")
            contains = state['analysis_result'].get("contains_ingredients", [])
            result_string += f"""판정: {name}
분류 근거:
  - {reason}
"""
            if contains:
                result_string += f"  - 주요 성분: {', '.join(contains)}\n"
        else:
            result_string += "성분 분석에 실패했습니다."

    elif state['image_type'] == 'food':
        result_string = f"""
[이미지 종류: 음식 사진]
음식 이름: {state.get('food_name', '이름 모를 음식')}
예상 재료: {state.get('estimated_ingredients', '')}
---
"""
        if not state.get('estimated_ingredients'):
            result_string += "재료를 예상할 수 없어, 비건 단계 분석을 생략합니다."
        elif state['analysis_result']:
            name = state['analysis_result'].get("classification_name", "분류 불가")
            reason = state['analysis_result'].get("reason", "이유를 파악할 수 없습니다.")
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

    state['final_result'] = result_string
    print(f"[format_result] 결과 포맷팅 완료")
    return state


# --- 조건부 분기 함수 ---
def route_by_image_type(state: AgentState) -> str:
    """이미지 타입에 따라 다음 노드를 결정합니다."""
    if state['image_type'] == 'ingredients':
        return "extract_ingredients"
    else:
        return "recognize_food"


# --- 랭그래프 만들기 ---
def create_vegan_analyzer_graph():
    # 생성
    graph = StateGraph(AgentState)

    # 노드 추가
    graph.add_node("detect_image_type", detect_image_type)
    graph.add_node("extract_ingredients", extract_ingredients)
    graph.add_node("recognize_food", recognize_food)
    graph.add_node("analyze_ingredients", analyze_ingredients)
    graph.add_node("format_result", format_result)

    # 엣지 연결
    graph.set_entry_point("detect_image_type")

    # 조건부 분기: image_type에 따라 다른 노드로
    graph.add_conditional_edges(
        "detect_image_type",
        route_by_image_type,
        {
            "extract_ingredients": "extract_ingredients",
            "recognize_food": "recognize_food"
        }
    )

    graph.add_edge("extract_ingredients", "analyze_ingredients")
    graph.add_edge("recognize_food", "analyze_ingredients")
    graph.add_edge("analyze_ingredients", "format_result")
    graph.add_edge("format_result", END)

    return graph.compile()


# --- 메인 실행기 ---
class VeganAnalyzerWithLangGraph:
    """LangGraph + 공식 OpenAI SDK를 사용한 비건 분석기"""
    def __init__(self):
        # main2.py 기준으로 프로젝트 루트의 .env 파일 경로 계산
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(current_dir))  # vegan_demo -> vegan -> SKN20-FINAL-2TEAM
        env_path = os.path.join(project_root, '.env')

        if not load_dotenv(dotenv_path=env_path):
            print(f"경고: .env 파일을 찾을 수 없습니다. (경로: {env_path})")

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key or api_key == "YOUR_OPENAI_API_KEY":
            self.client = None
        else:
            self.client = OpenAI(api_key=api_key)

        self.graph = create_vegan_analyzer_graph()

    def run_scan(self, image_path: str) -> str:
        """이미지를 스캔하고 분석합니다."""
        if not self.client:
            return "에러: API 키가 유효하지 않습니다."

        print(f"\n[VeganAnalyzerWithLangGraph] 이미지 스캔 시작: {image_path}")

        initial_state = AgentState(
            image_path=image_path,
            image_type="",
            extracted_ingredients="",
            food_name="",
            estimated_ingredients="",
            analysis_result={},
            final_result="",
            client=self.client,
        )

        # 그래프 실행
        final_state = self.graph.invoke(initial_state)
        return final_state['final_result']


if __name__ == "__main__":
    # 터미널 한글 깨짐 방지
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

    # main2.py 기준으로 test_image 폴더 경로 계산
    current_dir = os.path.dirname(os.path.abspath(__file__))
    test_image_dir = os.path.join(current_dir, "test_image")

    analyzer = VeganAnalyzerWithLangGraph()

    # 테스트할 이미지 리스트
    images_to_test = [
        os.path.join(test_image_dir, "IMG_8393.jpg"),  # 원재료명 이미지
        os.path.join(test_image_dir, "test1.png")      # 음식 사진 이미지
    ]

    final_output = ""
    for image in images_to_test:
        result = analyzer.run_scan(image)
        final_output += f"===== {image} 분석 결과 =====\n{result}\n\n"

    # 최종 결과를 파일에 저장
    result_path = os.path.join(current_dir, "result.txt")
    with open(result_path, "w", encoding="utf-8") as f:
        f.write(final_output)

    print(f"\n\n분석이 완료되었습니다. '{result_path}' 파일을 확인하세요.")
