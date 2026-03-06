"""백엔드 연동용 래퍼. 실제 FastAPI 연결은 백엔드 담당자가 수행.

사용법 (백엔드 담당자용):
    from rag.backend_adapter import analyze_product, search_only

    # 검색 + 분석
    result = analyze_product("헤스페리딘 포함 미백 화장품")

    # 검색만
    patents = search_only("헤스페리딘 포함 미백 화장품")
"""


def analyze_product(
    product_description: str,
    top_k: int = 10,
    verbose: bool = False,
    history: list[dict] = None,
) -> dict:
    """검색 + FTO 통합 분석. 백엔드 단일 진입점.

    Args:
        product_description: 사용자 제품 설명.
        top_k: 검색 결과 수.
        verbose: 중간 로그 출력.
        history: 이전 대화 히스토리 [{"role": "user"|"assistant", "content": "..."}]

    Returns:
        {"query": str, "search_results": list, "fto_result": dict}
    """
    from .search.pipeline import analyze
    return analyze(
        product_description,
        top_k=top_k,
        verbose=verbose,
        history=history,
    )


def analyze_single_patent(
    search_result: dict,
    user_query: str,
    verbose: bool = False,
) -> dict:
    """단일 특허 sLLM 분석. 프론트엔드 개별 호출용.

    공개 특허(register_status != '등록')는 sLLM을 거치지 않고
    고정 안내 메시지를 반환한다.

    Args:
        search_result: search_only() 결과 리스트의 개별 항목.
        user_query: 사용자 제품 설명.
        verbose: 중간 로그 출력.

    Returns:
        parse_response() 결과 + patent_id, score, metadata 포함.
    """
    patent_id = search_result.get("patent_id", "unknown")
    metadata = search_result.get("metadata", {})
    register_status = metadata.get("register_status", "")

    # ── 공개 특허: sLLM 스킵 ──
    if register_status != "등록":
        if verbose:
            print(f"[sLLM] {patent_id} 공개 특허 → sLLM 스킵")

        claims = search_result.get("claims", {})
        claim_pub = (
            claims.get("claim_pub_text", "")
            or claims.get("claim_pub", "")
        )

        conclusion_text = (
            "해당 공개특허의 청구항과 사용자의 제품 구성을 비교한 결과,\n"
            "일부 구성요소에서 기술적 유사성이 확인됩니다.\n\n"
            "본 문헌은 현재 출원 공개 단계로 권리가 확정되지 않았으나,\n"
            "향후 등록 시 권리범위에 포함될 가능성이 있으므로\n"
            "심사 경과 및 등록 여부를 지속적으로 확인하는 것이 필요합니다."
        )

        analysis_text = claim_pub.strip() if claim_pub else ""

        return {
            "patent_id": patent_id,
            "score": search_result.get("score", 0),
            "metadata": metadata,
            "estoppel_claim_numbers": search_result.get("estoppel_claim_numbers", []),
            "label": "공개",
            "comparisons": [],
            "analysis_text": analysis_text,
            "conclusion_text": conclusion_text,
            "raw_output": "",
        }

    # ── 등록 특허: sLLM 분석 수행 ──
    from .generate import build_prompt, call_llm, parse_response
    from app.logger import logger as _logger

    if verbose:
        _logger.info(f"[sLLM] {patent_id} 분석 시작")

    messages = build_prompt(search_result, user_query)

    if verbose:
        components_list = search_result.get("components", [])
        has_claims = bool(search_result.get("claims", {}).get("claim_regit_text", ""))
        _logger.info(f"[sLLM] {patent_id} 입력: components={len(components_list)}건, claim_regit={'O' if has_claims else 'X'}")

    import time as _time
    t_llm = _time.time()
    raw_output = call_llm(messages)
    llm_elapsed = _time.time() - t_llm

    if verbose:
        _logger.info(f"[sLLM] {patent_id} 응답 {llm_elapsed:.1f}s ({len(raw_output)}자):\n--- RAW START ---\n{raw_output}\n--- RAW END ---")

    parsed = parse_response(raw_output)

    parsed["patent_id"] = patent_id
    parsed["score"] = search_result.get("score", 0)
    parsed["metadata"] = metadata
    parsed["estoppel_claim_numbers"] = search_result.get("estoppel_claim_numbers", [])

    if verbose:
        _logger.info(f"[sLLM] {patent_id} -> {parsed.get('label', '?')} | sections={parsed.get('sections_found', {})} | comparisons={len(parsed.get('comparisons', []))}행")

    return parsed


def rewrite_query(
    history: list[dict],
    latest_message: str,
    verbose: bool = False,
) -> str:
    """대화 히스토리를 참고하여 후속 질문을 독립적인 제품 설명으로 재작성.

    sLLM(Qwen2.5-14B)에게 간단한 재작성만 요청한다.
    RunPod 서버리스 엔드포인트가 설정되면 /runsync API로 직접 호출하여
    서버리스 워커를 자동으로 깨운다 (generate.py와 동일 방식).
    실패 시 원본 메시지를 그대로 반환.
    """
    from . import config

    # 대화 맥락 구성
    conv_parts = []
    for msg in history[-6:]:  # 최근 6개만
        role = "사용자" if msg["role"] == "user" else "AI"
        conv_parts.append(f"{role}: {msg['content'][:500]}")
    conv_text = "\n".join(conv_parts)

    prompt_text = (
        "당신은 특허 검색을 위한 질문 재작성 도우미입니다.\n"
        "이전 대화를 참고하여 사용자의 최신 질문을 독립적인 제품/기술 설명 한 문장으로 재작성하세요.\n\n"
        "핵심 규칙:\n"
        "- 이전 대화에 나온 모든 성분/구성요소를 빠짐없이 가져오세요.\n"
        "- 사용자가 빼라는 성분만 제거하고, 나머지는 반드시 모두 나열하세요.\n"
        "- 사용자가 대체(대신)하라는 경우, 해당 성분을 새 성분으로 교체하고 나머지는 모두 유지하세요.\n"
        "- 사용자가 추가하라는 경우, 기존 성분 전부 + 새 성분을 함께 나열하세요.\n"
        "- '제외한', '빼고', '없이', '대신' 같은 부정/대체 표현 없이, 최종 성분만 나열하세요.\n"
        "- 사용자가 수치(중량%, 함량 등)를 변경하라는 경우, 기존 수치를 새 수치로 교체하세요.\n"
        "- 특허 분석 결과나 청구항 내용은 포함하지 마세요. 사용자의 제품 설명만 반영하세요.\n"
        "- 재작성된 제품 설명만 출력하세요. 다른 설명이나 인사말은 불필요합니다.\n\n"
        "[예시 1: 성분 제거]\n"
        "이전 대화: 사용자가 'A, B, C, D를 포함하는 화장품'에 대해 질문함\n"
        "현재 질문: B를 빼면 침해가 안될까?\n"
        "재작성: A, C, D를 포함하는 화장품\n\n"
        "[예시 2: 성분 추가]\n"
        "이전 대화: 사용자가 'X, Y, Z를 사용한 배터리'에 대해 질문함\n"
        "현재 질문: 여기에 W를 추가하면 어떨까?\n"
        "재작성: X, Y, Z, W를 사용한 배터리\n\n"
        "[예시 3: 성분 대체]\n"
        "이전 대화: 사용자가 '감초 추출물, 녹차 추출물, 비타민C를 포함하는 미백 크림'에 대해 질문함\n"
        "현재 질문: 감초 추출물 대신 박하엽 추출물을 넣으면?\n"
        "재작성: 박하엽 추출물, 녹차 추출물, 비타민C를 포함하는 미백 크림\n\n"
        "[예시 4: 수치 변경]\n"
        "이전 대화: 사용자가 '리놀레산 60중량%, 올레산, 팔미톨레산을 포함하는 탈모 치료용 화장품'에 대해 질문함\n"
        "현재 질문: 리놀레산을 10중량%로 사용하면 판매해도 될까?\n"
        "재작성: 리놀레산 10중량%, 올레산, 팔미톨레산을 포함하는 탈모 치료용 화장품\n\n"
        "[예시 5: 제형/형태 변경]\n"
        "이전 대화: 사용자가 'A, B, C를 포함하는 수중유형 에멀젼 형태의 미백 화장품'에 대해 질문함\n"
        "현재 질문: 유중수형으로 만들면 침해가 안될까?\n"
        "재작성: A, B, C를 포함하는 유중수형 에멀젼 형태의 미백 화장품\n\n"
        f"[이전 대화]\n{conv_text}\n\n"
        f"[현재 질문]\n{latest_message}\n\n"
        "[재작성된 제품 설명]\n"
    )

    import time as _rw_time

    # RunPod 서버리스 엔드포인트가 설정된 경우: /runsync API 직접 호출 (자동 웨이크업)
    endpoint_id = config.RUNPOD_PATENT_ENDPOINT_ID
    has_runpod = endpoint_id and config.RUNPOD_API_KEY

    if has_runpod:
        import requests

        # Qwen chat template 형식으로 프롬프트 변환
        raw_prompt = (
            f"<|im_start|>user\n{prompt_text}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )

        url = f"https://api.runpod.ai/v2/{endpoint_id}/runsync"
        headers = {
            "Authorization": f"Bearer {config.RUNPOD_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "input": {
                "prompt": raw_prompt,
                "max_tokens": 512,
                "temperature": 0.1,
                "stop": ["<|im_end|>"],
            },
        }

        try:
            if verbose:
                print("[Query Rewrite] RunPod 서버리스 /runsync 호출")

            resp = requests.post(url, json=payload, headers=headers, timeout=config.VLLM_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            status = data.get("status")

            if status == "COMPLETED":
                output = data.get("output", {})
                rewritten = (
                    output.get("text", "")
                    or _extract_runpod_text(output)
                ).strip()
                if verbose:
                    print(f"[Query Rewrite] 원본: {latest_message[:80]}")
                    print(f"[Query Rewrite] 재작성: {rewritten[:200]}")
                return rewritten if rewritten else latest_message

            if status in ("IN_QUEUE", "IN_PROGRESS"):
                run_id = data.get("id")
                if verbose:
                    print(f"[Query Rewrite] Cold start 대기 중... (run_id={run_id})")
                rewritten = _poll_rewrite_result(
                    endpoint_id, run_id, config.RUNPOD_API_KEY, verbose=verbose
                ).strip()
                if verbose:
                    print(f"[Query Rewrite] 원본: {latest_message[:80]}")
                    print(f"[Query Rewrite] 재작성: {rewritten[:200]}")
                return rewritten if rewritten else latest_message

            if verbose:
                print(f"[Query Rewrite] RunPod 오류: status={status}")

        except Exception as e:
            if verbose:
                print(f"[Query Rewrite] RunPod 호출 실패: {e}")

    else:
        # 폴백: OpenAI 호환 API (로컬 vLLM 등)
        from openai import OpenAI

        api_key = config.RUNPOD_API_KEY if config.RUNPOD_API_KEY else "dummy"
        client = OpenAI(
            base_url=config.VLLM_API_URL,
            api_key=api_key,
            timeout=30,
        )

        try:
            resp = client.chat.completions.create(
                model=config.VLLM_MODEL_NAME,
                messages=[{"role": "user", "content": prompt_text}],
                max_tokens=512,
                temperature=0.1,
            )
            rewritten = resp.choices[0].message.content.strip()
            if verbose:
                print(f"[Query Rewrite] 원본: {latest_message[:80]}")
                print(f"[Query Rewrite] 재작성: {rewritten[:200]}")
            return rewritten if rewritten else latest_message
        except Exception as e:
            if verbose:
                print(f"[Query Rewrite] OpenAI 호환 API 호출 실패: {e}")

    if verbose:
        print("[Query Rewrite] 실패, 원본 사용")
    return latest_message


def _extract_runpod_text(output: dict) -> str:
    """RunPod output에서 텍스트 추출 (OpenAI 호환 형식 포함)."""
    choices = output.get("choices", [])
    if choices:
        return choices[0].get("text", "")
    return str(output)


def _poll_rewrite_result(
    endpoint_id: str, run_id: str, api_key: str, verbose: bool = False
) -> str:
    """RunPod 비동기 작업 결과를 polling으로 대기 (rewrite_query 전용)."""
    import requests
    import time

    url = f"https://api.runpod.ai/v2/{endpoint_id}/status/{run_id}"
    headers = {"Authorization": f"Bearer {api_key}"}

    for i in range(60):  # 최대 5분 (5초 * 60)
        time.sleep(5)
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status")

        if verbose and i % 6 == 0:
            print(f"[Query Rewrite] polling... status={status} ({(i+1)*5}초 경과)")

        if status == "COMPLETED":
            output = data.get("output", {})
            return output.get("text", "") or _extract_runpod_text(output)
        if status == "FAILED":
            raise RuntimeError(f"[Query Rewrite] RunPod 작업 실패: {data}")

    raise RuntimeError(f"[Query Rewrite] RunPod 작업 타임아웃: run_id={run_id}")


def search_only(
    product_description: str,
    top_k: int = 10,
    verbose: bool = False,
) -> list[dict]:
    """검색만 수행 (sLLM 분석 없이).

    Args:
        product_description: 사용자 제품 설명.
        top_k: 검색 결과 수.
        verbose: 중간 로그 출력.

    Returns:
        검색 결과 리스트.
    """
    from .search.pipeline import search
    return search(product_description, top_k=top_k, verbose=verbose)
