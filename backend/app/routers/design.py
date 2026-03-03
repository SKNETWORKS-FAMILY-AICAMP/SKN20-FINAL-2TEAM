"""디자인 유사성 분석 라우터.

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
import threading
import requests
from typing import Optional

from fastapi import APIRouter, Form, UploadFile, File, HTTPException

router = APIRouter()

# ── design/src 패키지 임포트 시도 ──────────────────────
_DESIGN_AVAILABLE = False
_design_graph = None
_design_command_cls = None
_import_error = None
_load_lock = threading.Lock()

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

def _ensure_design_graph_loaded() -> bool:
    """design/src/design_chatbot.py를 지연 로딩하고 그래프를 초기화한다."""
    global _DESIGN_AVAILABLE, _design_graph, _design_command_cls, _import_error

    if _DESIGN_AVAILABLE and _design_graph is not None and _design_command_cls is not None:
        return True

    with _load_lock:
        if _DESIGN_AVAILABLE and _design_graph is not None and _design_command_cls is not None:
            return True

        try:
            # design/src를 패키지로 사용하기 위해 경로 추가
            _design_src = os.path.join(_PROJECT_ROOT, "design", "src")
            if os.path.isdir(_design_src) and _design_src not in sys.path:
                sys.path.insert(0, _design_src)

            # env 키 이름 차이 보정: design/src는 VLLM_API_BASE를 사용
            if not os.getenv("VLLM_API_BASE") and os.getenv("VLLM_BASE_URL"):
                os.environ["VLLM_API_BASE"] = os.getenv("VLLM_BASE_URL")

            from design_chatbot import create_graph
            from langgraph.types import Command

            _design_graph = create_graph()
            _design_command_cls = Command
            _DESIGN_AVAILABLE = True
            _import_error = None
            print("[design] LangGraph 디자인 챗봇 로드 성공")
            return True
        except Exception as e:
            _DESIGN_AVAILABLE = False
            _design_graph = None
            _design_command_cls = None
            _import_error = str(e)
            print(f"[design] 디자인 모듈 로드 실패: {e}")
            return False


# 앱 시작 시 1회 로드 시도 (실패해도 요청 시 재시도)
_ensure_design_graph_loaded()


# ── 인메모리 세션 저장소 ──────────────────────────────────
# thread_id → {graph, config, state, comparison_results, base64_image}
_sessions: dict[str, dict] = {}


@router.get("/design/status")
async def design_status():
    """디자인 챗봇 연결 상태 확인용 엔드포인트."""
    loaded = _ensure_design_graph_loaded()
    return {
        "success": True,
        "design_module_loaded": loaded,
        "mode": "langgraph" if loaded else "unavailable",
        "import_error": _import_error,
    }


# GPT 폴백 (보안 정책: 비활성화 — 외부 API로 데이터 유출 방지)
# def _get_openai_client():
#     """OpenAI GPT 클라이언트 (폴백용)."""
#     from openai import OpenAI
#     api_key = os.getenv("OPENAI_API_KEY", "")
#     if not api_key:
#         raise RuntimeError("OPENAI_API_KEY 미설정")
#     return OpenAI(api_key=api_key, timeout=60)


def _image_to_base64(file_bytes: bytes) -> str:
    return base64.b64encode(file_bytes).decode("utf-8")


def _read_image_bytes(image_path: str) -> Optional[bytes]:
    """imagePath가 URL/절대경로/상대경로일 때 모두 이미지 바이트를 읽는다."""
    if not image_path:
        return None

    try:
        if image_path.startswith("http://") or image_path.startswith("https://"):
            resp = requests.get(image_path, timeout=10)
            if resp.status_code == 200:
                return resp.content
            return None

        candidate_paths = [image_path]

        if not os.path.isabs(image_path):
            candidate_paths.extend([
                os.path.join(_PROJECT_ROOT, image_path),
                os.path.join(_PROJECT_ROOT, "design", image_path),
                os.path.join(_PROJECT_ROOT, "design", "data", image_path),
                os.path.join(_PROJECT_ROOT, "design", "data", "images", image_path),
            ])

        for path in candidate_paths:
            normalized = os.path.normpath(path)
            if os.path.exists(normalized):
                with open(normalized, "rb") as f:
                    return f.read()
    except Exception:
        return None

    return None


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

    if _ensure_design_graph_loaded() and _design_graph is not None:
        return await _image_via_langgraph(file_bytes, user_query, thread_id)
    else:
        # GPT 폴백 비활성화 (보안 정책: 외부 API로 데이터 유출 방지)
        # return await _image_via_gpt_fallback(file_bytes, user_query, thread_id)
        return {
            "success": False,
            "error": "디자인 분석 모듈을 로드할 수 없습니다. "
                     "RunPod 설정(.env)을 확인하세요. "
                     f"상세: {_import_error}",
        }


async def _image_via_langgraph(file_bytes: bytes, user_query: str, thread_id: str) -> dict:
    """LangGraph 디자인 챗봇으로 이미지 분석."""
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
            # 이미지 base64 첨부
            img_path = comp.get("image_path")
            image_bytes = _read_image_bytes(img_path)
            if image_bytes:
                design["image_base64"] = _image_to_base64(image_bytes)
            similar_designs.append(design)

        # base64_image를 세션에 보존 (detailed_compare_node에서 필요)
        b64_from_graph = result.get("base64_image", "")
        print(f"[design] step1 base64_image 길이: {len(b64_from_graph)}자")

        # 세션 저장 (select 단계에서 사용)
        _sessions[thread_id] = {
            "graph": graph,
            "config": config,
            "comparison_results": result.get("comparison_results", []),
            "base64_image": b64_from_graph,
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


# GPT 폴백 (보안 정책: 비활성화 — 외부 API로 데이터 유출 방지)
# async def _image_via_gpt_fallback(file_bytes: bytes, user_query: str, thread_id: str) -> dict:
#     """GPT-4o-mini vision 폴백: 이미지 분석."""
#     try:
#         client = _get_openai_client()
#         b64 = _image_to_base64(file_bytes)
#         image_url = f"data:image/jpeg;base64,{b64}"
#
#         resp = client.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[
#                 {"role": "system", "content": "당신은 제품 디자인 분석 전문가입니다."},
#                 {"role": "user", "content": [
#                     {"type": "text", "text": user_query},
#                     {"type": "image_url", "image_url": {"url": image_url}},
#                 ]},
#             ],
#             max_tokens=1024,
#         )
#         input_analysis = resp.choices[0].message.content
#
#         _sessions[thread_id] = {
#             "input_analysis": input_analysis,
#             "base64_image": b64,
#         }
#
#         return {
#             "success": True,
#             "thread_id": thread_id,
#             "input_analysis": input_analysis,
#             "similar_designs": [],
#         }
#     except Exception as e:
#         traceback.print_exc()
#         return {"success": False, "error": f"GPT 폴백 실패: {str(e)}"}


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
        # GPT 폴백 비활성화 (보안 정책: 외부 API로 데이터 유출 방지)
        # return await _select_via_gpt_fallback(session, selected_index)
        return {
            "success": False,
            "error": "디자인 분석 세션이 유효하지 않습니다. 이미지를 다시 업로드해주세요.",
        }


async def _select_via_langgraph(session: dict, selected_index: int) -> dict:
    """LangGraph interrupt 재개."""
    try:
        graph = session["graph"]
        config = session["config"]

        # base64_image를 Command.update로 상태에 주입
        # (MemorySaver가 대형 base64 문자열을 복원하지 못하는 경우 대비)
        b64_image = session.get("base64_image", "")
        print(f"[design] step2 재개 - selected_index={selected_index}, base64_image 길이={len(b64_image)}")

        # interrupt 재개: 선택한 디자인 번호 전달 + base64_image 상태 주입
        try:
            cmd = _design_command_cls(resume=str(selected_index), update={"base64_image": b64_image})
        except TypeError:
            # update 파라미터를 지원하지 않는 구 버전 langgraph 대비
            cmd = _design_command_cls(resume=str(selected_index))

        result = graph.invoke(cmd, config)

        final_report = result.get("final_report", "리포트 생성에 실패했습니다.")
        print(f"[design] final_report 길이: {len(final_report)}자")

        return {
            "success": True,
            "final_report": final_report,
        }
    except Exception as e:
        traceback.print_exc()
        return {"success": False, "error": str(e)}


# GPT 폴백 (보안 정책: 비활성화 — 외부 API로 데이터 유출 방지)
# async def _select_via_gpt_fallback(session: dict, selected_index: int) -> dict:
#     """GPT 폴백: 상세 비교."""
#     try:
#         client = _get_openai_client()
#         input_analysis = session.get("input_analysis", "분석 정보 없음")
#
#         resp = client.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[
#                 {"role": "system", "content": "당신은 디자인 FTO 전문 어시스턴트입니다."},
#                 {"role": "user", "content": f"입력 디자인 분석:\n{input_analysis}\n\nFTO 리포트를 작성해주세요."},
#             ],
#             max_tokens=2048,
#         )
#         report = resp.choices[0].message.content
#
#         return {
#             "success": True,
#             "final_report": report,
#         }
#     except Exception as e:
#         return {"success": False, "error": str(e)}


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

    if _ensure_design_graph_loaded() and _design_graph is not None:
        return await _text_via_langgraph(text_query, new_thread_id, image_thread_id)
    else:
        # GPT 폴백 비활성화 (보안 정책: 외부 API로 데이터 유출 방지)
        # return await _text_via_gpt_fallback(text_query, new_thread_id, image_thread_id)
        return {
            "success": False,
            "error": "디자인 분석 모듈을 로드할 수 없습니다. "
                     "RunPod 설정(.env)을 확인하세요. "
                     f"상세: {_import_error}",
        }


async def _text_via_langgraph(text_query: str, thread_id: str, image_thread_id: Optional[str]) -> dict:
    """LangGraph 텍스트 경로."""
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
        # GPT 폴백 비활성화 (보안 정책: 외부 API로 데이터 유출 방지)
        # return await _text_via_gpt_fallback(text_query, thread_id, image_thread_id)
        return {"success": False, "error": f"디자인 분석 처리 중 오류: {str(e)}"}


# GPT 폴백 (보안 정책: 비활성화 — 외부 API로 데이터 유출 방지)
# async def _text_via_gpt_fallback(text_query: str, thread_id: str, image_thread_id: Optional[str]) -> dict:
#     """GPT 폴백: 텍스트 질문 답변."""
#     try:
#         client = _get_openai_client()
#
#         context = ""
#         if image_thread_id:
#             prev = _sessions.get(image_thread_id, {})
#             if prev.get("input_analysis"):
#                 context = f"\n\n[이전 이미지 분석 컨텍스트]\n{prev['input_analysis']}"
#
#         resp = client.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=[
#                 {"role": "system", "content": f"당신은 디자인 특허 전문 어시스턴트입니다.{context}"},
#                 {"role": "user", "content": text_query},
#             ],
#             max_tokens=1024,
#         )
#         answer = resp.choices[0].message.content
#
#         return {
#             "success": True,
#             "thread_id": thread_id,
#             "answer": answer,
#             "search_images": [],
#         }
#     except Exception as e:
#         return {"success": False, "error": str(e)}
