import os
from huggingface_hub import HfApi, create_repo

token = os.environ.get("HF_TOKEN")
repo_id = "itsbini/qwen2.5-3b-fto"

api = HfApi()
create_repo(repo_id=repo_id, repo_type="model", exist_ok=True, token=token)
print(f"repo 생성(또는 확인) 완료: {repo_id}")

api.upload_folder(
    folder_path="/root/SKN20-FINAL-2TEAM/SLLM_model/outputs/qwen2.5-3b-lora",
    repo_id=repo_id,
    repo_type="model",
    token=token,
)
print("업로드 완료")
