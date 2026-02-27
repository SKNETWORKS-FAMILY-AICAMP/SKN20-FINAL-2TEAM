"""디자인 유사성 분석 라우터 — GPT 전용 버전.

원본: design.py
변경:
  1. design_chatbot_gpt에서 import (GPT 버전 LangGraph)
  2. GPT 폴백은 원본과 동일 (이미 GPT 사용)

프론트엔드 계약 (design-chat.html 기준):
    POST /design/image  → {success, thread_id, input_analysis, similar_designs[]}
    POST /design/select → {success, final_report}
    POST /design/text   → {success, thread_id, answer, search_images[]}
"""
import os
import sys
import uuid
import base64
import tempfile
import traceback
import requests
from typing import Optional

from fastapi import APIRouter, Form, UploadFile, File, HTTPException

router = APIRouter()

# ── design/src 패키지 임포트 시도 (GPT 버전) ──────────────
_DESIGN_AVAILABLE = False
_design_graph = None
_import_error = None

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    # design/src를 패키지로 사용하기 위해 경로 추가
    _design_src = os.path.join(_PROJECT_ROOT, "design", "src")
    if os.path.isdir(_design_src) and _design_src not in sys.path:
        sys.path.insert(0, _design_src)

    # ── 변경: design_chatbot_gpt에서 임포트 ──
    from design_chatbot_gpt import create_graph, GraphState
    from langgraph.types import Command

    _design_graph = create_graph()
    _DESIGN_AVAILABLE = True
    print("[design-gpt] LangGraph 디자인 챗봇 (GPT 버전) 로드 성공")
except Exception as e:
    _import_error = str(e)
    print(f"[design-gpt] 디자인 모듈 로드 실패 (GPT 폴백 사용): {e}")


# ── 인메모리 세션 저장소 ──────────────────────────────────
# thread_id → {graph, config, state, comparison_results, base64_image}
_sessions: dict[str, dict] = {}


def _get_openai_client():
    """OpenAI GPT 클라이언트."""
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
    """이미지 업로드 → VLM 분석 + ChromaDB 유사 디자인 검색 (GPT 버전)."""
    file_bytes = await image.read()
    thread_id = str(uuid.uuid4())

    if _DESIGN_AVAILABLE and _design_graph is not None:
        return await _image_via_langgraph(file_bytes, user_query, thread_id)
    else:
        return await _image_via_gpt_fallback(file_bytes, user_query, thread_id)


async def _image_via_langgraph(file_bytes: bytes, user_query: str, thread_id: str) -> dict:
    """LangGraph 디자인 챗봇 (GPT 버전)으로 이미지 분석."""
    # 임시 파일 저장
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

        # 실행 — interrupt에서 멈춤 (유사 디자인 선택 대기)
        result = graph.invoke(initial_state, config)

        # comparison_results에서 프론트엔드 포맷으로 변환
        similar_designs = []
        for comp in result.get("comparison_results", []):
            design = {
                "index": comp["index"],
                "application_number": comp.get("application_number", "N/A"),
                "article_name": comp.get("article_name", "N/A"),
                "admst_stat": comp.get("admst_stat", "N/A"),
                "distance": comp.get("hybrid_score", 0),
            }
            # 이미지 base64 첨부 (URL 또는 로컬 파일)
            img_path = comp.get("image_path", "")
            if img_path:
                try:
                    if img_path.startswith("http://") or img_path.startswith("https://"):
                        resp = requests.get(img_path, timeout=5)
                        if resp.status_code == 200:
                            design["image_base64"] = _image_to_base64(resp.content)
                    elif os.path.exists(img_path):
                        with open(img_path, "rb") as f:
                            design["image_base64"] = _image_to_base64(f.read())
                except Exception:
                    pass
            similar_designs.append(design)

        # 세션 저장 (select 단계에서 사용)
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
        return {"success": False, "error": str(e)}
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


async def _image_via_gpt_fallback(file_bytes: bytes, user_query: str, thread_id: str) -> dict:
    """GPT-4o-mini vision 폴백: 이미지 분석."""
    try:
        client = _get_openai_client()
        b64 = _image_to_base64(file_bytes)
        image_url = f"data:image/jpeg;base64,{b64}"

        # GPT-4o-mini로 이미지 형상 분석
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
    except Exception as e:
        traceback.print_exc()
        return {"success": False, "error": f"GPT 폴백 실패: {str(e)}"}


# ══════════════════════════════════════════════════════
# POST /design/select — 디자인 선택 → 상세 비교 + 리포트
# ══════════════════════════════════════════════════════

@router.post("/design/select")
async def select_design(
    thread_id: str = Form(...),
    selected_index: int = Form(...),
):
    """사용자가 선택한 디자인에 대해 상세 비교 + FTO 리포트 생성."""
    session = _sessions.get(thread_id)
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    if "graph" in session:
        return await _select_via_langgraph(session, selected_index)
    else:
        return await _select_via_gpt_fallback(session, selected_index)


async def _select_via_langgraph(session: dict, selected_index: int) -> dict:
    """LangGraph interrupt 재개."""
    try:
        graph = session["graph"]
        config = session["config"]

        # interrupt 재개: 선택한 디자인 번호 전달
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
    """텍스트 기반 디자인 질문 (일반 대화 + DB 검색) — GPT 버전."""
    new_thread_id = thread_id or str(uuid.uuid4())

    if _DESIGN_AVAILABLE and _design_graph is not None:
        return await _text_via_langgraph(text_query, new_thread_id, image_thread_id)
    else:
        return await _text_via_gpt_fallback(text_query, new_thread_id, image_thread_id)


async def _text_via_langgraph(text_query: str, thread_id: str, image_thread_id: Optional[str]) -> dict:
    """LangGraph 텍스트 경로 (GPT 버전)."""
    try:
        graph = _design_graph
        config = {"configurable": {"thread_id": f"text-{thread_id}"}}

        # 이전 대화 히스토리 가져오기
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

        # 세션에 히스토리 저장
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
        return await _text_via_gpt_fallback(text_query, thread_id, image_thread_id)


async def _text_via_gpt_fallback(text_query: str, thread_id: str, image_thread_id: Optional[str]) -> dict:
    """GPT 폴백: 텍스트 질문 답변."""
    try:
        client = _get_openai_client()

        # 이전 이미지 컨텍스트 가져오기
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
    except Exception as e:
        return {"success": False, "error": str(e)}
