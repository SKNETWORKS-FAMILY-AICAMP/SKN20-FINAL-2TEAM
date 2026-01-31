import os
import json
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from peft import PeftModel
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
ADAPTER_PATH = BASE_DIR / "outputs/gemma3-4b-it-lora"
SEED_PATH = BASE_DIR / "data/raw/seeds/seed_cases.json"
LABEL_PATH = BASE_DIR / "data/processed/train.jsonl"

# 각 특허에서 10개씩 샘플링 (총 30개)
TARGET_PATENTS = ["1014541990000", "1019930200000", "1021522890000"]
SAMPLES_PER_PATENT = 10

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

def load_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows

def evaluate_model(model, tokenizer, seeds, labels, model_name):
    """모델 평가 함수"""
    results = {
        "json_valid": 0,
        "risk_correct": 0,
        "total": len(seeds)
    }

    predictions = []

    for i, (seed, label) in enumerate(zip(seeds, labels)):
        prompt = build_prompt(seed["user_query"], seed["regit_num"], seed["claim_text"])
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=512,
                do_sample=False,
                pad_token_id=tokenizer.pad_token_id,
            )

        response = tokenizer.decode(outputs[0], skip_special_tokens=True)
        if "<assistant>" in response:
            response = response.split("<assistant>")[-1].strip()
        if "</assistant>" in response:
            response = response.split("</assistant>")[0].strip()

        pred_risk = None
        json_valid = False

        try:
            pred = json.loads(response)
            json_valid = True
            results["json_valid"] += 1
            pred_risk = pred.get("risk_level", "")

            if pred_risk == label.get("risk_level", ""):
                results["risk_correct"] += 1
        except:
            # JSON 파싱 실패 시 텍스트에서 risk_level 추출 시도
            for level in ["높음", "애매", "낮음"]:
                if level in response:
                    pred_risk = level
                    break

        predictions.append({
            "idx": i + 1,
            "query": seed["user_query"][:30],
            "true": label.get("risk_level", ""),
            "pred": pred_risk,
            "json_valid": json_valid
        })

        status = "✓" if pred_risk == label.get("risk_level", "") else "✗"
        print(f"  [{i+1:2d}/{len(seeds)}] {status} {pred_risk or 'N/A':4s} (정답: {label.get('risk_level', ''):4s})")

    return results, predictions

def main():
    token = os.environ.get("HF_TOKEN")

    # 데이터 로드 (각 특허에서 10개씩 샘플링)
    with open(SEED_PATH, "r", encoding="utf-8") as f:
        all_seeds = json.load(f)
    all_labels = load_jsonl(LABEL_PATH)

    seeds = []
    labels = []
    for patent in TARGET_PATENTS:
        count = 0
        for s, l in zip(all_seeds, all_labels):
            if s["regit_num"] == patent and count < SAMPLES_PER_PATENT:
                seeds.append(s)
                labels.append(l)
                count += 1

    print("=" * 70)
    print("모델 비교: Fine-tuned 4B vs Base 12B")
    print("=" * 70)
    print(f"테스트 데이터: {len(seeds)}개\n")

    # ===== 1. Fine-tuned 4B 모델 =====
    print("-" * 70)
    print("[1] Fine-tuned Gemma 4B (LoRA)")
    print("-" * 70)

    tokenizer_4b = AutoTokenizer.from_pretrained(ADAPTER_PATH)
    model_4b = AutoModelForCausalLM.from_pretrained(
        "google/gemma-3-4b-it",
        token=token,
        torch_dtype=torch.bfloat16,
        device_map="auto",
    )
    model_4b = PeftModel.from_pretrained(model_4b, ADAPTER_PATH)
    model_4b.eval()

    results_4b, preds_4b = evaluate_model(model_4b, tokenizer_4b, seeds, labels, "4B-finetuned")

    # 메모리 해제
    del model_4b, tokenizer_4b
    torch.cuda.empty_cache()

    # ===== 2. Base 12B 모델 =====
    print("\n" + "-" * 70)
    print("[2] Base Gemma 12B (학습 안함, 4-bit 양자화)")
    print("-" * 70)

    tokenizer_12b = AutoTokenizer.from_pretrained("google/gemma-3-12b-it", token=token)
    if tokenizer_12b.pad_token is None:
        tokenizer_12b.pad_token = tokenizer_12b.eos_token

    # 4-bit 양자화로 메모리 절약
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    model_12b = AutoModelForCausalLM.from_pretrained(
        "google/gemma-3-12b-it",
        token=token,
        quantization_config=bnb_config,
        device_map="auto",
    )
    model_12b.eval()

    results_12b, preds_12b = evaluate_model(model_12b, tokenizer_12b, seeds, labels, "12B-base")

    # ===== 결과 비교 =====
    print("\n" + "=" * 70)
    print("비교 결과")
    print("=" * 70)

    total = len(seeds)

    print(f"\n{'메트릭':<20} | {'4B Fine-tuned':^15} | {'12B Base':^15}")
    print("-" * 55)
    print(f"{'JSON 유효성':<20} | {results_4b['json_valid']:>6}/{total} ({results_4b['json_valid']/total*100:>5.1f}%) | {results_12b['json_valid']:>6}/{total} ({results_12b['json_valid']/total*100:>5.1f}%)")
    print(f"{'risk_level 정확도':<20} | {results_4b['risk_correct']:>6}/{total} ({results_4b['risk_correct']/total*100:>5.1f}%) | {results_12b['risk_correct']:>6}/{total} ({results_12b['risk_correct']/total*100:>5.1f}%)")

    # 케이스별 비교
    print(f"\n[케이스별 비교]")
    print(f"{'#':<3} | {'Query':<25} | {'정답':<4} | {'4B-FT':<4} | {'12B':<4}")
    print("-" * 55)

    diff_count = 0
    for p4, p12 in zip(preds_4b, preds_12b):
        mark_4b = "✓" if p4["pred"] == p4["true"] else "✗"
        mark_12b = "✓" if p12["pred"] == p12["true"] else "✗"

        # 결과가 다른 경우 하이라이트
        if (p4["pred"] == p4["true"]) != (p12["pred"] == p12["true"]):
            diff_count += 1
            print(f"{p4['idx']:<3} | {p4['query']:<25} | {p4['true']:<4} | {mark_4b}{p4['pred'] or 'N/A':<3} | {mark_12b}{p12['pred'] or 'N/A':<3} ★")
        else:
            print(f"{p4['idx']:<3} | {p4['query']:<25} | {p4['true']:<4} | {mark_4b}{p4['pred'] or 'N/A':<3} | {mark_12b}{p12['pred'] or 'N/A':<3}")

    print(f"\n★ 결과가 다른 케이스: {diff_count}개")

    # 승자 판정
    print("\n" + "=" * 70)
    if results_4b['risk_correct'] > results_12b['risk_correct']:
        diff = results_4b['risk_correct'] - results_12b['risk_correct']
        print(f"결론: Fine-tuned 4B 모델이 {diff}개 더 정확 ({results_4b['risk_correct']/total*100:.1f}% vs {results_12b['risk_correct']/total*100:.1f}%)")
        print("→ 작은 모델도 Fine-tuning하면 큰 Base 모델보다 특정 태스크에서 우수!")
    elif results_4b['risk_correct'] < results_12b['risk_correct']:
        diff = results_12b['risk_correct'] - results_4b['risk_correct']
        print(f"결론: Base 12B 모델이 {diff}개 더 정확 ({results_12b['risk_correct']/total*100:.1f}% vs {results_4b['risk_correct']/total*100:.1f}%)")
    else:
        print(f"결론: 두 모델 동일한 정확도 ({results_4b['risk_correct']/total*100:.1f}%)")
    print("=" * 70)

    # 결과 저장
    result_path = BASE_DIR / "outputs/compare_4b_vs_12b.json"
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump({
            "samples": total,
            "4b_finetuned": results_4b,
            "12b_base": results_12b,
            "predictions_4b": preds_4b,
            "predictions_12b": preds_12b,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n결과 저장: {result_path}")

if __name__ == "__main__":
    main()
