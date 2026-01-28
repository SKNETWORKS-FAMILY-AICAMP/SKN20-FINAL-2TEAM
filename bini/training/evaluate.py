import os
import json
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel
from pathlib import Path
from collections import defaultdict

BASE_DIR = Path(__file__).resolve().parents[1]
ADAPTER_PATH = BASE_DIR / "outputs/gemma3-1b-it-lora"
BASE_MODEL = "google/gemma-3-1b-it"
SEED_PATH = BASE_DIR / "data/raw/seeds/seed_cases.json"
LABEL_PATH = BASE_DIR / "data/processed/train.jsonl"

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

def main():
    token = os.environ.get("HF_TOKEN")

    print("=" * 60)
    print("모델 평가 스크립트")
    print("=" * 60)

    # 데이터 로드
    with open(SEED_PATH, "r", encoding="utf-8") as f:
        seeds = json.load(f)
    labels = load_jsonl(LABEL_PATH)

    print(f"데이터셋: {len(seeds)}개")

    # 모델 로드
    print("\n모델 로딩 중...")
    tokenizer = AutoTokenizer.from_pretrained(ADAPTER_PATH)
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        token=token,
        torch_dtype=torch.bfloat16,
        device_map="auto",
    )
    model = PeftModel.from_pretrained(model, ADAPTER_PATH)
    model.eval()
    print("모델 로딩 완료\n")

    # 평가 메트릭
    results = {
        "total": len(seeds),
        "json_valid": 0,
        "risk_level_correct": 0,
        "match_correct": 0,
        "match_total": 0,
    }

    risk_confusion = defaultdict(lambda: defaultdict(int))  # pred -> actual -> count
    match_confusion = defaultdict(lambda: defaultdict(int))

    errors = []

    print("평가 시작...")
    print("-" * 60)

    for i, (seed, label) in enumerate(zip(seeds, labels)):
        user_query = seed["user_query"]
        claim_text = seed["claim_text"]
        regit_num = seed["regit_num"]

        prompt = build_prompt(user_query, regit_num, claim_text)
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

        # JSON 파싱
        try:
            pred = json.loads(response)
            results["json_valid"] += 1

            # risk_level 평가
            pred_risk = pred.get("risk_level", "")
            true_risk = label.get("risk_level", "")

            if pred_risk == true_risk:
                results["risk_level_correct"] += 1
                status = "✓"
            else:
                status = "✗"
                errors.append({
                    "idx": i + 1,
                    "query": user_query[:30],
                    "pred": pred_risk,
                    "true": true_risk
                })

            risk_confusion[pred_risk][true_risk] += 1

            # match 평가 (comparisons)
            pred_comps = pred.get("comparisons", [])
            true_comps = label.get("comparisons", [])

            for pc, tc in zip(pred_comps, true_comps):
                results["match_total"] += 1
                pred_match = pc.get("match", "")
                true_match = tc.get("match", "")
                if pred_match == true_match:
                    results["match_correct"] += 1
                match_confusion[pred_match][true_match] += 1

            print(f"[{i+1:2d}/{len(seeds)}] {status} risk: {pred_risk:4s} (정답: {true_risk:4s}) | {user_query[:25]}...")

        except json.JSONDecodeError:
            print(f"[{i+1:2d}/{len(seeds)}] ✗ JSON 파싱 실패 | {user_query[:25]}...")
            errors.append({
                "idx": i + 1,
                "query": user_query[:30],
                "error": "JSON 파싱 실패"
            })

    # 결과 출력
    print("\n" + "=" * 60)
    print("평가 결과")
    print("=" * 60)

    json_acc = results["json_valid"] / results["total"] * 100
    risk_acc = results["risk_level_correct"] / results["total"] * 100
    match_acc = results["match_correct"] / results["match_total"] * 100 if results["match_total"] > 0 else 0

    print(f"\n[전체 성능]")
    print(f"  JSON 유효성:     {results['json_valid']:3d}/{results['total']} ({json_acc:.1f}%)")
    print(f"  risk_level 정확도: {results['risk_level_correct']:3d}/{results['total']} ({risk_acc:.1f}%)")
    print(f"  match 정확도:     {results['match_correct']:3d}/{results['match_total']} ({match_acc:.1f}%)")

    # risk_level 혼동 행렬
    print(f"\n[risk_level 혼동 행렬] (행: 예측, 열: 정답)")
    levels = ["높음", "애매", "낮음"]
    print(f"{'':8s} | {'높음':^6s} | {'애매':^6s} | {'낮음':^6s}")
    print("-" * 35)
    for pred_l in levels:
        row = [risk_confusion[pred_l][true_l] for true_l in levels]
        print(f"{pred_l:8s} | {row[0]:^6d} | {row[1]:^6d} | {row[2]:^6d}")

    # match 혼동 행렬
    print(f"\n[match 혼동 행렬] (행: 예측, 열: 정답)")
    matches = ["대응", "미대응", "판단불가"]
    print(f"{'':8s} | {'대응':^6s} | {'미대응':^6s} | {'판단불가':^6s}")
    print("-" * 42)
    for pred_m in matches:
        row = [match_confusion[pred_m][true_m] for true_m in matches]
        print(f"{pred_m:8s} | {row[0]:^6d} | {row[1]:^8d} | {row[2]:^8d}")

    # 오류 케이스
    if errors:
        print(f"\n[오류 케이스] ({len(errors)}개)")
        for e in errors[:10]:
            if "error" in e:
                print(f"  #{e['idx']}: {e['query']}... - {e['error']}")
            else:
                print(f"  #{e['idx']}: {e['query']}... - 예측: {e['pred']}, 정답: {e['true']}")

    print("\n" + "=" * 60)
    print("평가 완료")
    print("=" * 60)

    # 결과 저장
    result_path = BASE_DIR / "outputs/evaluation_result.json"
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump({
            "metrics": {
                "json_validity": json_acc,
                "risk_level_accuracy": risk_acc,
                "match_accuracy": match_acc,
            },
            "details": results,
            "errors": errors,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n결과 저장: {result_path}")

if __name__ == "__main__":
    main()
