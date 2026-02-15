"""Gemma3 1B vs Qwen2.5 1.5B 비교 학습 스크립트.

사용법:
    # 0. HuggingFace 로그인 (Gemma3 gated repo 접근용)
    huggingface-cli login --token <YOUR_HF_TOKEN>

    # 1. Gemma3 1B 학습
    cd /workspace/SKN20-FINAL-2TEAM
    python -m SLLM_model.training.train_compare --model gemma

    # 2. Qwen2.5 1.5B 학습
    python -m SLLM_model.training.train_compare --model qwen

    # 3. 둘 다 순차 학습
    python -m SLLM_model.training.train_compare --model both
"""

import argparse
import os
from pathlib import Path

import pandas as pd
import torch
from datasets import Dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    Trainer,
    TrainingArguments,
    default_data_collator,
)
from peft import LoraConfig, get_peft_model

# ─── 경로 ───────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parents[1]  # SLLM_model/
DATA_DIR = Path("/workspace/patent-data/GEMINI/sllm_1st_test/data")
TRAIN_FILE = DATA_DIR / "sllm_train_2869.xlsx"

# ─── 모델 설정 ──────────────────────────────────────────
MODELS = {
    "gemma": {
        "model_id": "google/gemma-3-1b-it",
        "output_dir": str(BASE_DIR / "outputs/gemma3-1b-v2"),
    },
    "qwen": {
        "model_id": "Qwen/Qwen2.5-1.5B-Instruct",
        "output_dir": str(BASE_DIR / "outputs/qwen2.5-1.5b-lora"),
    },
}

# ─── 시스템 프롬프트 (eval 스크립트와 동일) ───────────────
SYSTEM_PROMPT = """당신은 화장품 특허 침해(FTO) 분석 전문가입니다.

[문구 규칙]
- "판단"이라는 단어 사용 금지 → "분석"으로 대체
- "리스크" 사용 금지 → "가능성"으로 대체

[분석 규칙]
- 구성요소 완비의 원칙: 모든 구성요소를 포함해야 침해
- 균등론: 특허 구성 수치가 경미하게 이탈 시 전문가 검토 대상
- 금반언: 공개청구항에는 있었지만, 등록청구항에는 삭제된 구성은 침해 주장 불가
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


def build_user_prompt(row: pd.Series) -> str:
    """입력 프롬프트 구성 (eval/01_infer.py와 동일 로직)."""
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

    meta = []
    for col, name in [("apply_num", "출원번호"), ("regit_num", "등록번호"), ("pub_num", "공개번호")]:
        val = str(row.get(col, ""))
        if val and val != "nan":
            meta.append(f"{name}: {val}")
    if meta:
        parts.append(f"\n[특허 정보]\n" + "\n".join(meta))

    return "\n".join(parts)


def load_sft_data() -> list[dict]:
    """xlsx → chat 형식 SFT 데이터 변환."""
    df = pd.read_excel(TRAIN_FILE)
    print(f"학습 데이터: {len(df)}건")

    samples = []
    for _, row in df.iterrows():
        user_prompt = build_user_prompt(row)
        output = str(row.get("output_form", ""))
        if not output or output == "nan":
            continue
        samples.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": output},
            ]
        })

    print(f"유효 샘플: {len(samples)}건")
    return samples


def train_model(model_key: str, lora_cfg: dict):
    """단일 모델 학습."""
    model_info = MODELS[model_key]
    model_id = model_info["model_id"]
    output_dir = model_info["output_dir"]

    print(f"\n{'='*60}")
    print(f"모델 학습 시작: {model_id}")
    print(f"출력 경로: {output_dir}")
    print(f"{'='*60}\n")

    # 토크나이저
    token = os.environ.get("HF_TOKEN", None)
    tokenizer = AutoTokenizer.from_pretrained(model_id, token=token, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    # 데이터 준비 - chat template 적용
    sft_data = load_sft_data()
    texts = []
    for sample in sft_data:
        text = tokenizer.apply_chat_template(
            sample["messages"], tokenize=False, add_generation_prompt=False,
        )
        texts.append(text)

    dataset = Dataset.from_dict({"text": texts})

    # 양자화 설정
    bf16_ok = torch.cuda.is_bf16_supported()
    torch_dtype = torch.bfloat16 if bf16_ok else torch.float16

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch_dtype,
        bnb_4bit_use_double_quant=True,
    )

    # 모델 로드
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        token=token,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )
    model.gradient_checkpointing_enable()

    # LoRA 적용
    lora_config = LoraConfig(
        r=lora_cfg["r"],
        lora_alpha=lora_cfg["lora_alpha"],
        lora_dropout=lora_cfg["lora_dropout"],
        bias=lora_cfg["bias"],
        task_type="CAUSAL_LM",
        target_modules=lora_cfg["target_modules"],
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # 토크나이즈
    max_length = lora_cfg.get("max_seq_length", 4096)

    # assistant 응답 시작 위치를 모델별로 다르게 찾기
    if model_key == "gemma":
        response_marker = "<start_of_turn>model\n"
    else:
        response_marker = "<|im_start|>assistant\n"

    def tokenize_fn(examples):
        tokenized = tokenizer(
            examples["text"],
            truncation=True,
            max_length=max_length,
            padding="max_length",
            return_tensors=None,
        )

        if "token_type_ids" not in tokenized:
            tokenized["token_type_ids"] = [[0] * len(ids) for ids in tokenized["input_ids"]]

        labels_list = []
        for i, text in enumerate(examples["text"]):
            input_ids = tokenized["input_ids"][i]

            marker_pos = text.rfind(response_marker)
            if marker_pos != -1:
                prompt_text = text[:marker_pos + len(response_marker)]
                prompt_tokens = tokenizer(prompt_text, add_special_tokens=False)["input_ids"]
                prompt_len = len(prompt_tokens)
                if tokenizer.bos_token_id is not None and len(input_ids) > 0 and input_ids[0] == tokenizer.bos_token_id:
                    if len(prompt_tokens) == 0 or prompt_tokens[0] != tokenizer.bos_token_id:
                        prompt_len += 1

                labels = [-100] * prompt_len + input_ids[prompt_len:]
                labels = labels[:len(input_ids)]
                if len(labels) < len(input_ids):
                    labels += [-100] * (len(input_ids) - len(labels))
            else:
                labels = input_ids.copy()

            # padding → -100
            for j in range(len(labels)):
                if input_ids[j] == tokenizer.pad_token_id:
                    labels[j] = -100

            labels_list.append(labels)

        tokenized["labels"] = labels_list
        return tokenized

    tokenized_ds = dataset.map(tokenize_fn, batched=True, remove_columns=["text"])

    # 학습 설정
    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=lora_cfg["num_train_epochs"],
        per_device_train_batch_size=lora_cfg["per_device_train_batch_size"],
        gradient_accumulation_steps=lora_cfg["gradient_accumulation_steps"],
        learning_rate=lora_cfg["learning_rate"],
        warmup_ratio=lora_cfg["warmup_ratio"],
        weight_decay=lora_cfg["weight_decay"],
        logging_steps=lora_cfg["logging_steps"],
        save_steps=lora_cfg["save_steps"],
        save_total_limit=2,
        bf16=bf16_ok,
        fp16=not bf16_ok,
        optim=lora_cfg["optim"],
        report_to=[],
        push_to_hub=False,
        dataloader_pin_memory=True,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_ds,
        data_collator=default_data_collator,
    )

    trainer.train()
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)
    print(f"\n학습 완료! 저장 경로: {output_dir}")

    # 메모리 해제
    del model, trainer
    torch.cuda.empty_cache()

    return output_dir


def main():
    parser = argparse.ArgumentParser(description="Gemma3 1B vs Qwen2.5 1.5B 비교 학습")
    parser.add_argument("--model", choices=["gemma", "qwen", "both"], default="both",
                        help="학습할 모델 (gemma / qwen / both)")
    parser.add_argument("--epochs", type=int, default=3, help="학습 에폭 수")
    parser.add_argument("--batch_size", type=int, default=2, help="배치 사이즈")
    parser.add_argument("--lr", type=float, default=2e-5, help="학습률")
    args = parser.parse_args()

    # LoRA 설정
    lora_cfg = {
        "r": 16,
        "lora_alpha": 32,
        "lora_dropout": 0.05,
        "bias": "none",
        "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj", "up_proj", "down_proj", "gate_proj"],
        "max_seq_length": 4096,
        "num_train_epochs": args.epochs,
        "per_device_train_batch_size": args.batch_size,
        "gradient_accumulation_steps": 4,
        "learning_rate": args.lr,
        "warmup_ratio": 0.05,
        "weight_decay": 0.01,
        "logging_steps": 10,
        "save_steps": 100,
        "optim": "paged_adamw_8bit",
    }

    targets = ["gemma", "qwen"] if args.model == "both" else [args.model]

    results = {}
    for model_key in targets:
        output_dir = train_model(model_key, lora_cfg)
        results[model_key] = output_dir

    print(f"\n{'='*60}")
    print("학습 완료 요약")
    print(f"{'='*60}")
    for k, v in results.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
