from typing import TypedDict
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from openai import OpenAI
from dotenv import load_dotenv
import base64
from pathlib import Path
import os

load_dotenv()

# .env 파일에서 API 키 로드

# .env 파일 로드
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
env_path = os.path.join(project_root, '.env')

if not load_dotenv(env_path):
    print("경고: .env 파일을 찾을 수 없거나 경로가 잘못되었습니다.")

# OpenAI 클라이언트 초기화
api_key = os.getenv("OPENAI_API_KEY")
if not api_key or api_key == "YOUR_OPENAI_API_KEY":
    print("에러: .env 파일에 유효한 OPENAI_API_KEY를 설정해야 합니다.")
    client = None
else:
    client = OpenAI(api_key=api_key)

# State 정의
class State(TypedDict):
    question: str
    image_path: str
    image_type: str  # food or ingredients
    ingredient_list: list  # 원재료명 리스트
    food_name: str
    expected_ingredients: list  # 예상 재료 리스트
    vegan_level: int  # 1~7
    answer: str

llm = ChatOpenAI(model="gpt-4o", temperature=0)


# 이미지를 base64로 인코딩
def encode_image(image_path: str) -> str:
    with open(image_path, "rb") as image_file:
        return base64.standard_b64encode(image_file.read()).decode("utf-8")

# detect 노드: 이미지 타입 판단 (food or ingredients)
def detect(state: State):
    image_path = state["image_path"]
    base64_image = encode_image(image_path)
    
    response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an image classifier. Determine if the image primarily shows a prepared food dish, or a text-heavy ingredient list. Your response must be a single word: 'food' or 'ingredients'."},
                {"role": "user", "content": [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}]},
            ],
            max_tokens=5,
        )
    
    # Vision API 호출 (간단화 버전)
    # 실제로는 이미지를 전달해야 하지만, 데모용으로 간단화
    result = llm.invoke(response).content
    
    image_type = response.choices[0].message.content.lower()
    return {"image_type": image_type}

# food 노드: 음식 사진 분석
def food_node(state: State):
    prompt = f"""
    다음 질문을 바탕으로 음식 사진을 분석해주세요:
    질문: {state['question']}
    
    아래 형식으로 답변해주세요:
    음식이름: [음식 이름]
    예상재료: [쉼표로 구분된 재료 리스트]
    """
    
    result = llm.invoke(prompt).content
    
    food_name = ""
    expected_ingredients = []
    
    for line in result.split('\n'):
        line = line.strip()
        if '음식이름' in line:
            parts = line.split(':', 1)
            if len(parts) > 1:
                food_name = parts[1].strip()
        elif '예상재료' in line:
            parts = line.split(':', 1)
            if len(parts) > 1:
                expected_ingredients = [ing.strip() for ing in parts[1].split(',')]
    
    return {
        "food_name": food_name or "알 수 없는 음식",
        "expected_ingredients": expected_ingredients or []
    }

# ingredients 노드: 원재료 추출
def ingredients_node(state: State):
    prompt = f"""
    다음 원재료 사진에서 모든 재료명을 추출해주세요:
    질문: {state['question']}
    
    쉼표로 구분된 재료명 리스트로만 답변해주세요.
    """
    
    result = llm.invoke(prompt).content
    ingredient_list = [ing.strip() for ing in result.split(',') if ing.strip()]
    
    return {"ingredient_list": ingredient_list}

# vegan_level 노드: 비건 단계 분석
def vegan_level_node(state: State):
    ingredients = state.get("expected_ingredients", []) or state.get("ingredient_list", [])
    
    system_prompt = """
    [분류 기준]
    1. 비건 (Vegan): 완전 채식.
    2. 락토 베지테리언 (Lacto Vegetarian): 유제품 O, 달걀 X
    3. 오보 베지테리언 (Ovo Vegetarian): 달걀 O, 유제품 X
    4. 락토-오보 베지테리언 (Lacto-Ovo Vegetarian): 유제품 O, 달걀 O
    5. 페스코 베지테리언 (Pesco / Pescatarian): 생선/해산물 O
    6. 폴로 베지테리언 (Pollo Vegetarian): 닭고기 O
    7. 플렉시테리언 (Flexitarian): 주로 채식, 때때로 육류 섭취.
    
    주어진 재료 리스트를 분석해 어떤 단계까지 허용되는 제품인지 판단한다.
    1~7중 하나의 숫자만 반환한다.
    """
    
    prompt = f"""
    {system_prompt}
    
    재료 리스트: {', '.join(ingredients)}
    
    1~7 중 하나의 숫자만 답변해주세요.
    """
    
    result = llm.invoke(prompt).content
    
    # 안전한 숫자 추출
    digits = ''.join(filter(str.isdigit, result))
    vegan_level = int(digits) if digits else 4  # 기본값 4 (락토-오보 베지테리언)
    
    # 범위 체크 (1~7만 유효)
    vegan_level = max(1, min(vegan_level, 7))
    
    return {"vegan_level": vegan_level}

# answer 노드: 최종 답변 생성
def answer_node(state: State):
    prompt = f"""
    사용자의 질문: {state['question']}
    
    분석 결과:
    - 음식: {state.get('food_name', '불명')}
    - 재료: {', '.join(state.get('expected_ingredients', []) or state.get('ingredient_list', []))}
    - 비건 레벨: {state['vegan_level']}/7 (1=완전비건, 7=육류포함)
    
    위 정보를 바탕으로 사용자에게 친근한 한국어로 답변해주세요.
    """
    
    result = llm.invoke(prompt).content
    return {"answer": result}

# Graph 구성
graph = StateGraph(State)

graph.add_node("detect", detect)
graph.add_node("food", food_node)
graph.add_node("ingredients", ingredients_node)
graph.add_node("vegan_level", vegan_level_node)
graph.add_node("answer", answer_node)

graph.set_entry_point("detect")

# detect 후 이미지 타입에 따라 분기
graph.add_conditional_edges(
    "detect",
    lambda state: "food" if state["image_type"] == "food" else "ingredients",
    {
        "food": "food",
        "ingredients": "ingredients"
    }
)

graph.add_edge("food", "vegan_level")
graph.add_edge("ingredients", "vegan_level")
graph.add_edge("vegan_level", "answer")
graph.add_edge("answer", END)

app = graph.compile()

# 실행 예제
result = app.invoke({
    "question": "이 음식이 비건인가요?",
    "image_path": "C:\\Users\\playdata2\\Desktop\\SKN_AI_20\\SKN20-FINAL-2TEAM\\vegan\\vegan_demo\\test_image\\IMG_8393.jpg",
    "image_type": "",
    "ingredient_list": [],
    "food_name": "",
    "expected_ingredients": [],
    "vegan_level": 0,
    "answer": ""
})

print(f"\n🥗 최종 답변:\n{result['answer']}")
print(f"비건 레벨: {result['vegan_level']}/7")