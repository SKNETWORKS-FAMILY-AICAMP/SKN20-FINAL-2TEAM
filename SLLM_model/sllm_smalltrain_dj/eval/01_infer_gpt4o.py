"""Step 1 (GPT-4o): GPT-4o API로 테스트 데이터 추론.

기존 02_evaluate.py, 03_compare.py와 동일한 출력 형식(infer_gpt4o.xlsx)을 생성한다.

사용법:
    export OPENAI_API_KEY=sk-...
    python 01_infer_gpt4o.py
    python 01_infer_gpt4o.py --max_samples 100   # 일부만 테스트
    python 01_infer_gpt4o.py --model gpt-4o-mini  # 저렴한 모델로 테스트

출력:
    output/infer_gpt4o.xlsx  (기존 컬럼 + pred_output 컬럼)
"""

import argparse
import os
import sys
import time
from pathlib import Path

import pandas as pd
from loguru import logger

# ─── 로깅 설정 ────────────────────────────────────────────
LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
LOG_DIR.mkdir(exist_ok=True)
logger.remove()
logger.add(sys.stderr, level="INFO")
logger.add(
    LOG_DIR / "eval_infer_gpt4o_{time:YYYY-MM-DD_HH-mm-ss}.log",
    level="DEBUG",
    rotation="100 MB",
    encoding="utf-8",
)

# ─── 경로 ───────────────────────────────────────────────
EVAL_DIR = Path(__file__).resolve().parent
BASE_DIR = EVAL_DIR.parents[1]  # SLLM_model/
DEFAULT_TEST_DATA = str(BASE_DIR / "data" / "sllm_qwen_data" / "sllm_test.xlsx")

# ─── 시스템 프롬프트 (다른 infer 스크립트와 동일) ────────────
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
    """입력 프롬프트 구성 (다른 infer 스크립트와 동일)."""
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


def call_gpt4o(client, model: str, user_content: str, max_tokens: int, retries: int = 3) -> str:
    """GPT-4o API 호출. 실패 시 최대 retries회 재시도."""
    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                max_tokens=max_tokens,
                temperature=0.0,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.warning(f"API 오류 (시도 {attempt+1}/{retries}): {e}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)  # 지수 백오프
    logger.error("최대 재시도 초과. 빈 문자열 반환.")
    return ""


def main():
    parser = argparse.ArgumentParser(description="GPT-4o 추론 (Step 1)")
    parser.add_argument("--model", default="gpt-4o", help="OpenAI 모델명 (기본: gpt-4o)")
    parser.add_argument("--test_data", default=DEFAULT_TEST_DATA, help="테스트 데이터 경로")
    parser.add_argument("--output_dir", default="./output", help="결과 저장 폴더")
    parser.add_argument("--max_tokens", type=int, default=2048, help="최대 생성 토큰 수")
    parser.add_argument("--max_samples", type=int, default=None, help="테스트할 최대 샘플 수 (미지정 시 전체)")
    parser.add_argument("--model_name", default="gpt4o", help="출력 파일명에 쓸 모델 이름")
    args = parser.parse_args()

    # API 키 확인
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
        logger.error("export OPENAI_API_KEY=sk-... 후 재실행하세요.")
        sys.exit(1)

    try:
        from openai import OpenAI
    except ImportError:
        logger.error("openai 패키지가 없습니다. pip install openai 후 재실행하세요.")
        sys.exit(1)

    client = OpenAI(api_key=api_key)

    logger.info(f"=== GPT-4o 추론 시작 ===")
    logger.info(f"모델: {args.model}")
    logger.info(f"테스트 데이터: {args.test_data}")

    df = pd.read_excel(args.test_data)
    if args.max_samples:
        df = df.head(args.max_samples)
        logger.info(f"샘플 제한: {args.max_samples}건")
    logger.info(f"총 추론 대상: {len(df)}건")

    preds = []
    for i, (_, row) in enumerate(df.iterrows()):
        user_content = build_prompt(row)
        pred = call_gpt4o(client, args.model, user_content, args.max_tokens)
        preds.append(pred)

        if (i + 1) % 10 == 0 or (i + 1) == len(df):
            logger.info(f"[{i+1}/{len(df)}] 진행 중...")

    # 저장
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    df["pred_output"] = preds
    out_path = out_dir / f"infer_{args.model_name}.xlsx"
    df.to_excel(out_path, index=False)
    logger.success(f"추론 완료! 저장: {out_path}")
    logger.info(f"다음 단계: python 02_evaluate.py --input {out_path} --model_name {args.model_name}")


if __name__ == "__main__":
    main()
