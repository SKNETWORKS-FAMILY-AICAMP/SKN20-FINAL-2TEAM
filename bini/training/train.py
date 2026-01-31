print("RUNNING FILE:", __file__)

import os
import yaml
import torch
from dotenv import load_dotenv
from datasets import load_dataset

# .env 파일에서 환경변수 로드
load_dotenv()
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    BitsAndBytesConfig,
    Trainer,
    TrainingArguments,
    default_data_collator,
)
from peft import LoraConfig, get_peft_model
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]  # bini/

DATA_PATH = BASE_DIR / "data/processed/sft_train.jsonl"

ds = load_dataset("json", data_files={"train": str(DATA_PATH)})
cfg = yaml.safe_load(open(BASE_DIR / "training/lora_config.yaml", "r", encoding="utf-8"))

def get_device():
    """디바이스 자동 감지: CUDA > MPS > CPU"""
    if torch.cuda.is_available():
        return "cuda"
    elif torch.backends.mps.is_available():
        return "mps"
    return "cpu"

def main():
    device = get_device()
    print(f"Using device: {device}")

    base_model = cfg["base_model"]
    out_dir = cfg["output_dir"]

    token = os.environ.get("HF_TOKEN", None)

    tokenizer = AutoTokenizer.from_pretrained(base_model, token=token)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Gemma 3 모델은 token_type_ids 필요
    tokenizer.return_token_type_ids = True

    # 디바이스별 precision 설정
    if device == "cuda":
        bf16_ok = torch.cuda.is_bf16_supported()
        use_bf16 = bool(cfg.get("bf16", False)) and bf16_ok
        use_fp16 = bool(cfg.get("fp16", False)) or (not use_bf16)
        torch_dtype = torch.bfloat16 if use_bf16 else torch.float16
        device_map = "auto"
        optim = cfg["optim"]
    elif device == "mps":
        use_bf16 = False
        use_fp16 = False
        torch_dtype = torch.float32
        device_map = None
        optim = "adamw_torch"
    else:
        use_bf16 = False
        use_fp16 = False
        torch_dtype = torch.float32
        device_map = None
        optim = "adamw_torch"

    print(f"Loading model with dtype: {torch_dtype}")

    # 4-bit 양자화로 메모리 절약 (QLoRA)
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch_dtype,
        bnb_4bit_use_double_quant=True,
    )

    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        token=token,
        quantization_config=bnb_config,
        device_map=device_map,
    )

    if device_map is None:
        model = model.to(device)

    model.gradient_checkpointing_enable()

    lora = LoraConfig(
        r=cfg["r"],
        lora_alpha=cfg["lora_alpha"],
        lora_dropout=cfg["lora_dropout"],
        bias=cfg["bias"],
        task_type="CAUSAL_LM",
        target_modules=cfg["target_modules"],
    )
    model = get_peft_model(model, lora)

    tokenizer.padding_side = "right"
    max_length = cfg.get("max_seq_length", 2048)

    # 응답 시작 토큰 찾기 (labels 마스킹용)
    assistant_token = "<assistant>"

    def tokenize_function(examples):
        tokenized = tokenizer(
            examples["text"],
            truncation=True,
            max_length=max_length,
            padding="max_length",
            return_tensors=None,
        )

        # token_type_ids가 없으면 0으로 채움
        if "token_type_ids" not in tokenized:
            tokenized["token_type_ids"] = [[0] * len(ids) for ids in tokenized["input_ids"]]

        # labels 생성: 프롬프트 부분은 -100으로 마스킹 (응답 부분만 학습)
        labels_list = []
        for i, text in enumerate(examples["text"]):
            input_ids = tokenized["input_ids"][i]

            # <assistant> 위치 찾기
            assistant_start = text.find(assistant_token)
            if assistant_start != -1:
                # <assistant> 이전까지의 텍스트
                prompt_text = text[:assistant_start + len(assistant_token)]
                prompt_tokens = tokenizer(prompt_text, add_special_tokens=False)["input_ids"]
                prompt_len = len(prompt_tokens) + 1  # +1 for BOS token

                # 프롬프트 부분은 -100, 나머지는 input_ids
                labels = [-100] * prompt_len + input_ids[prompt_len:]
                # 길이 맞추기
                labels = labels[:len(input_ids)]
                if len(labels) < len(input_ids):
                    labels = labels + [-100] * (len(input_ids) - len(labels))
            else:
                # assistant 토큰이 없으면 전체 학습
                labels = input_ids.copy()

            labels_list.append(labels)

        tokenized["labels"] = labels_list
        return tokenized

    # 데이터셋 전처리
    tokenized_ds = ds["train"].map(
        tokenize_function,
        batched=True,
        remove_columns=ds["train"].column_names,
    )

    training_args = TrainingArguments(
        output_dir=out_dir,
        num_train_epochs=cfg["num_train_epochs"],
        per_device_train_batch_size=cfg["per_device_train_batch_size"],
        gradient_accumulation_steps=cfg["gradient_accumulation_steps"],
        learning_rate=cfg["learning_rate"],
        warmup_ratio=cfg["warmup_ratio"],
        weight_decay=cfg["weight_decay"],
        logging_steps=cfg["logging_steps"],
        save_steps=cfg["save_steps"],
        bf16=use_bf16,
        fp16=use_fp16,
        optim=optim,
        report_to=[],
        push_to_hub=False,
        dataloader_pin_memory=False if device == "mps" else True,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_ds,
        data_collator=default_data_collator,  # labels를 덮어쓰지 않음
    )

    trainer.train()
    trainer.save_model(out_dir)
    tokenizer.save_pretrained(out_dir)
    print(f"Saved LoRA adapter to: {out_dir}")

if __name__ == "__main__":
    main()
