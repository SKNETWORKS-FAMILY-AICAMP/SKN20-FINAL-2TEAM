"""RunPod 서버리스 handler — vLLM + LoRA 동적 로딩.

평가 환경과 동일한 설정:
  - base: Qwen/Qwen2.5-14B-Instruct
  - LoRA: itsbini/qwen2.5-14b-fto (enable_lora=True)
  - max_model_len: 4096
  - max_tokens: 2048
  - temperature: 0
"""

import os
import runpod
from vllm import LLM, SamplingParams
from vllm.lora.request import LoRARequest

# ── 설정 ──────────────────────────────────────────
BASE_MODEL = os.environ.get("BASE_MODEL", "Qwen/Qwen2.5-14B-Instruct")
LORA_MODEL = os.environ.get("LORA_MODEL", "itsbini/qwen2.5-14b-fto")
MAX_MODEL_LEN = int(os.environ.get("MAX_MODEL_LEN", "4096"))
MAX_LORA_RANK = int(os.environ.get("MAX_LORA_RANK", "16"))
GPU_UTILIZATION = float(os.environ.get("GPU_UTILIZATION", "0.90"))
HF_TOKEN = os.environ.get("HF_TOKEN", None)

# ── 모델 로드 (Cold Start 시 1회) ──────────────────
print(f"[handler] Loading base model: {BASE_MODEL}")
print(f"[handler] LoRA adapter: {LORA_MODEL}")
print(f"[handler] max_model_len={MAX_MODEL_LEN}, max_lora_rank={MAX_LORA_RANK}")

llm = LLM(
    model=BASE_MODEL,
    tokenizer=BASE_MODEL,
    enable_lora=True,
    max_lora_rank=MAX_LORA_RANK,
    max_model_len=MAX_MODEL_LEN,
    gpu_memory_utilization=GPU_UTILIZATION,
    trust_remote_code=True,
    dtype="float16",
)

lora_request = LoRARequest("fto", 1, LORA_MODEL)

print("[handler] Model loaded successfully!")


# ── OpenAI 호환 /v1/completions 처리 ──────────────
def handler(job):
    """RunPod 서버리스 handler.

    입력 형식 (2가지 지원):

    1) 단순 형식:
       {"input": {"prompt": "...", "max_tokens": 2048, "temperature": 0}}

    2) OpenAI /v1/completions 호환:
       {"input": {"openai_route": "/v1/completions",
                   "openai_input": {"prompt": "...", "model": "...", ...}}}
    """
    job_input = job["input"]

    # OpenAI 호환 형식 처리
    if "openai_route" in job_input:
        openai_input = job_input.get("openai_input", {})
        prompt = openai_input.get("prompt", "")
        max_tokens = openai_input.get("max_tokens", 2048)
        temperature = openai_input.get("temperature", 0)
        stop = openai_input.get("stop", ["<|im_end|>"])
    else:
        # 단순 형식
        prompt = job_input.get("prompt", "")
        max_tokens = job_input.get("max_tokens", 2048)
        temperature = job_input.get("temperature", 0)
        stop = job_input.get("stop", ["<|im_end|>"])

    if not prompt:
        return {"error": "prompt is required"}

    # max_tokens 상한 제한 (평가 환경: 2048)
    max_tokens = min(max_tokens, 4096)

    sampling_params = SamplingParams(
        max_tokens=max_tokens,
        temperature=temperature,
        stop=stop,
    )

    # LoRA 동적 로딩으로 추론
    outputs = llm.generate([prompt], sampling_params, lora_request=lora_request)

    generated_text = outputs[0].outputs[0].text

    # OpenAI /v1/completions 호환 응답
    if "openai_route" in job_input:
        return {
            "id": f"cmpl-runpod-{job['id']}",
            "object": "text_completion",
            "choices": [
                {
                    "index": 0,
                    "text": generated_text,
                    "finish_reason": "stop",
                }
            ],
            "model": LORA_MODEL,
            "usage": {
                "prompt_tokens": len(outputs[0].prompt_token_ids),
                "completion_tokens": len(outputs[0].outputs[0].token_ids),
                "total_tokens": len(outputs[0].prompt_token_ids) + len(outputs[0].outputs[0].token_ids),
            },
        }

    # 단순 형식 응답
    return {
        "text": generated_text,
        "usage": {
            "prompt_tokens": len(outputs[0].prompt_token_ids),
            "completion_tokens": len(outputs[0].outputs[0].token_ids),
        },
    }


runpod.serverless.start({"handler": handler})
