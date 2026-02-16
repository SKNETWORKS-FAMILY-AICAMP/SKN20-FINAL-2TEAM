# HuggingFace 모델 사용 가이드

## 모델 저장소

| 모델 | 저장소 | 베이스 모델 |
|------|--------|-------------|
| Gemma3 1B | `77eileen/gemma3-1b-patent-fto` | google/gemma-3-1b-it |
| Qwen2.5 1.5B | `77eileen/qwen2.5-1.5b-patent-fto` | Qwen/Qwen2.5-1.5B-Instruct |

- 어댑터: LoRA (QLoRA 4-bit NF4로 학습)
- 접근 권한: Private

---

## 1. 사전 준비

### HuggingFace 토큰 발급
1. https://huggingface.co/settings/tokens 접속
2. "New token" 클릭
3. **Write** 권한으로 토큰 생성 (업로드 시 필요)
4. 토큰 복사 후 `.env` 파일에 저장:
   ```
   HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxx
   ```

### 저장소 접근 권한
- Private 저장소이므로 팀원은 77eileen에게 **Collaborator** 권한 요청 필요
- HuggingFace 저장소 Settings > Collaborators에서 팀원 추가

---

## 2. 학습된 모델 불러오기 (4-bit 양자화)

```python
import os
import torch
from dotenv import load_dotenv
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from peft import PeftModel

load_dotenv()
token = os.environ.get("HF_TOKEN")

# --- Gemma3 1B 로드 ---
REPO_ID = "77eileen/gemma3-1b-patent-fto"
BASE_MODEL = "google/gemma-3-1b-it"

# --- Qwen2.5 1.5B 로드 시 아래로 변경 ---
# REPO_ID = "77eileen/qwen2.5-1.5b-patent-fto"
# BASE_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"

tokenizer = AutoTokenizer.from_pretrained(REPO_ID, token=token)

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
)

base_model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    token=token,
    quantization_config=bnb_config,
    device_map="auto",
)

model = PeftModel.from_pretrained(base_model, REPO_ID, token=token)
model.eval()
```

---

## 3. 모델 업로드하기

### 새 repo 생성 + 업로드 (Python)

```python
from huggingface_hub import HfApi

token = "hf_xxxxxxxxxxxxxxxxxxxx"
api = HfApi(token=token)

# repo 생성 (최초 1회)
api.create_repo("77eileen/gemma3-1b-patent-fto", repo_type="model", private=True)

# 모델 폴더 업로드
api.upload_folder(
    folder_path="./SLLM_model/outputs/gemma3-1b-v2",
    repo_id="77eileen/gemma3-1b-patent-fto",
    repo_type="model",
)
```

### 기존 repo에 업로드 (업데이트)

```python
api.upload_folder(
    folder_path="./SLLM_model/outputs/gemma3-1b-v2",
    repo_id="77eileen/gemma3-1b-patent-fto",
    repo_type="model",
    commit_message="Update: 추가 학습"
)
```

---

## 4. 필요한 패키지

```bash
pip install torch transformers peft huggingface_hub python-dotenv bitsandbytes accelerate
```

---

## 문제 해결

### 401 Unauthorized
- HF_TOKEN이 설정되지 않았거나 만료됨
- Private 저장소 접근 권한 없음 (Collaborator 추가 요청)

### CUDA Out of Memory
- `BitsAndBytesConfig`로 4-bit 양자화 사용
- `device_map="auto"` 설정 확인

### Gemma 3 접근 오류
- https://huggingface.co/google/gemma-3-1b-it 에서 라이선스 동의 필요
