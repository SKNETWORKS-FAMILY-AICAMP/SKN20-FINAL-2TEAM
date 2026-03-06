# RunPod 서버리스 — vLLM + LoRA 동적 로딩
# base: Qwen/Qwen2.5-14B-Instruct + LoRA: itsbini/qwen2.5-14b-fto

FROM runpod/worker-v1-vllm:v2.7.0stable-cuda12.1.0

# 커스텀 handler 복사 (기본 handler 대체)
COPY handler.py /app/handler.py

# RunPod serverless handler 진입점
CMD ["python", "/app/handler.py"]
