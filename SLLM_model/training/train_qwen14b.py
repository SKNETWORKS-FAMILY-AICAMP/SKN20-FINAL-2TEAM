"""Qwen2.5 14B 파인튜닝 스크립트 (sllm_qwen_data 기반).

사용법:
    cd /workspace/SKN20-FINAL-2TEAM
    python -m SLLM_model.training.train_qwen14b

옵션:
    --epochs      학습 에폭 수 (기본: 2)
    --batch_size  배치 사이즈 (기본: 1)
    --lr          학습률 (기본: 3e-5)
"""

import argparse
import os
import sys
from pathlib import Path

import pandas as pd
import torch
from loguru import logger
from datasets import Dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    Trainer,
    TrainerCallback,
    TrainingArguments,
    default_data_collator,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

# ─── 로깅 설정 ────────────────────────────────────────────
LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
LOG_DIR.mkdir(exist_ok=True)
logger.remove()
logger.add(sys.stderr, level="INFO")
logger.add(
    LOG_DIR / "train_qwen14b_{time:YYYY-MM-DD_HH-mm-ss}.log",
    level="DEBUG",
    rotation="100 MB",
    encoding="utf-8",
)

# ─── 경로 ───────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parents[1]  # SLLM_model/
DATA_DIR = BASE_DIR / "data" / "sllm_qwen_data"
TRAIN_FILE = DATA_DIR / "sllm_train.xlsx"
TEST_FILE  = DATA_DIR / "sllm_test.xlsx"

# ─── 모델 설정 ──────────────────────────────────────────
MODEL_ID = "Qwen/Qwen2.5-14B-Instruct"
OUTPUT_DIR = str(BASE_DIR / "outputs" / "qwen2.5-14b-lora")

# ─── 시스템 프롬프트 ────────────────────────────────────
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


class LoguruCallback(TrainerCallback):
    """Trainer의 학습 metrics를 loguru 로그 파일에 저장하는 콜백."""

    def on_log(self, args, state, control, logs=None, **kwargs):
        if logs is None:
            return
        step = state.global_step
        msg_parts = [f"step={step}"]
        for key in ["loss", "grad_norm", "learning_rate", "epoch"]:
            if key in logs:
                msg_parts.append(
                    f"{key}={logs[key]:.6f}" if isinstance(logs[key], float) else f"{key}={logs[key]}"
                )
        logger.info(" | ".join(msg_parts))


def build_user_prompt(row: pd.Series) -> str:
    """입력 프롬프트 구성."""
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
        parts.append("\n[특허 정보]\n" + "\n".join(meta))

    return "\n".join(parts)


def load_sft_data(file: Path) -> list[dict]:
    """xlsx → chat 형식 SFT 데이터 변환."""
    df = pd.read_excel(file)
    logger.info(f"데이터 로드: {len(df)}건 ({file})")

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

    logger.info(f"유효 샘플: {len(samples)}건")
    return samples


def main():
    parser = argparse.ArgumentParser(description="Qwen2.5 14B 파인튜닝 (sllm_qwen_data)")
    parser.add_argument("--epochs", type=int, default=2, help="학습 에폭 수")
    parser.add_argument("--batch_size", type=int, default=2, help="배치 사이즈")
    parser.add_argument("--lr", type=float, default=3e-5, help="학습률")
    args = parser.parse_args()

    logger.info(f"{'='*60}")
    logger.info(f"모델: {MODEL_ID}")
    logger.info(f"출력 경로: {OUTPUT_DIR}")
    logger.info(f"epochs={args.epochs}, batch_size={args.batch_size}, lr={args.lr}")
    logger.info(f"{'='*60}")

    token = os.environ.get("HF_TOKEN", None)

    # 토크나이저
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, token=token, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    # 데이터 준비
    sft_data = load_sft_data(TRAIN_FILE)
    texts = [
        tokenizer.apply_chat_template(s["messages"], tokenize=False, add_generation_prompt=False)
        for s in sft_data
    ]
    dataset = Dataset.from_dict({"text": texts})

    eval_data = load_sft_data(TEST_FILE)
    eval_texts = [
        tokenizer.apply_chat_template(s["messages"], tokenize=False, add_generation_prompt=False)
        for s in eval_data
    ]
    eval_dataset = Dataset.from_dict({"text": eval_texts})

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
        MODEL_ID,
        token=token,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)

    # LoRA 적용
    lora_config = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.1,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "up_proj", "down_proj", "gate_proj"],
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # 토크나이즈 (assistant 응답 부분만 loss 계산)
    max_length = 4096
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

            for j in range(len(labels)):
                if input_ids[j] == tokenizer.pad_token_id:
                    labels[j] = -100

            labels_list.append(labels)

        tokenized["labels"] = labels_list
        return tokenized

    tokenized_ds = dataset.map(tokenize_fn, batched=True, remove_columns=["text"])
    tokenized_eval_ds = eval_dataset.map(tokenize_fn, batched=True, remove_columns=["text"])

    # 학습 설정
    training_args = TrainingArguments(
        output_dir=OUTPUT_DIR,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=1,
        eval_accumulation_steps=8,
        learning_rate=args.lr,
        warmup_ratio=0.05,
        weight_decay=0.01,
        logging_steps=5,
        save_steps=5000,
        save_total_limit=2,
        eval_strategy="steps",
        eval_steps=5000,
        bf16=bf16_ok,
        fp16=not bf16_ok,
        optim="paged_adamw_8bit",
        report_to=[],
        push_to_hub=False,
        dataloader_pin_memory=True,
        gradient_checkpointing=True,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_ds,
        eval_dataset=tokenized_eval_ds,
        data_collator=default_data_collator,
        callbacks=[LoguruCallback()],
    )

    logger.info("학습 시작...")
    trainer.train()
    trainer.save_model(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    logger.success(f"학습 완료! 저장 경로: {OUTPUT_DIR}")

    del model, trainer
    torch.cuda.empty_cache()
    logger.info("GPU 메모리 해제 완료")


if __name__ == "__main__":
    main()
