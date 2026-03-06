"""디자인 유사성 분석 라우터.

프론트엔드 계약 (design-chat.html 기준):
    POST /design/image  → {success, thread_id, input_analysis, similar_designs[]}
    POST /design/select → {success, final_report}
    POST /design/text   → {success, thread_id, answer, search_images[]}
    GET  /design/session/{thread_id} → 세션 히스토리 조회
"""
import os
import sys
import uuid
import base64
import tempfile
import traceback
import threading
import json
import requests
from loguru import logger
from typing import Optional

from fastapi import APIRouter, Form, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.design_session import (
    DesignSession,
    DesignSessionImage,
    DesignSessionMessage,
    DesignSessionStatus,
    ImageType,
    MessageRole,
)
from app.services.s3_service import s3_service
from app.config import settings

router = APIRouter()

# ── design/src 패키지 임포트 시도 ──────────────────────
_DESIGN_AVAILABLE = False
_design_graph = None
_design_command_cls = None
_detailed_compare_fn = None   # detailed_compare_node 함수 (재비교용)
_generate_report_fn = None    # generate_report_node 함수 (재비교용)
_import_error = None
_load_lock = threading.Lock()

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

def _ensure_design_graph_loaded() -> bool:
    """design/src/design_chatbot.py를 지연 로딩하고 그래프를 초기화한다."""
    global _DESIGN_AVAILABLE, _design_graph, _design_command_cls, _detailed_compare_fn, _generate_report_fn, _import_error

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

            from design_chatbot import create_graph, detailed_compare_node, generate_report_node
            from langgraph.types import Command

            _design_graph = create_graph()
            _design_command_cls = Command
            _detailed_compare_fn = detailed_compare_node
            _generate_report_fn = generate_report_node
            _DESIGN_AVAILABLE = True
            _import_error = None
            print("[design] LangGraph 디자인 챗봇 로드 성공")
            return True
        except Exception as e:
            _DESIGN_AVAILABLE = False
            _design_graph = None
            _design_command_cls = None
            _detailed_compare_fn = None
            _generate_report_fn = None
            _import_error = str(e)
            print(f"[design] 디자인 모듈 로드 실패: {e}")
            return False


# 앱 시작 시 로드하지 않음 (첫 요청 시 _ensure_design_graph_loaded() 호출로 지연 로딩)


# ── 인메모리 세션 저장소 (LangGraph 상태용) ──────────────────
# thread_id → {graph, config, state, comparison_results, base64_image}
_sessions: dict[str, dict] = {}


def _check_s3_available() -> bool:
    """S3 설정이 있는지 확인."""
    return bool(settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY)


@router.get("/design/status")
async def design_status():
    """디자인 챗봇 연결 상태 확인용 엔드포인트."""
    loaded = _ensure_design_graph_loaded()
    s3_available = _check_s3_available()
    return {
        "success": True,
        "design_module_loaded": loaded,
        "mode": "langgraph" if loaded else "unavailable",
        "import_error": _import_error,
        "s3_available": s3_available,
    }


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
    db: Session = Depends(get_db),
):
    """이미지 업로드 → S3 저장 → VLM 분석 + ChromaDB 유사 디자인 검색."""
    file_bytes = await image.read()
    thread_id = str(uuid.uuid4())

    if _ensure_design_graph_loaded() and _design_graph is not None:
        return await _image_via_langgraph(
            file_bytes, user_query, thread_id,
            image.filename, len(file_bytes), db
        )
    else:
        return {
            "success": False,
            "error": "디자인 분석 모듈을 로드할 수 없습니다. "
                     "RunPod 설정(.env)을 확인하세요. "
                     f"상세: {_import_error}",
        }


async def _image_via_langgraph(
    file_bytes: bytes,
    user_query: str,
    thread_id: str,
    original_filename: Optional[str],
    file_size: int,
    db: Session,
) -> dict:
    """LangGraph 디자인 챗봇으로 이미지 분석 + S3/RDS 저장."""

    # 1. RDS에 세션 생성 — 30개 초과 시 오래된 세션 자동 삭제
    SESSION_LIMIT = 30
    existing_count = (
        db.query(DesignSession)
        .filter(~DesignSession.thread_id.startswith("text-"))
        .count()
    )
    if existing_count >= SESSION_LIMIT:
        delete_ids = [
            row[0] for row in
            db.query(DesignSession.id)
            .filter(~DesignSession.thread_id.startswith("text-"))
            .order_by(DesignSession.created_at.asc())
            .limit(existing_count - SESSION_LIMIT + 1)
            .all()
        ]
        if delete_ids:
            db.query(DesignSessionMessage).filter(
                DesignSessionMessage.session_id.in_(delete_ids)
            ).delete(synchronize_session=False)
            db.query(DesignSessionImage).filter(
                DesignSessionImage.session_id.in_(delete_ids)
            ).delete(synchronize_session=False)
            db.query(DesignSession).filter(
                DesignSession.id.in_(delete_ids)
            ).delete(synchronize_session=False)
            db.commit()

    session = DesignSession(
        thread_id=thread_id,
        status=DesignSessionStatus.analyzing,
    )
    db.add(session)
    db.flush()  # session.id 확보

    # 2. S3에 이미지 업로드 (설정된 경우)
    s3_key = None
    s3_url = None
    if _check_s3_available():
        try:
            s3_key, s3_url = s3_service.upload_image(
                file_bytes=file_bytes,
                session_id=thread_id,
                filename=original_filename,
            )

            # RDS에 이미지 정보 저장
            session_image = DesignSessionImage(
                session_id=session.id,
                image_type=ImageType.user_upload,
                s3_key=s3_key,
                s3_url=s3_url,
                original_filename=original_filename,
                file_size=file_size,
            )
            db.add(session_image)
            print(f"[design] S3 업로드 완료: {s3_url}")
        except Exception as e:
            print(f"[design] S3 업로드 실패 (계속 진행): {e}")

    # 3. 임시 파일 저장 (LangGraph용)
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
                "image_path": comp.get("image_path", ""),  # 재비교 시 직접 노드 호출용
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

        # 4. RDS 세션 업데이트
        input_analysis = result.get("input_analysis", "")
        session.status = DesignSessionStatus.waiting_selection
        session.input_analysis = input_analysis
        # similar_designs(base64 포함)를 저장 → 세션 복원 시 카드 재렌더링에 사용
        session.comparison_results_json = similar_designs

        # 5. 대화 히스토리 저장
        if user_query:
            user_msg = DesignSessionMessage(
                session_id=session.id,
                role=MessageRole.user,
                content=user_query,
            )
            db.add(user_msg)

        if input_analysis:
            assistant_msg = DesignSessionMessage(
                session_id=session.id,
                role=MessageRole.assistant,
                content=input_analysis,
            )
            db.add(assistant_msg)

        db.commit()

        # 인메모리 세션 저장 (select 단계에서 사용)
        # user_image_base64: LangGraph 내부 포맷 대신 원본 bytes로 직접 변환 (표시용)
        _sessions[thread_id] = {
            "graph": graph,
            "config": config,
            "comparison_results": result.get("comparison_results", []),
            "base64_image": b64_from_graph,
            "user_image_base64": _image_to_base64(file_bytes),
            "s3_url": s3_url,
        }

        return {
            "success": True,
            "thread_id": thread_id,
            "input_analysis": input_analysis,
            "similar_designs": similar_designs,
            "s3_url": s3_url,  # 프론트엔드에서 참조 가능
        }
    except Exception as e:
        traceback.print_exc()
        # 에러 상태로 업데이트
        session.status = DesignSessionStatus.error
        db.commit()
        return {"success": False, "error": str(e)}
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ══════════════════════════════════════════════════════
# POST /design/select — 디자인 선택 → 상세 비교 + 리포트
# ══════════════════════════════════════════════════════

@router.post("/design/select")
async def select_design(
    thread_id: str = Form(...),
    selected_index: int = Form(...),
    db: Session = Depends(get_db),
):
    """사용자가 선택한 디자인에 대해 상세 비교 + FTO 리포트 생성."""
    session = _sessions.get(thread_id)

    # 인메모리 세션이 있으면 LangGraph로 처리
    if session:
        if "graph" in session:
            # DB 상태 확인: 이미 completed면 LangGraph 그래프가 종료됐으므로 노드 직접 호출
            db_session = db.query(DesignSession).filter(
                DesignSession.thread_id == thread_id
            ).first()
            if db_session and db_session.status == DesignSessionStatus.completed:
                return await _recompare_via_nodes(session, selected_index, thread_id, db, db_session)
            return await _select_via_langgraph(session, selected_index, thread_id, db)
        return {
            "success": False,
            "error": "디자인 분석 세션이 유효하지 않습니다. 이미지를 다시 업로드해주세요.",
        }

    # 인메모리 없음 → DB 확인
    db_session = db.query(DesignSession).filter(
        DesignSession.thread_id == thread_id
    ).first()

    if not db_session:
        return {
            "success": False,
            "error": "세션을 찾을 수 없습니다. 이미지를 다시 업로드해주세요.",
            "session_expired": True,
        }

    if db_session.status == DesignSessionStatus.completed:
        # 완료된 세션 + 인메모리 데이터 있으면 재비교, 없으면 저장된 리포트 반환
        if _detailed_compare_fn and _generate_report_fn:
            return await _recompare_via_nodes(session, selected_index, thread_id, db, db_session)
        return {
            "success": True,
            "final_report": db_session.final_report or "리포트가 저장되지 않았습니다.",
        }

    # waiting_selection / analyzing / error → 서버 재시작으로 LangGraph 상태 소실
    return {
        "success": False,
        "error": "세션이 만료되었습니다. 서버 재시작으로 LangGraph 상태가 초기화되었습니다. "
                 "이미지를 다시 업로드해주세요.",
        "session_expired": True,
    }


async def _select_via_langgraph(
    session: dict,
    selected_index: int,
    thread_id: str,
    db: Session,
) -> dict:
    """LangGraph interrupt 재개 + RDS 업데이트."""
    try:
        graph = session["graph"]
        config = session["config"]

        # base64_image를 Command.update로 상태에 주입
        b64_image = session.get("base64_image", "")
        print(f"[design] step2 재개 - selected_index={selected_index}, base64_image 길이={len(b64_image)}")

        # interrupt 재개: 선택한 디자인 번호 전달 + base64_image 상태 주입
        try:
            cmd = _design_command_cls(resume=str(selected_index), update={"base64_image": b64_image})
        except TypeError:
            cmd = _design_command_cls(resume=str(selected_index))

        result = graph.invoke(cmd, config)

        final_report = result.get("final_report", "리포트 생성에 실패했습니다.")
        print(f"[design] final_report 길이: {len(final_report)}자")

        # RDS 세션 업데이트
        db_session = db.query(DesignSession).filter(
            DesignSession.thread_id == thread_id
        ).first()

        if db_session:
            db_session.status = DesignSessionStatus.completed
            db_session.selected_index = selected_index
            db_session.final_report = final_report

            # 최종 리포트를 대화 히스토리에 추가
            assistant_msg = DesignSessionMessage(
                session_id=db_session.id,
                role=MessageRole.assistant,
                content=final_report,
            )
            db.add(assistant_msg)
            db.commit()

        # 선택된 디자인 이미지 정보
        comparison_results = session.get("comparison_results", [])
        selected = next((r for r in comparison_results if r.get("index") == selected_index), None)
        selected_image_base64 = ""
        selected_info = {}
        if selected:
            selected_info = {
                "index": selected.get("index"),
                "application_number": selected.get("application_number", ""),
                "article_name": selected.get("article_name", ""),
                "admst_stat": selected.get("admst_stat", ""),
            }
            img_bytes = _read_image_bytes(selected.get("image_path", ""))
            if img_bytes:
                selected_image_base64 = _image_to_base64(img_bytes)

        return {
            "success": True,
            "final_report": final_report,
            "user_image_s3_url": session.get("s3_url", ""),
            "user_image_base64": session.get("user_image_base64", ""),
            "selected_design": {**selected_info, "image_base64": selected_image_base64} if selected else None,
        }
    except Exception as e:
        traceback.print_exc()
        return {"success": False, "error": str(e)}


async def _recompare_via_nodes(
    mem_session: Optional[dict],
    selected_index: int,
    thread_id: str,
    db: Session,
    db_session,
) -> dict:
    """인메모리 또는 DB 데이터로 노드 함수를 직접 호출하여 다른 디자인과 재비교."""
    try:
        # 인메모리 우선, 없으면 DB에서 복원
        comparison_results = (mem_session or {}).get("comparison_results", [])
        b64_image = (mem_session or {}).get("base64_image", "")          # VLM 노드용 (LangGraph 포맷)
        user_display_b64 = (mem_session or {}).get("user_image_base64", "")  # 표시/PDF용 (원본 bytes)

        # DB에서 comparison_results 복원 (인메모리에 없을 때)
        if not comparison_results:
            stored = db_session.comparison_results_json
            if isinstance(stored, str):
                stored = json.loads(stored)
            comparison_results = stored or []

        # DB에서 원본 이미지 복원 (인메모리에 없을 때)
        if not b64_image and db_session.images:
            user_upload = next(
                (img for img in db_session.images if img.image_type == ImageType.user_upload),
                None
            )
            if user_upload and user_upload.s3_url:
                img_bytes = _read_image_bytes(user_upload.s3_url)
                if img_bytes:
                    b64_image = _image_to_base64(img_bytes)
                    user_display_b64 = b64_image  # S3에서 복원한 경우 동일하게 사용

        if not comparison_results or not b64_image:
            return {"success": False, "error": "재비교에 필요한 데이터가 없습니다. 이미지를 다시 업로드해주세요."}

        selected = next((r for r in comparison_results if r.get("index") == selected_index), None)
        if not selected:
            return {"success": False, "error": f"{selected_index}번 디자인을 찾을 수 없습니다."}

        # 노드 함수에 넘길 상태 구성
        state = {
            "input_type": "image",
            "image_path": "",
            "text_query": "",
            "user_query": "이 디자인과 상세 비교해줘",
            "base64_image": b64_image,
            "input_analysis": db_session.input_analysis or "",
            "search_results": {},
            "comparison_results": comparison_results,
            "selected_index": selected_index,
            "detailed_comparison": "",
            "final_report": "",
            "general_answer": "",
            "messages": [],
        }

        # LangGraph 우회 — 노드 함수 직접 호출
        try:
            state = _detailed_compare_fn(state)
        except TypeError as e:
            if "null value for" in str(e) or "choices" in str(e):
                logger.warning(f"[상세비교] VLM 응답 오류 (RunPod cold start 또는 이미지 크기 초과): {e}")
                state["detailed_comparison"] = "VLM 서버 응답 오류 — 잠시 후 다시 시도해주세요."
            else:
                raise
        state = _generate_report_fn(state)

        final_report = state.get("final_report", "리포트 생성 실패")

        # DB 업데이트
        db_session.selected_index = selected_index
        db_session.final_report = final_report
        assistant_msg = DesignSessionMessage(
            session_id=db_session.id,
            role=MessageRole.assistant,
            content=final_report,
        )
        db.add(assistant_msg)
        db.commit()

        # 선택 디자인 이미지
        selected_info = {
            "index": selected.get("index"),
            "application_number": selected.get("application_number", ""),
            "article_name": selected.get("article_name", ""),
            "admst_stat": selected.get("admst_stat", ""),
        }
        selected_image_base64 = ""
        img_bytes = _read_image_bytes(selected.get("image_path", ""))
        if img_bytes:
            selected_image_base64 = _image_to_base64(img_bytes)

        return {
            "success": True,
            "final_report": final_report,
            "user_image_base64": user_display_b64,  # 원본 bytes 기반 base64 (표시/PDF용)
            "user_image_s3_url": (mem_session or {}).get("s3_url", ""),
            "selected_design": {**selected_info, "image_base64": selected_image_base64},
        }
    except Exception as e:
        traceback.print_exc()
        return {"success": False, "error": str(e)}


# ══════════════════════════════════════════════════════
# POST /design/text — 텍스트 질문
# ══════════════════════════════════════════════════════

@router.post("/design/text")
async def design_text_chat(
    text_query: str = Form(...),
    thread_id: Optional[str] = Form(None),
    image_thread_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """텍스트 기반 디자인 질문 (일반 대화 + DB 검색 + 멀티턴 히스토리)."""
    new_thread_id = thread_id or str(uuid.uuid4())

    if _ensure_design_graph_loaded() and _design_graph is not None:
        return await _text_via_langgraph(text_query, new_thread_id, image_thread_id, db)
    else:
        return {
            "success": False,
            "error": "디자인 분석 모듈을 로드할 수 없습니다. "
                     "RunPod 설정(.env)을 확인하세요. "
                     f"상세: {_import_error}",
        }


async def _text_via_langgraph(
    text_query: str,
    thread_id: str,
    image_thread_id: Optional[str],
    db: Session,
) -> dict:
    """LangGraph 텍스트 경로 + RDS 멀티턴 히스토리."""
    try:
        graph = _design_graph
        text_thread_id = f"text-{thread_id}"
        config = {"configurable": {"thread_id": text_thread_id}}

        # 1. RDS에서 세션 조회 또는 생성
        db_session = db.query(DesignSession).filter(
            DesignSession.thread_id == text_thread_id
        ).first()

        if not db_session:
            db_session = DesignSession(
                thread_id=text_thread_id,
                status=DesignSessionStatus.analyzing,
            )
            db.add(db_session)
            db.flush()

        # 2. RDS에서 이전 대화 히스토리 로드
        messages = []
        db_messages = db.query(DesignSessionMessage).filter(
            DesignSessionMessage.session_id == db_session.id
        ).order_by(DesignSessionMessage.created_at).all()

        for msg in db_messages:
            messages.append({
                "role": msg.role.value,
                "content": msg.content,
            })

        # 3. 이전 이미지 분석 컨텍스트 주입
        context_query = text_query
        if image_thread_id:
            prev_session = db.query(DesignSession).filter(
                DesignSession.thread_id == image_thread_id
            ).first()

            if prev_session:
                # 이전 이미지 URL과 분석 결과를 컨텍스트에 추가
                s3_url = None
                if prev_session.images:
                    user_upload = next(
                        (img for img in prev_session.images
                         if img.image_type == ImageType.user_upload),
                        None
                    )
                    if user_upload:
                        s3_url = user_upload.s3_url

                context = f"""[이전 이미지 분석 컨텍스트]
- 이미지 URL: {s3_url or 'N/A'}
- 분석 결과: {prev_session.input_analysis or 'N/A'}
"""
                context_query = f"{context}\n\n사용자 질문: {text_query}"
                print(f"[design] 이미지 컨텍스트 주입: {image_thread_id}")

        initial_state = {
            "input_type": "",
            "image_path": "",
            "text_query": context_query,
            "user_query": context_query,
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

        answer = result.get("general_answer", "")

        # 4. RDS에 대화 히스토리 저장
        user_msg = DesignSessionMessage(
            session_id=db_session.id,
            role=MessageRole.user,
            content=text_query,  # 원본 질문 저장 (컨텍스트 제외)
        )
        db.add(user_msg)

        if answer:
            assistant_msg = DesignSessionMessage(
                session_id=db_session.id,
                role=MessageRole.assistant,
                content=answer,
            )
            db.add(assistant_msg)

        db_session.status = DesignSessionStatus.completed
        db.commit()

        # 인메모리 세션 업데이트 (호환성 유지)
        _sessions[text_thread_id] = {
            "messages": result.get("messages", []),
        }

        return {
            "success": True,
            "thread_id": thread_id,
            "answer": answer,
            "search_images": [],
        }
    except Exception as e:
        traceback.print_exc()
        return {"success": False, "error": f"디자인 분석 처리 중 오류: {str(e)}"}


# ══════════════════════════════════════════════════════
# GET /design/session/{thread_id} — 세션 히스토리 조회
# ══════════════════════════════════════════════════════

@router.get("/design/session/{thread_id}")
async def get_session_history(
    thread_id: str,
    db: Session = Depends(get_db),
):
    """세션 히스토리 조회 (페이지 새로고침 시 복원용)."""
    db_session = db.query(DesignSession).filter(
        DesignSession.thread_id == thread_id
    ).first()

    if not db_session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    # 이미지 정보
    images = []
    for img in db_session.images:
        images.append({
            "id": img.id,
            "image_type": img.image_type.value,
            "s3_url": img.s3_url,
            "original_filename": img.original_filename,
            "created_at": img.created_at.isoformat() if img.created_at else None,
        })

    # 대화 히스토리
    messages = []
    for msg in db_session.messages:
        messages.append({
            "id": msg.id,
            "role": msg.role.value,
            "content": msg.content,
            "created_at": msg.created_at.isoformat() if msg.created_at else None,
        })

    # comparison_results_json 처리
    comparison_results = db_session.comparison_results_json
    if isinstance(comparison_results, str):
        try:
            comparison_results = json.loads(comparison_results)
        except json.JSONDecodeError:
            comparison_results = []

    return {
        "success": True,
        "session": {
            "thread_id": db_session.thread_id,
            "status": db_session.status.value,
            "input_analysis": db_session.input_analysis,
            "similar_designs": comparison_results,  # base64 포함된 similar_designs 포맷
            "selected_index": db_session.selected_index,
            "final_report": db_session.final_report,
            "created_at": db_session.created_at.isoformat() + "+00:00" if db_session.created_at else None,
            "updated_at": db_session.updated_at.isoformat() + "+00:00" if db_session.updated_at else None,
        },
        "images": images,
        "messages": messages,
    }


# ══════════════════════════════════════════════════════
# GET /design/sessions — 세션 목록 조회 (사이드바용)
# ══════════════════════════════════════════════════════

@router.get("/design/sessions")
async def list_design_sessions(
    limit: int = 20,
    db: Session = Depends(get_db),
):
    """디자인 분석 세션 목록 조회 (사이드바용)."""
    sessions = (
        db.query(DesignSession)
        .filter(~DesignSession.thread_id.startswith("text-"))
        .order_by(DesignSession.created_at.desc())
        .limit(limit)
        .all()
    )

    result = []
    for s in sessions:
        # 유저 업로드 이미지 URL (사이드바 썸네일용)
        s3_url = None
        for img in s.images:
            if img.image_type == ImageType.user_upload:
                s3_url = img.s3_url
                break

        # 미리보기 텍스트: input_analysis 첫 줄
        preview = ""
        if s.input_analysis:
            preview = s.input_analysis.split('\n')[0][:60]

        result.append({
            "thread_id": s.thread_id,
            "status": s.status.value,
            "preview": preview,
            "s3_url": s3_url,
            "created_at": s.created_at.isoformat() + "+00:00" if s.created_at else None,
        })

    return result


# ══════════════════════════════════════════════════════
# DELETE /design/session/{thread_id} — 세션 삭제
# ══════════════════════════════════════════════════════

@router.patch("/design/session/{thread_id}")
async def rename_design_session(
    thread_id: str,
    data: dict,
    db: Session = Depends(get_db),
):
    """디자인 분석 세션 이름 변경."""
    db_session = db.query(DesignSession).filter(
        DesignSession.thread_id == thread_id
    ).first()
    if not db_session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    preview = data.get("preview", "").strip()
    if not preview:
        raise HTTPException(status_code=400, detail="이름을 입력해주세요.")
    db_session.input_analysis = preview
    db.commit()
    return {"success": True, "preview": preview}


@router.delete("/design/session/{thread_id}")
async def delete_design_session(
    thread_id: str,
    db: Session = Depends(get_db),
):
    """디자인 분석 세션 삭제 (cascade: 이미지·메시지 포함)."""
    db_session = db.query(DesignSession).filter(
        DesignSession.thread_id == thread_id
    ).first()

    if not db_session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    db.delete(db_session)
    db.commit()

    # 인메모리 세션도 제거
    _sessions.pop(thread_id, None)

    return {"success": True}

