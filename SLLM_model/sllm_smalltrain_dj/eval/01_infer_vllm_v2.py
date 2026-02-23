"""Step 1: 모델 추론 (vLLM v2 — HuggingFace repo 지원).

vLLM 엔진으로 배치 추론. 로컬 경로 또는 HuggingFace repo ID 모두 지원.
HF repo인 경우 자동 다운로드 후 LoRA adapter를 적용한다.

사용법:
    # 로컬 LoRA adapter
    python 01_infer_vllm_v2.py --model_path ./qwen7b_adapter --model_name qwen7b_ft

    # HuggingFace repo (LoRA adapter)
    python 01_infer_vllm_v2.py --model_path 77eileen/qwen2.5-7b-patent-fto --model_name qwen7b_ft

    # 머지 모델 (LoRA 아님)
    python 01_infer_vllm_v2.py --model_path Qwen/Qwen2.5-7B-Instruct --model_name qwen7b_base

출력:
    output/infer_qwen7b_ft.xlsx  (원본 + pred_output 컬럼 추가)
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
from loguru import logger
from vllm import LLM, SamplingParams
from vllm.lora.request import LoRARequest

# ─── 로깅 설정 ────────────────────────────────────────────
LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
LOG_DIR.mkdir(exist_ok=True)
logger.remove()
logger.add(sys.stderr, level="INFO")
logger.add(
    LOG_DIR / "eval_infer_vllm_{time:YYYY-MM-DD_HH-mm-ss}.log",
    level="DEBUG",
    rotation="100 MB",
    encoding="utf-8",
)


SYSTEM_PROMPT = """당신은 화장품 특허 침해(FTO) 분석 전문가입니다.

[문구 규칙]
- "판단"이라는 단어 사용 금지 → "분석"으로 대체
- "리스크" 사용 금지 → "가능성"으로 대체

[분석 규칙]
- 구성요소 완비의 원칙: 모든 구성요소를 포함해야 침해
- 균등론: 수치 경미 이탈 시 전문가 검토 대상
- 금반언: 등록청구항에서 삭제된 구성은 침해 주장 불가
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


def build_prompt(row: pd.Series) -> str:
    """입력 프롬프트 구성: user_query → claim_reg → claim_pub → components → 메타정보"""
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


def resolve_model_path(model_path_str: str) -> Path:
    """로컬 경로면 그대로, HF repo ID면 snapshot_download로 다운로드."""
    local_path = Path(model_path_str)
    if local_path.exists():
        logger.info(f"로컬 경로 사용: {local_path}")
        return local_path

    # HF repo ID로 간주 (public repo → 토큰 불필요)
    logger.info(f"HF repo 감지: {model_path_str} → 다운로드 시작...")
    from huggingface_hub import snapshot_download

    downloaded = snapshot_download(repo_id=model_path_str)
    logger.info(f"다운로드 완료: {downloaded}")
    return Path(downloaded)


def main():
    parser = argparse.ArgumentParser(description="Step 1: 모델 추론 (vLLM v2 — HF 지원)")
    parser.add_argument("--model_path", required=True, help="로컬 경로 또는 HuggingFace repo ID")
    parser.add_argument("--model_name", required=True, help="모델 이름 (출력 파일명에 사용)")
    parser.add_argument("--test_data", default="../../data/sllm_qwen_data/sllm_test.xlsx")
    parser.add_argument("--output_dir", default="./output")
    parser.add_argument("--max_tokens", type=int, default=2048)
    parser.add_argument("--gpu_memory", type=float, default=0.9, help="GPU 메모리 사용 비율 (0~1)")
    args = parser.parse_args()

    logger.info(f"=== 모델 추론 (vLLM v2): {args.model_name} ===")

    # ─── 모델 경로 해석 (로컬 or HF) ─────────────────────
    model_path = resolve_model_path(args.model_path)

    # ─── LoRA 어댑터 여부 확인 ──────────────────────────
    adapter_config_path = model_path / "adapter_config.json"
    is_lora = adapter_config_path.exists()

    if is_lora:
        with open(adapter_config_path) as f:
            adapter_cfg = json.load(f)
        base_model = adapter_cfg["base_model_name_or_path"]
        lora_rank = adapter_cfg.get("r", 16)
        logger.info(f"LoRA 어댑터 감지 → 베이스: {base_model}, rank: {lora_rank}")
        llm = LLM(
            model=base_model,
            trust_remote_code=True,
            gpu_memory_utilization=args.gpu_memory,
            max_model_len=4096,
            enable_lora=True,
            max_lora_rank=lora_rank,
        )
        lora_request = LoRARequest("adapter", 1, str(model_path.resolve()))
    else:
        logger.info(f"머지 모델 로드: {model_path}")
        llm = LLM(
            model=str(model_path),
            trust_remote_code=True,
            gpu_memory_utilization=args.gpu_memory,
            max_model_len=4096,
        )
        lora_request = None

    tokenizer = llm.get_tokenizer()

    sampling_params = SamplingParams(
        max_tokens=args.max_tokens,
        temperature=0,
    )

    # ─── 데이터 로드 & 프롬프트 구성 ────────────────────
    df = pd.read_excel(args.test_data)
    logger.info(f"테스트: {len(df)}건")

    prompts = []
    for _, row in df.iterrows():
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_prompt(row)},
        ]
        prompts.append(
            tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        )

    # ─── 배치 추론 ──────────────────────────────────────
    logger.info(f"vLLM 배치 추론 시작 ({len(prompts)}건)")
    outputs = llm.generate(prompts, sampling_params, lora_request=lora_request)

    preds = [output.outputs[0].text for output in outputs]
    logger.info(f"추론 완료: {len(preds)}건")

    # ─── 저장 ───────────────────────────────────────────
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    df["pred_output"] = preds
    out_path = out_dir / f"infer_{args.model_name}.xlsx"
    df.to_excel(out_path, index=False)
    logger.success(f"추론 완료! 저장: {out_path}")


if __name__ == "__main__":
    main()
