"""Step 1: 모델 추론.

파인튜닝 완료된 모델로 테스트 데이터에 대해 추론을 실행한다.
모델별로 한 번씩 실행.

사용법:
    python 01_infer.py --model_path ./gemma-fto --model_name gemma
    python 01_infer.py --model_path ./qwen-fto --model_name qwen

출력:
    output/infer_gemma.xlsx  (원본 + pred_output 컬럼 추가)
    output/infer_qwen.xlsx
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import torch
from loguru import logger
from transformers import AutoModelForCausalLM, AutoTokenizer

# ─── 로깅 설정 ────────────────────────────────────────────
LOG_DIR = Path(__file__).resolve().parents[2] / "logs"  # SLLM_model/logs/
LOG_DIR.mkdir(exist_ok=True)
logger.remove()
logger.add(sys.stderr, level="INFO")
logger.add(
    LOG_DIR / "eval_infer_{time:YYYY-MM-DD_HH-mm-ss}.log",
    level="DEBUG",
    rotation="100 MB",
    encoding="utf-8",
)


SYSTEM_PROMPT = """당신은 화장품 특허 침해(FTO) 분석 전문가입니다.

[문구 규칙]
- "판단"이라는 단어 사용 금지 → "분석"으로 대체
- "리스크" 사용 금지 → "가능성"으로 대체

[분석 규칙]
- 구성요소 완비의 원칙: 모든 구성요소를 포함해야 침해
- 균등론: 수치 경미 이탈 시 전문가 검토 대상
- 금반언: 등록청구항에서 삭제된 구성은 침해 주장 불가
- 내재성: 성분 동일 + 용도/효과 미언급 시 "미대응(내재성)"

[대응 여부]
- 대응: 동일/포함
- 미대응: 해당 구성 없음
- 미대응(균등): 수치 경미 이탈
- 미대응(내재성): 용도/효과 미언급
- 확인불가: 정보 부족

[출력 형식]
◆구성 대비◆ → 테이블
◆판단◆ → 분석 설명 (결론성 문구 금지)
◆결론◆ → 아래 4개 중 하나만:
- "침해 가능성이 높은 것으로 분석됩니다."
- "침해 가능성이 낮은 것으로 분석됩니다."
- "전문가의 추가 검토가 권고됩니다."
- "침해 여부 분석을 위해 보다 구체적인 실시 정보가 필요합니다."
"""


def build_prompt(row: pd.Series) -> str:
    """입력 프롬프트 구성: user_query → claim_reg → claim_pub → components → 메타정보"""
    parts = []
    for col, header in [
        ("user_query", None),
        ("claim_reg", "[등록 청구항]"),
        ("claim_pub", "[공개 청구항]"),
        ("components", "[구성요소]"),
    ]:
        val = str(row.get(col, ""))
        if val and val != "nan":
            parts.append(f"\n{header}\n{val}" if header else val)

    # 메타정보 (output_form에 regit_num 등이 포함되므로 필수)
    meta = []
    for col, name in [("apply_num", "출원번호"), ("regit_num", "등록번호"), ("pub_num", "공개번호")]:
        val = str(row.get(col, ""))
        if val and val != "nan":
            meta.append(f"{name}: {val}")
    if meta:
        parts.append(f"\n[특허 정보]\n" + "\n".join(meta))

    return "\n".join(parts)


def load_model(model_path: str):
    """모델 + 토크나이저 로드. LoRA adapter 자동 감지."""
    path = Path(model_path)
    adapter_config = path / "adapter_config.json"

    if adapter_config.exists():
        # LoRA adapter
        from peft import PeftModel

        with open(adapter_config) as f:
            cfg = json.load(f)
        base = cfg["base_model_name_or_path"]
        logger.info(f"Base: {base}")
        logger.info(f"Adapter: {model_path}")

        tokenizer = AutoTokenizer.from_pretrained(base, trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(
            base, torch_dtype=torch.float16, device_map="auto", trust_remote_code=True,
        )
        model = PeftModel.from_pretrained(model, model_path)
    else:
        # merged 모델
        logger.info(f"Model: {model_path}")
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(
            model_path, torch_dtype=torch.float16, device_map="auto", trust_remote_code=True,
        )

    model.eval()
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    return model, tokenizer


def main():
    parser = argparse.ArgumentParser(description="Step 1: 모델 추론")
    parser.add_argument("--model_path", required=True, help="파인튜닝 모델 경로")
    parser.add_argument("--model_name", required=True, help="모델 이름 (gemma / qwen)")
    parser.add_argument("--test_data", default="../data/sllm_test_718.xlsx")
    parser.add_argument("--output_dir", default="./output")
    parser.add_argument("--max_tokens", type=int, default=2048)
    args = parser.parse_args()

    logger.info(f"=== 모델 추론: {args.model_name} ===")

    model, tokenizer = load_model(args.model_path)
    df = pd.read_excel(args.test_data)
    logger.info(f"테스트: {len(df)}건")

    preds = []
    for i, row in df.iterrows():
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_prompt(row)},
        ]
        input_text = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True,
        )
        inputs = tokenizer(input_text, return_tensors="pt").to(model.device)

        with torch.no_grad():
            out = model.generate(
                **inputs,
                max_new_tokens=args.max_tokens,
                do_sample=False,
                pad_token_id=tokenizer.pad_token_id,
            )

        gen = out[0][inputs["input_ids"].shape[1]:]
        preds.append(tokenizer.decode(gen, skip_special_tokens=True))

        if (i + 1) % 50 == 0 or (i + 1) == len(df):
            logger.info(f"[{i+1}/{len(df)}]")

    # 저장
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    df["pred_output"] = preds
    out_path = out_dir / f"infer_{args.model_name}.xlsx"
    df.to_excel(out_path, index=False)
    logger.success(f"추론 완료! 저장: {out_path}")


if __name__ == "__main__":
    main()
