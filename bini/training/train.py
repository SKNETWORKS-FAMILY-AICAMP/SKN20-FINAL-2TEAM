print("RUNNING FILE:", __file__)

import os
import yaml
import torch
from datasets import load_dataset
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
)
from peft import LoraConfig, get_peft_model
from trl import SFTTrainer
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

    # HF gated 모델일 수 있음 → 사전에 토큰 로그인 필요
    # export HF_TOKEN=...
    token = os.environ.get("HF_TOKEN", None)

    tokenizer = AutoTokenizer.from_pretrained(base_model, token=token)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # 디바이스별 precision 설정
    if device == "cuda":
        bf16_ok = torch.cuda.is_bf16_supported()
        use_bf16 = bool(cfg.get("bf16", False)) and bf16_ok
        use_fp16 = bool(cfg.get("fp16", False)) or (not use_bf16)
        torch_dtype = torch.bfloat16 if use_bf16 else torch.float16
        device_map = "auto"
        optim = cfg["optim"]  # paged_adamw_8bit
    elif device == "mps":
        # MPS: bf16/fp16 미지원, bitsandbytes 미지원
        use_bf16 = False
        use_fp16 = False
        torch_dtype = torch.float32
        device_map = None  # MPS는 device_map="auto" 미지원
        optim = "adamw_torch"
    else:
        use_bf16 = False
        use_fp16 = False
        torch_dtype = torch.float32
        device_map = None
        optim = "adamw_torch"

    print(f"Loading model with dtype: {torch_dtype}")

    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        token=token,
        torch_dtype=torch_dtype,
        device_map=device_map,
    )

    # MPS/CPU인 경우 수동으로 디바이스 이동
    if device_map is None:
        model = model.to(device)

    lora = LoraConfig(
        r=cfg["r"],
        lora_alpha=cfg["lora_alpha"],
        lora_dropout=cfg["lora_dropout"],
        bias=cfg["bias"],
        task_type="CAUSAL_LM",
        target_modules=cfg["target_modules"],  # "all-linear" = 모델 구조 의존성 낮음
    )
    model = get_peft_model(model, lora)

    # 토크나이저 설정
    tokenizer.padding_side = "right"

    # SFTConfig로 TrainingArguments 대체 (TRL 0.27+)
    from trl import SFTConfig
    sft_config = SFTConfig(
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
        max_length=cfg.get("max_seq_length", 2048),
        dataset_text_field="text",
    )

    trainer = SFTTrainer(
        model=model,
        train_dataset=ds["train"],
        processing_class=tokenizer,
        args=sft_config,
    )
    


    trainer.train()
    trainer.save_model(out_dir)
    tokenizer.save_pretrained(out_dir)
    print(f"Saved LoRA adapter to: {out_dir}")

if __name__ == "__main__":
    main()
