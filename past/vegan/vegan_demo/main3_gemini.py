# vegan_demo/main3_laggraph.py

import sys
import io
import os
import base64
import json
from typing import TypedDict
from openai import OpenAI
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END

# --- 기본 설정 ---

# 터미널 한글 깨짐 방지
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# .env 파일에서 API 키 로드
# 스크립트의 현재 위치를 기준으로 프로젝트 루트 경로를 계산합니다.
# 이 스크립트(vegan_demo/main3_laggraph.py)에서 루트(SKN20-FINAL-2TEAM)까지 두 단계 상위로 이동합니다.
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
env_path = os.path.join(project_root, '.env')

if load_dotenv(dotenv_path=env_path):
    print(f".env 파일 로드 성공: {env_path}")
else:
    print(f"경고: .env 파일을 다음 경로에서 찾을 수 없습니다: {env_path}")

# OpenAI 클라이언트 초기화
api_key = os.getenv("OPENAI_API_KEY")
if not api_key or api_key == "YOUR_OPENAI_API_KEY":
    print("에러: .env 파일에 유효한 OPENAI_API_KEY를 설정해야 합니다.")
    client = None
else:
    client = OpenAI(api_key=api_key)

# --- 상태 정의 ---

class VeganCheckState(TypedDict):
    """그래프의 각 노드 간에 전달될 상태를 정의합니다."""
    image_path: str                 # 입력된 이미지 경로
    image_type: str                 # 판별된 이미지 종류 ('food', 'ingredients', 'error')
    ingredients_text: str | None    # 추출된 원재료명 또는 예상 재료
    food_name: str | None           # 인식된 음식 이름
    analysis_result: dict | None    # 성분 분석 결과 (JSON)
    final_output: str | None        # 최종적으로 사용자에게 보여줄 결과 문자열
    error_message: str | None       # 에러 발생 시 메시지

# --- Helper 함수 ---

def encode_image(image_path: str) -> str | None:
    """이미지 파일을 Base64로 인코딩합니다."""
    try:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except FileNotFoundError:
        print(f"오류: 이미지 파일을 찾을 수 없습니다 - {image_path}")
        return None

# --- 그래프의 각 노드(기능) 정의 ---

def detect_image_type(state: VeganCheckState) -> dict:
    """이미지의 종류가 '음식'인지 '성분표'인지 판단합니다."""
    print(f"\n[Node: detect_image_type] 이미지 종류 판별 시작: {state['image_path']}")
    if not client: return {"error_message": "API 키가 유효하지 않습니다."}
    
    base64_image = encode_image(state['image_path'])
    if not base64_image: return {"error_message": f"이미지를 읽을 수 없습니다: {state['image_path']}"}
        
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an image classifier. Determine if the image primarily shows a prepared food dish, or a text-heavy ingredient list. Your response must be a single word: 'food' or 'ingredients'."},
                {"role": "user", "content": [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}]},
            ],
            max_tokens=5,
        )
        image_type = response.choices[0].message.content.lower()
        print(f"[Node: detect_image_type] 판별 결과: '{image_type}'")
        return {"image_type": image_type}
    except Exception as e:
        print(f"[Node: detect_image_type] 오류: {e}")
        return {"image_type": "error", "error_message": str(e)}

def extract_ingredients_from_image(state: VeganCheckState) -> dict:
    """(성분표 이미지용) 이미지에서 텍스트(성분)를 추출합니다."""
    print("[Node: extract_ingredients_from_image] 원재료명 추출 시작")
    if not client: return {"error_message": "API 키가 유효하지 않습니다."}

    base64_image = encode_image(state['image_path'])
    if not base64_image: return {"error_message": f"이미지를 읽을 수 없습니다: {state['image_path']}"}

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "user", "content": [
                    {"type": "text", "text": "이 이미지는 제품의 '원재료명' 부분입니다. 이미지에서 원재료명에 해당하는 텍스트만 모두 추출해서, 쉼표(,)로 구분된 하나의 문자열로 만들어주세요. 다른 설명이나 줄바꿈 없이 텍스트만 응답해주세요."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                ]}
            ],
            max_tokens=1000,
        )
        ingredients = response.choices[0].message.content
        print(f"[Node: extract_ingredients_from_image] 추출된 원재료명: {ingredients[:100]}...")
        return {"ingredients_text": ingredients}
    except Exception as e:
        print(f"[Node: extract_ingredients_from_image] 오류: {e}")
        return {"error_message": f"성분 추출 중 오류 발생: {e}"}

def recognize_food(state: VeganCheckState) -> dict:
    """(음식 사진용) 음식 이름과 예상 재료를 분석합니다."""
    print("[Node: recognize_food] 음식 인식 시작")
    if not client: return {"error_message": "API 키가 유효하지 않습니다."}

    base64_image = encode_image(state['image_path'])
    if not base64_image: return {"error_message": f"이미지를 읽을 수 없습니다: {state['image_path']}"}

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are a food expert. Analyze the food in the image. Your response must be a JSON object with two keys: 'food_name' (the name of the dish) and 'estimated_ingredients' (a comma-separated string of likely main ingredients)."},
                {"role": "user", "content": [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}]}
            ]
        )
        food_info = json.loads(response.choices[0].message.content)
        print(f"[Node: recognize_food] 음식 이름: {food_info.get('food_name')}, 예상 재료: {food_info.get('estimated_ingredients')}")
        return {
            "food_name": food_info.get("food_name"),
            "ingredients_text": food_info.get("estimated_ingredients") # 분석을 위해 ingredients_text 필드 사용
        }
    except Exception as e:
        print(f"[Node: recognize_food] 오류: {e}")
        return {"error_message": f"음식 인식 중 오류 발생: {e}"}

def analyze_ingredients(state: VeganCheckState) -> dict:
    """추출된 성분을 비건 7단계에 따라 분석합니다."""
    print("[Node: analyze_ingredients] 비건 단계 분석 시작")
    if not client: return {"error_message": "API 키가 유효하지 않습니다."}
    
    ingredients_text = state.get("ingredients_text")
    if not ingredients_text:
        return {"error_message": "분석할 재료 정보가 없습니다."}

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
    7. 플렉시테리언 (Flexitarian): 이 단계는 제품 분류에 사용하지 않습니다.
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
        response = client.chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"다음은 제품의 원재료명 리스트입니다. 분석해주세요: {ingredients_text}"}
            ]
        )
        analysis = json.loads(response.choices[0].message.content)
        print(f"[Node: analyze_ingredients] 분석 결과: {analysis.get('classification_name')}")
        return {"analysis_result": analysis}
    except Exception as e:
        print(f"[Node: analyze_ingredients] 오류: {e}")
        return {"error_message": f"성분 분석 중 오류 발생: {e}"}

def format_result(state: VeganCheckState) -> dict:
    """모든 정보를 취합하여 최종 결과 문자열을 생성합니다."""
    print("[Node: format_result] 최종 결과 생성")
    if state.get("error_message"):
        return {"final_output": f"오류 발생: {state['error_message']}"}

    image_type = state['image_type']
    analysis = state.get("analysis_result")
    
    if not analysis:
        return {"final_output": "성분 분석 결과가 없어 최종 결과를 생성할 수 없습니다."}

    name = analysis.get("classification_name", "분류 불가")
    reason = analysis.get("reason", "이유를 파악할 수 없습니다.")
    contains = analysis.get("contains_ingredients", [])

    if image_type == 'ingredients':
        ingredients = state.get("ingredients_text", "없음")
        result_string = f"""
[이미지 종류: 원재료명]
추출된 원재료명 전체:
---
{ingredients}
---
====================
판정: {name}
분류 근거:
  - {reason}"""
        if contains:
            result_string += f"  - 주요 성분: {', '.join(contains)}\n"
        return {"final_output": result_string}

    elif image_type == 'food':
        food_name = state.get("food_name", "이름 모를 음식")
        est_ingredients = state.get("ingredients_text", "")
        result_string = f"""
[이미지 종류: 음식 사진]
음식 이름: {food_name}
예상 재료: {est_ingredients}
---
====================
예상 비건 단계 판정: {name}
분류 근거:
  - {reason}
(※ 예상 재료 기반의 분석이므로 실제와 다를 수 있습니다.)
"""
        return {"final_output": result_string}
    
    else:
        return {"final_output": "알 수 없는 이미지 유형입니다."}


# --- 그래프 라우팅 로직 ---

def where_to_go_after_detection(state: VeganCheckState):
    """이미지 종류에 따라 다음 노드를 결정합니다."""
    if state.get("error_message"): return "end"
    
    image_type = state.get("image_type")
    if image_type == 'ingredients':
        return 'extract_ingredients_from_image'
    elif image_type == 'food':
        return 'recognize_food'
    else: # error or unknown
        return 'end'

def what_to_do_after_extraction(state: VeganCheckState):
    """성분 추출 후 분석할지, 끝낼지 결정합니다."""
    if state.get("error_message"): return "end"
    if not state.get("ingredients_text"): return "end" # 추출된 내용이 없으면 분석 없이 종료
    return "analyze_ingredients"

# --- 그래프 구성 ---

workflow = StateGraph(VeganCheckState)

# 노드 추가
workflow.add_node("detect_image_type", detect_image_type)
workflow.add_node("extract_ingredients_from_image", extract_ingredients_from_image)
workflow.add_node("recognize_food", recognize_food)
workflow.add_node("analyze_ingredients", analyze_ingredients)
workflow.add_node("format_result", format_result)

# 엣지(연결) 추가
workflow.set_entry_point("detect_image_type")

workflow.add_conditional_edges(
    "detect_image_type",
    where_to_go_after_detection,
    {
        "extract_ingredients_from_image": "extract_ingredients_from_image",
        "recognize_food": "recognize_food",
        "end": "format_result" # 에러 발생 시 바로 포맷팅으로 가서 에러 메시지 출력
    }
)

workflow.add_conditional_edges(
    "extract_ingredients_from_image",
    what_to_do_after_extraction,
    {
        "analyze_ingredients": "analyze_ingredients",
        "end": "format_result"
    }
)

workflow.add_conditional_edges(
    "recognize_food",
    what_to_do_after_extraction,
    {
        "analyze_ingredients": "analyze_ingredients",
        "end": "format_result" # 예상 재료가 없으면 분석 없이 종료
    }
)

workflow.add_edge("analyze_ingredients", "format_result")
workflow.add_edge("format_result", END)


# 그래프 컴파일
app = workflow.compile()


# --- 실행 ---

if __name__ == "__main__":
    if not client:
        sys.exit(1)

    # 테스트할 이미지 리스트 (스크립트 실행 위치 기준 상대 경로)
    images_to_test = [
        "test_image/IMG_8393.jpg", # 원재료명 이미지
        "test_image/test1.png"     # 음식 사진 이미지
    ]
    
    final_output_for_file = ""
    for image_path in images_to_test:
        # 초기 상태를 설정하여 그래프 실행
        initial_state = {"image_path": image_path}
        
        print(f"\n--- Running analysis for: {image_path} ---")
        # .invoke()를 사용해 최종 상태를 한번에 받습니다.
        final_state = app.invoke(initial_state)
        print("--- Analysis complete ---")

        # 최종 결과
        result_output = final_state.get("final_output", "결과를 생성하지 못했습니다.")
        
        # 원본과 동일한 형식의 헤더를 만들기 위해 경로를 조합합니다.
        original_image_path_for_header = f"vegan_demo/{image_path}"
        final_output_for_file += f"===== {original_image_path_for_header} 분석 결과 =====\n{result_output}\n\n"

    # 최종 결과를 파일에 저장 (현재 디렉토리에 저장)
    output_filename = "result_langgraph.txt"
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(final_output_for_file)

    print(f"\n\n분석이 완료되었습니다. '{output_filename}' 파일을 확인하세요.")
    print("\n--- 최종 파일 내용 ---")
    print(final_output_for_file)
