# HuggingFace 모델 사용 가이드

## 모델 정보

| 항목 | 내용 |
|------|------|
| 저장소 | https://huggingface.co/77eileen/patent |
| 베이스 모델 | google/gemma-3-4b-it |
| 어댑터 | LoRA (QLoRA로 학습) |
| 접근 권한 | Private |

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

## 2. 학습된 모델 불러오기

### 기본 사용법

```python
import os
import torch
from dotenv import load_dotenv
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel

load_dotenv()
token = os.environ.get("HF_TOKEN")

# 1. 토크나이저 로드 (HuggingFace에서)
tokenizer = AutoTokenizer.from_pretrained(
    "77eileen/patent",
    token=token
)

# 2. 베이스 모델 로드
base_model = AutoModelForCausalLM.from_pretrained(
    "google/gemma-3-4b-it",
    token=token,
    torch_dtype=torch.bfloat16,
    device_map="auto",
)

# 3. LoRA 어댑터 적용
model = PeftModel.from_pretrained(
    base_model,
    "77eileen/patent",
    token=token
)
model.eval()
```

### 4-bit 양자화로 메모리 절약 (권장)

```python
from transformers import BitsAndBytesConfig

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
)

base_model = AutoModelForCausalLM.from_pretrained(
    "google/gemma-3-4b-it",
    token=token,
    quantization_config=bnb_config,
    device_map="auto",
)

model = PeftModel.from_pretrained(
    base_model,
    "77eileen/patent",
    token=token
)
```

### 추론 예시

```python
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

# 추론
prompt = build_prompt(
    user_query="ATPA 겔화제 30%, 디부틸라우로일글루타마이드 5%...",
    regit_num="1014541990000",
    claim_text="[청구항 내용]"
)

inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

with torch.no_grad():
    outputs = model.generate(
        **inputs,
        max_new_tokens=512,
        do_sample=False,
        pad_token_id=tokenizer.pad_token_id,
    )

response = tokenizer.decode(outputs[0], skip_special_tokens=True)
response = response.split("<assistant>")[-1].strip()
print(response)
```

---

## 3. 새 모델 업로드하기 (팀원용)

### CLI로 업로드 (권장)

```bash
# 1. HuggingFace CLI 로그인
huggingface-cli login
# 토큰 입력 (Write 권한 필요)

# 2. 모델 업로드
huggingface-cli upload 77eileen/patent ./outputs/gemma3-4b-it-lora \
    --repo-type model \
    --commit-message "Update: 추가 학습 v2"
```

### Python으로 업로드

```python
from huggingface_hub import HfApi

api = HfApi()

# 폴더 전체 업로드
api.upload_folder(
    folder_path="./outputs/gemma3-4b-it-lora",
    repo_id="77eileen/patent",
    repo_type="model",
    token=os.environ.get("HF_TOKEN"),
    commit_message="Update: 추가 학습 v2"
)
```

### 특정 파일만 업로드

```python
api.upload_file(
    path_or_fileobj="./outputs/gemma3-4b-it-lora/adapter_model.safetensors",
    path_in_repo="adapter_model.safetensors",
    repo_id="77eileen/patent",
    token=os.environ.get("HF_TOKEN"),
)
```

---

## 4. 버전 관리

### 브랜치로 버전 구분

```bash
# 새 브랜치에 업로드
huggingface-cli upload 77eileen/patent ./outputs/new-model \
    --repo-type model \
    --revision v2-extended-training
```

### 불러올 때 버전 지정

```python
model = PeftModel.from_pretrained(
    base_model,
    "77eileen/patent",
    revision="v2-extended-training",  # 브랜치명
    token=token
)
```

---

## 5. 필요한 패키지

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
- https://huggingface.co/google/gemma-3-4b-it 에서 라이선스 동의 필요
