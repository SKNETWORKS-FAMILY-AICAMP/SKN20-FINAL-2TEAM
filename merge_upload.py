from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer
from huggingface_hub import HfApi
import torch
import os

# /workspace에 여유 공간이 충분함 (276TB)
os.environ["HF_HOME"] = "/workspace/hf_cache"

BASE_MODEL = "Qwen/Qwen2.5-14B-Instruct"
LORA_MODEL = "itsbini/qwen2.5-14b-fto"
OUTPUT_DIR = "/workspace/qwen2.5-14b-fto-merged"
HF_TOKEN = os.environ.get("HF_TOKEN", "")  # export HF_TOKEN=hf_xxx 로 설정
UPLOAD_REPO = "itsbini/qwen2.5-14b-fto-merged"

print("1/4 베이스 모델 로딩 중... (10~15분 소요)")
tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    torch_dtype=torch.float16,
    device_map="auto",
    trust_remote_code=True
)

print("2/4 LoRA 어댑터 병합 중...")
model = PeftModel.from_pretrained(model, LORA_MODEL)
model = model.merge_and_unload()

print("3/4 로컬 저장 중...")
model.save_pretrained(OUTPUT_DIR)
tokenizer.save_pretrained(OUTPUT_DIR)

print("4/4 HuggingFace 업로드 중... (20~30분 소요)")
api = HfApi(token=HF_TOKEN)
api.create_repo(UPLOAD_REPO, exist_ok=True)
api.upload_folder(
    folder_path=OUTPUT_DIR,
    repo_id=UPLOAD_REPO,
    repo_type="model"
)
print("완료! 업로드된 레포:", UPLOAD_REPO)
