"""RunPod 서버리스 keep-alive.

검색 완료 후 sLLM 분석이 진행되는 동안 워커가 idle timeout으로
꺼지지 않도록 주기적으로 최소 요청을 보낸다.

사용법:
    from app.utils.runpod_keepalive import start_keepalive, stop_keepalive

    start_keepalive()   # 검색 완료 시
    stop_keepalive()    # TOP3 분석 완료 시
"""
import os
import threading
import time

from app.logger import logger

_keepalive_thread: threading.Thread | None = None
_keepalive_stop = threading.Event()

PING_INTERVAL = 25  # 초 (idle timeout 40초보다 짧게)


def _ping_worker():
    """워커에 최소 요청을 보내 alive 유지."""
    from openai import OpenAI

    base_url = os.getenv("RUNPOD_PATENT_BASE_URL") or os.getenv("VLLM_API_URL") or os.getenv("VLLM_BASE_URL", "")
    api_key = os.getenv("RUNPOD_API_KEY", "dummy")
    model = os.getenv("PATENT_VLLM_MODEL", "itsbini/qwen2.5-14b-fto-merged")

    if not base_url:
        logger.warning("[keep-alive] VLLM_API_URL 미설정 — 중단")
        return

    client = OpenAI(base_url=base_url, api_key=api_key, timeout=30)

    while not _keepalive_stop.is_set():
        _keepalive_stop.wait(PING_INTERVAL)
        if _keepalive_stop.is_set():
            break
        try:
            client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
            )
            logger.debug("[keep-alive] ping 전송 완료")
        except Exception as e:
            logger.debug(f"[keep-alive] ping 실패 (무시): {e}")

    logger.info("[keep-alive] 중단됨")


def start_keepalive():
    """keep-alive 시작. 이미 실행 중이면 무시."""
    global _keepalive_thread
    if _keepalive_thread and _keepalive_thread.is_alive():
        return

    _keepalive_stop.clear()
    _keepalive_thread = threading.Thread(target=_ping_worker, daemon=True)
    _keepalive_thread.start()
    logger.info(f"[keep-alive] 시작 (매 {PING_INTERVAL}초)")


def stop_keepalive():
    """keep-alive 중단."""
    global _keepalive_thread
    _keepalive_stop.set()
    _keepalive_thread = None
