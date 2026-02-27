"""디자인 유사성 분석 라우터.

프론트엔드 계약 (design-chat.html 기준):
    POST /design/image  → {success, thread_id, input_analysis, similar_designs[]}
    POST /design/select → {success, final_report}
    POST /design/text   → {success, thread_id, answer, search_images[]}

Fallback chain:
    1. Proxy → design service (port 8001)
    2. LangGraph direct import (if available)
    3. GPT-4o-mini fallback (if OPENAI_API_KEY set)
"""
import os
import sys
import uuid
import base64
import logging
import tempfile
import traceback
from typing import Optional

from fastapi import APIRouter, Form, UploadFile, File, HTTPException
import httpx

from app.services.image_analyzer import DesignAnalysisService

router = APIRouter()
logger = logging.getLogger("design")

# ── design/src 패키지 임포트 시도 ──────────────────────
_DESIGN_AVAILABLE = False
_design_graph = None
_import_error = None

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    _design_src = os.path.join(_PROJECT_ROOT, "design", "src")
    if os.path.isdir(_design_src) and _design_src not in sys.path:
        sys.path.insert(0, _design_src)

    from design_chatbot import create_graph, GraphState
    from langgraph.types import Command

    _design_graph = create_graph()
    _DESIGN_AVAILABLE = True
    print("[design] LangGraph 디자인 챗봇 로드 성공")
except Exception as e:
    _import_error = str(e)
    print(f"[design] 디자인 모듈 로드 실패 (프록시/GPT 폴백 사용): {e}")


# ── 인메모리 세션 저장소 (LangGraph/GPT 폴백용) ──────────────────────
_sessions: dict[str, dict] = {}


def _get_openai_client():
    """OpenAI GPT 클라이언트 (폴백용)."""
    from openai import OpenAI
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY 미설정")
    return OpenAI(api_key=api_key, timeout=60)


def _image_to_base64(file_bytes: bytes) -> str:
    return base64.b64encode(file_bytes).decode("utf-8")


# ══════════════════════════════════════════════════════
# POST /design/image — 이미지 업로드 → 유사 디자인 검색
# ══════════════════════════════════════════════════════

@router.post("/design/image")
async def analyze_design_image(
    image: UploadFile = File(...),
    user_query: str = Form("이 제품과 유사한 디자인을 분석해줘"),
):
    """이미지 업로드 → VLM 분석 + ChromaDB 유사 디자인 검색."""
    file_bytes = await image.read()
    thread_id = str(uuid.uuid4())

    # ── Fallback 1: Proxy to design service ──
    try:
        result = await DesignAnalysisService.analyze_image(
            file_bytes, image.filename or "image.jpg",
            image.content_type, user_query,
        )
        logger.info("[design/image] 프록시 성공")
        return result
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        logger.warning(f"[design/image] 프록시 실패 (서비스 미실행?): {e}")
    except httpx.HTTPStatusError as e:
        logger.warning(f"[design/image] 프록시 HTTP 에러: {e.response.status_code}")
    except Exception as e:
        logger.warning(f"[design/image] 프록시 예외: {e}")

    # ── Fallback 2: LangGraph direct ──
    if _DESIGN_AVAILABLE and _design_graph is not None:
        try:
            return await _image_via_langgraph(file_bytes, user_query, thread_id)
        except Exception as e:
            logger.warning(f"[design/image] LangGraph 실패: {e}")

    # ── Fallback 3: GPT ──
    try:
        return await _image_via_gpt_fallback(file_bytes, user_query, thread_id)
    except Exception as e:
        logger.error(f"[design/image] GPT 폴백도 실패: {e}")

    return {
        "success": False,
        "error": "디자인 분석 서비스에 연결할 수 없습니다. "
                 "design 서비스(port 8001)가 실행 중인지 확인하세요.",
    }


async def _image_via_langgraph(file_bytes: bytes, user_query: str, thread_id: str) -> dict:
    """LangGraph 디자인 챗봇으로 이미지 분석."""
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        graph = _design_graph
        config = {"configurable": {"thread_id": thread_id}}

        initial_state = {
            "input_type": "",
            "image_path": tmp_path,
            "text_query": "",
            "user_query": user_query,
            "base64_image": "",
            "input_analysis": "",
            "search_results": {},
            "comparison_results": [],
            "selected_index": 0,
            "detailed_comparison": "",
            "final_report": "",
            "general_answer": "",
            "messages": [],
        }

        result = graph.invoke(initial_state, config)

        similar_designs = []
        for comp in result.get("comparison_results", []):
            design = {
                "index": comp["index"],
                "application_number": comp.get("application_number", "N/A"),
                "article_name": comp.get("article_name", "N/A"),
                "admst_stat": comp.get("admst_stat", "N/A"),
                "distance": comp.get("hybrid_score", 0),
            }
            img_path = comp.get("image_path")
            if img_path and os.path.exists(img_path):
                with open(img_path, "rb") as f:
                    design["image_base64"] = _image_to_base64(f.read())
            similar_designs.append(design)

        _sessions[thread_id] = {
            "graph": graph,
            "config": config,
            "comparison_results": result.get("comparison_results", []),
        }

        return {
            "success": True,
            "thread_id": thread_id,
            "input_analysis": result.get("input_analysis", ""),
            "similar_designs": similar_designs,
        }
    except Exception as e:
        traceback.print_exc()
        raise
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


async def _image_via_gpt_fallback(file_bytes: bytes, user_query: str, thread_id: str) -> dict:
    """GPT-4o-mini vision 폴백: 이미지 분석."""
    client = _get_openai_client()
    b64 = _image_to_base64(file_bytes)
    image_url = f"data:image/jpeg;base64,{b64}"

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "당신은 제품 디자인 분석 전문가입니다. 이미지의 형상을 관찰하고 분석 결과를 제공하세요."},
            {"role": "user", "content": [
                {"type": "text", "text": user_query},
                {"type": "image_url", "image_url": {"url": image_url}},
            ]},
        ],
        max_tokens=1024,
    )
    input_analysis = resp.choices[0].message.content

    _sessions[thread_id] = {
        "input_analysis": input_analysis,
        "base64_image": b64,
    }

    return {
        "success": True,
        "thread_id": thread_id,
        "input_analysis": input_analysis,
        "similar_designs": [],
    }


# ══════════════════════════════════════════════════════
# POST /design/select — 디자인 선택 → 상세 비교 + 리포트
# ══════════════════════════════════════════════════════

@router.post("/design/select")
async def select_design(
    thread_id: str = Form(...),
    selected_index: int = Form(...),
):
    """사용자가 선택한 디자인에 대해 상세 비교 + FTO 리포트 생성."""

    # ── Fallback 1: Proxy ──
    try:
        result = await DesignAnalysisService.select_design(thread_id, selected_index)
        logger.info("[design/select] 프록시 성공")
        return result
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        logger.warning(f"[design/select] 프록시 실패: {e}")
    except httpx.HTTPStatusError as e:
        logger.warning(f"[design/select] 프록시 HTTP 에러: {e.response.status_code}")
    except Exception as e:
        logger.warning(f"[design/select] 프록시 예외: {e}")

    # ── Fallback 2/3: Local session (LangGraph or GPT) ──
    session = _sessions.get(thread_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail="세션을 찾을 수 없습니다. 디자인 서비스가 중단되었을 수 있습니다.",
        )

    if "graph" in session:
        return await _select_via_langgraph(session, selected_index)
    else:
        return await _select_via_gpt_fallback(session, selected_index)


async def _select_via_langgraph(session: dict, selected_index: int) -> dict:
    """LangGraph interrupt 재개."""
    try:
        graph = session["graph"]
        config = session["config"]

        result = graph.invoke(Command(resume=str(selected_index)), config)

        return {
            "success": True,
            "final_report": result.get("final_report", "리포트 생성에 실패했습니다."),
        }
    except Exception as e:
        traceback.print_exc()
        return {"success": False, "error": str(e)}


async def _select_via_gpt_fallback(session: dict, selected_index: int) -> dict:
    """GPT 폴백: 상세 비교."""
    try:
        client = _get_openai_client()
        input_analysis = session.get("input_analysis", "분석 정보 없음")

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "당신은 디자인 FTO 전문 어시스턴트입니다. 입력된 분석 결과를 바탕으로 FTO 리포트를 작성하세요."},
                {"role": "user", "content": f"입력 디자인 분석:\n{input_analysis}\n\n위 분석 결과를 바탕으로 FTO 리포트를 작성해주세요."},
            ],
            max_tokens=2048,
        )
        report = resp.choices[0].message.content

        return {
            "success": True,
            "final_report": report,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ══════════════════════════════════════════════════════
# POST /design/text — 텍스트 질문
# ══════════════════════════════════════════════════════

@router.post("/design/text")
async def design_text_chat(
    text_query: str = Form(...),
    thread_id: Optional[str] = Form(None),
    image_thread_id: Optional[str] = Form(None),
):
    """텍스트 기반 디자인 질문 (일반 대화 + DB 검색)."""
    new_thread_id = thread_id or str(uuid.uuid4())

    # ── Fallback 1: Proxy ──
    try:
        result = await DesignAnalysisService.text_query(
            text_query, thread_id, image_thread_id,
        )
        logger.info("[design/text] 프록시 성공")
        return result
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        logger.warning(f"[design/text] 프록시 실패: {e}")
    except httpx.HTTPStatusError as e:
        logger.warning(f"[design/text] 프록시 HTTP 에러: {e.response.status_code}")
    except Exception as e:
        logger.warning(f"[design/text] 프록시 예외: {e}")

    # ── Fallback 2: LangGraph ──
    if _DESIGN_AVAILABLE and _design_graph is not None:
        try:
            return await _text_via_langgraph(text_query, new_thread_id, image_thread_id)
        except Exception as e:
            logger.warning(f"[design/text] LangGraph 실패: {e}")

    # ── Fallback 3: GPT ──
    try:
        return await _text_via_gpt_fallback(text_query, new_thread_id, image_thread_id)
    except Exception as e:
        logger.error(f"[design/text] GPT 폴백도 실패: {e}")

    return {
        "success": False,
        "error": "디자인 분석 서비스에 연결할 수 없습니다.",
    }


async def _text_via_langgraph(text_query: str, thread_id: str, image_thread_id: Optional[str]) -> dict:
    """LangGraph 텍스트 경로."""
    try:
        graph = _design_graph
        config = {"configurable": {"thread_id": f"text-{thread_id}"}}

        prev_session = _sessions.get(f"text-{thread_id}", {})
        messages = prev_session.get("messages", [])

        initial_state = {
            "input_type": "",
            "image_path": "",
            "text_query": text_query,
            "user_query": text_query,
            "base64_image": "",
            "input_analysis": "",
            "search_results": {},
            "comparison_results": [],
            "selected_index": 0,
            "detailed_comparison": "",
            "final_report": "",
            "general_answer": "",
            "messages": messages,
        }

        result = graph.invoke(initial_state, config)

        _sessions[f"text-{thread_id}"] = {
            "messages": result.get("messages", []),
        }

        return {
            "success": True,
            "thread_id": thread_id,
            "answer": result.get("general_answer", ""),
            "search_images": [],
        }
    except Exception as e:
        traceback.print_exc()
        raise


async def _text_via_gpt_fallback(text_query: str, thread_id: str, image_thread_id: Optional[str]) -> dict:
    """GPT 폴백: 텍스트 질문 답변."""
    client = _get_openai_client()

    context = ""
    if image_thread_id:
        prev = _sessions.get(image_thread_id, {})
        if prev.get("input_analysis"):
            context = f"\n\n[이전 이미지 분석 컨텍스트]\n{prev['input_analysis']}"

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": f"당신은 디자인 특허 전문 어시스턴트입니다. 친절하고 정확하게 답변하세요.{context}"},
            {"role": "user", "content": text_query},
        ],
        max_tokens=1024,
    )
    answer = resp.choices[0].message.content

    return {
        "success": True,
        "thread_id": thread_id,
        "answer": answer,
        "search_images": [],
    }
