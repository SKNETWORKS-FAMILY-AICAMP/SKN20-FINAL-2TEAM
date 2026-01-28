import os
import json
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
ADAPTER_PATH = BASE_DIR / "outputs/gemma3-1b-it-lora"
BASE_MODEL = "google/gemma-3-1b-it"

SYSTEM = (
    "너는 특허 청구항과 사용자 제품 구성을 비교하여 구성요소별 대응 여부를 판단하고, "
    "그 결과에 따라 특허 침해 리스크를 평가하는 모델이다. "
    "최종 응답은 반드시 JSON 형식으로 출력한다."
)

def build_prompt(user_query: str, regit_num: str, claim_text: str) -> str:
    return (
        f"<system>\n{SYSTEM}\n</system>\n"
        f"<user>\n"
        f"[사용자 제품 설명]\n{user_query}\n\n"
        f"[특허 정보]\n특허번호: {regit_num}\n청구항:\n{claim_text}\n\n"
        f"구성요소별 대응 여부를 판단하고, 침해 리스크를 평가하라.\n"
        f"</user>\n"
        f"<assistant>\n"
    )

def main():
    token = os.environ.get("HF_TOKEN")

    print("Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(ADAPTER_PATH)

    print("Loading base model...")
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        token=token,
        torch_dtype=torch.bfloat16,
        device_map="auto",
    )

    print("Loading LoRA adapter...")
    model = PeftModel.from_pretrained(model, ADAPTER_PATH)
    model.eval()

    # 테스트 케이스
    test_cases = [
        {
            "user_query": "tributyl acetylcitrate를 함유하는 크림을 만들었어",
            "expected": "높음"
        },
        {
            "user_query": "비타민C 세럼을 개발 중이야",
            "expected": "낮음"
        },
        {
            "user_query": "새로운 화장품을 기획하고 있어",
            "expected": "애매"
        },
    ]

    regit_num = "102918091"
    claim_text = "아세틸트리부틸스트레이트(tributyl acetylcitrate) 또는 이의 화장품학적으로 허용되는 염을 유효성분으로 함유하는 것을 특징으로 하는 미백용 화장료 조성물."

    print("\n" + "="*60)
    print("추론 테스트 시작")
    print("="*60)

    for i, case in enumerate(test_cases, 1):
        prompt = build_prompt(case["user_query"], regit_num, claim_text)

        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=512,
                do_sample=False,
                pad_token_id=tokenizer.pad_token_id,
            )

        response = tokenizer.decode(outputs[0], skip_special_tokens=True)
        # assistant 태그 이후 부분만 추출
        if "<assistant>" in response:
            response = response.split("<assistant>")[-1].strip()
        if "</assistant>" in response:
            response = response.split("</assistant>")[0].strip()

        print(f"\n[테스트 {i}]")
        print(f"입력: {case['user_query']}")
        print(f"예상: {case['expected']}")
        print(f"출력: {response[:500]}")

        # JSON 파싱 시도
        try:
            result = json.loads(response)
            print(f"✓ 파싱 성공 | risk_level: {result.get('risk_level', 'N/A')}")
        except:
            print("✗ JSON 파싱 실패")

    print("\n" + "="*60)
    print("테스트 완료")
    print("="*60)

if __name__ == "__main__":
    main()
