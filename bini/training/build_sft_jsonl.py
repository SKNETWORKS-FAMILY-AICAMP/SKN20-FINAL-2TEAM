import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]  

SEED_PATH = BASE_DIR / "data/raw/seeds/seed_cases.json"
LABEL_PATH = BASE_DIR / "data/processed/train.jsonl"
OUT_PATH = BASE_DIR / "data/processed/sft_train.jsonl"

SYSTEM = (
    "너는 특허 청구항과 사용자 제품 구성을 비교하여 구성요소별 대응 여부를 판단하고, "
    "그 결과에 따라 특허 침해 리스크를 평가하는 모델이다. "
    "최종 응답은 반드시 JSON 형식으로 출력한다."
)

def load_jsonl(path: str):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception as e:
                raise ValueError(f"Invalid JSONL at line {line_no}: {e}\n{line[:200]}")
    return rows

def main():
    with open(SEED_PATH, "r", encoding="utf-8") as f:
        seeds = json.load(f)

    labels = load_jsonl(LABEL_PATH)

    if len(seeds) != len(labels):
        raise ValueError(f"seed({len(seeds)}) and labels({len(labels)}) count mismatch")

    with open(OUT_PATH, "w", encoding="utf-8") as out:
        for i, (seed, y) in enumerate(zip(seeds, labels), 1):
            user_query = seed["user_query"].strip()
            claim_text = seed["claim_text"].strip()
            regit_num = seed["regit_num"]

            prompt = (
                f"<system>\n{SYSTEM}\n</system>\n"
                f"<user>\n"
                f"[사용자 제품 설명]\n{user_query}\n\n"
                f"[특허 정보]\n특허번호: {regit_num}\n청구항:\n{claim_text}\n\n"
                f"구성요소별 대응 여부를 판단하고, 침해 리스크를 평가하라.\n"
                f"</user>\n"
                f"<assistant>\n"
            )

            completion = json.dumps(y, ensure_ascii=False)
            text = prompt + completion + "\n</assistant>\n"

            out.write(json.dumps({"text": text}, ensure_ascii=False) + "\n")

    print(f"Wrote: {OUT_PATH} ({len(seeds)} rows)")

if __name__ == "__main__":
    main()
