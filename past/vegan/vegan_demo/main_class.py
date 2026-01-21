# vegan_demo/main.py

import sys
import io
import os
import base64
import json
from openai import OpenAI
from dotenv import load_dotenv

# --- Helper function ---
def encode_image(image_path: str):
    """이미지 파일을 Base64로 인코딩합니다."""
    try:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except FileNotFoundError:
        return None

# --- 각 전문 Agent들의 클래스 정의 ---

class ImageTypeDetectorAgent:
    """이미지의 종류가 '음식'인지 '성분표'인지 판단합니다."""
    def detect_type(self, image_path: str, client: OpenAI):
        base64_image = encode_image(image_path)
        if not base64_image: return "error"
        
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are an image classifier. Determine if the image primarily shows a prepared food dish, or a text-heavy ingredient list. Your response must be a single word: 'food' or 'ingredients'."},
                    {"role": "user", "content": [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}]},
                ],
                max_tokens=5,
            )
            return response.choices[0].message.content.lower()
        except Exception as e:
            print(f"[ImageTypeDetectorAgent] Error: {e}")
            return "error"

class VisionAgent:
    """(성분표 이미지용) GPT-4o Vision을 사용해 이미지에서 텍스트(성분)를 추출합니다."""
    def extract_ingredients_from_image(self, image_path: str, client: OpenAI):
        base64_image = encode_image(image_path)
        if not base64_image: return None
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
            return response.choices[0].message.content
        except Exception as e:
            print(f"[VisionAgent] Error: {e}")
            return None

class FoodRecognitionAgent:
    """(음식 사진용) GPT-4o Vision을 사용해 음식 이름과 예상 재료를 분석합니다."""
    def recognize_food(self, image_path: str, client: OpenAI):
        base64_image = encode_image(image_path)
        if not base64_image: return None
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": "You are a food expert. Analyze the food in the image. Your response must be a JSON object with two keys: 'food_name' (the name of the dish) and 'estimated_ingredients' (a comma-separated string of likely main ingredients)."},
                    {"role": "user", "content": [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}]}
                ]
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"[FoodRecognitionAgent] Error: {e}")
            return None

class AnalysisAgent:
    """추출된 성분 텍스트를 비건 7단계에 따라 분석하고 분류합니다."""
    def check_ingredients(self, ingredients_text: str, client: OpenAI):
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
            response = client.chat.completions.create(
                model="gpt-4o",
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"다음은 제품의 원재료명 리스트입니다. 분석해주세요: {ingredients_text}"}
                ]
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"[AnalysisAgent] Error: {e}")
            return None

class MasterAgent:
    """전체 워크플로우를 조율하는 오케스트레이터"""
    def __init__(self):
        if not load_dotenv(dotenv_path='vegan_demo/.env'):
             print("경고: .env 파일을 찾을 수 없습니다.")
        
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key or api_key == "YOUR_OPENAI_API_KEY":
            self.client = None
        else:
            self.client = OpenAI(api_key=api_key)

        self.image_detector = ImageTypeDetectorAgent()
        self.vision_agent = VisionAgent()
        self.food_agent = FoodRecognitionAgent()
        self.analysis_agent = AnalysisAgent()

    def run_scan(self, image_path: str):
        if not self.client:
            return "에러: API 키가 유효하지 않습니다."

        print(f"\n[MasterAgent] 이미지 스캔 시작: {image_path}")
        image_type = self.image_detector.detect_type(image_path, self.client)
        print(f"[MasterAgent] 이미지 종류 판별: '{image_type}'")

        if image_type == 'ingredients':
            return self.handle_ingredients_image(image_path)
        elif image_type == 'food':
            return self.handle_food_image(image_path)
        else:
            return f"이미지 종류를 판별할 수 없습니다: {image_path}"

    def handle_ingredients_image(self, image_path):
        ingredients = self.vision_agent.extract_ingredients_from_image(image_path, self.client)
        if not ingredients: return "성분 추출에 실패했습니다."
        
        analysis = self.analysis_agent.check_ingredients(ingredients, self.client)
        if not analysis: return "성분 분석에 실패했습니다."

        name = analysis.get("classification_name", "분류 불가")
        reason = analysis.get("reason", "이유를 파악할 수 없습니다.")
        contains = analysis.get("contains_ingredients", [])

        result_string = f"""
[이미지 종류: 원재료명]
추출된 원재료명 전체:
---
{ingredients}
---
====================
판정: {name}
분류 근거:
  - {reason}
"""
        if contains:
            result_string += f"  - 주요 성분: {', '.join(contains)}\n"
        return result_string

    def handle_food_image(self, image_path):
        food_info = self.food_agent.recognize_food(image_path, self.client)
        if not food_info: return "음식 인식에 실패했습니다."
        
        food_name = food_info.get("food_name", "이름 모를 음식")
        est_ingredients = food_info.get("estimated_ingredients", "")
        
        result_string = f"""
[이미지 종류: 음식 사진]
음식 이름: {food_name}
예상 재료: {est_ingredients}
---
"""
        if not est_ingredients:
            result_string += "재료를 예상할 수 없어, 비건 단계 분석을 생략합니다."
            return result_string

        analysis = self.analysis_agent.check_ingredients(est_ingredients, self.client)
        if not analysis:
            result_string += "예상 재료에 대한 비건 단계 분석에 실패했습니다."
            return result_string

        name = analysis.get("classification_name", "분류 불가")
        reason = analysis.get("reason", "이유를 파악할 수 없습니다.")
        
        result_string += f"""
====================
예상 비건 단계 판정: {name}
분류 근거:
  - {reason}
(※ 예상 재료 기반의 분석이므로 실제와 다를 수 있습니다.)
"""
        return result_string

if __name__ == "__main__":
    # 터미널 한글 깨짐 방지
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

    master = MasterAgent()
    
    # 테스트할 이미지 리스트
    images_to_test = [
        "vegan_demo/test_image/IMG_8393.jpg", # 원재료명 이미지
        "vegan_demo/test_image/test1.png"     # 음식 사진 이미지
    ]
    
    final_output = ""
    for image in images_to_test:
        result = master.run_scan(image)
        final_output += f"===== {image} 분석 결과 =====\n{result}\n\n"

    # 최종 결과를 파일에 저장
    with open("vegan_demo/result.txt", "w", encoding="utf-8") as f:
        f.write(final_output)

    print("\n\n분석이 완료되었습니다. 'vegan_demo/result.txt' 파일을 확인하세요.")