"""
디자인 유사성 분석 챗봇 API 서버 — GPT 전용 버전

원본: api.py
변경: design_chatbot_gpt에서 graph 임포트

실행: cd design/src && python api_gpt.py
"""

import os
import uuid
import base64
import requests

from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import uvicorn

from langgraph.types import Command

# ── 변경: GPT 버전에서 임포트 ──
from design_chatbot_gpt import graph


app = FastAPI(
    title="디자인 유사성 분석 챗봇 (GPT 버전)",
    description="이미지/텍스트 기반 디자인 FTO 분석 API (OpenAI GPT-4o-mini)",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "./temp_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.post("/chat/image")
async def chat_image(
    image: UploadFile = File(...),
    user_query: str = Form("이 제품과 유사한 디자인을 분석해줘")
):
    """1단계: 이미지 업로드 → 유사 디자인 10개 반환"""
    try:
        image_path = os.path.join(UPLOAD_DIR, image.filename)
        contents = await image.read()
        with open(image_path, "wb") as f:
            f.write(contents)

        try:
            img = Image.open(image_path)
            img.verify()
        except Exception:
            raise HTTPException(status_code=400, detail="유효하지 않은 이미지입니다.")

        thread_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}

        initial_state = {
            "input_type": "", "image_path": image_path,
            "text_query": "", "user_query": user_query,
            "base64_image": "", "input_analysis": "",
            "search_results": {}, "comparison_results": [],
            "selected_index": 0, "detailed_comparison": "",
            "final_report": "", "general_answer": "",
            "search_images": [], "messages": [],
        }

        result = graph.invoke(initial_state, config)

        similar_designs = []
        for comp in result.get('comparison_results', []):
            image_base64 = None
            img_path = comp.get('image_path', '')
            if img_path:
                try:
                    if img_path.startswith('http://') or img_path.startswith('https://'):
                        resp = requests.get(img_path, timeout=5)
                        if resp.status_code == 200:
                            image_base64 = base64.b64encode(resp.content).decode('utf-8')
                    elif os.path.exists(img_path):
                        with open(img_path, 'rb') as f:
                            image_base64 = base64.b64encode(f.read()).decode('utf-8')
                except Exception:
                    pass

            similar_designs.append({
                "index": comp['index'],
                "application_number": comp['application_number'],
                "article_name": comp['article_name'],
                "admst_stat": comp['admst_stat'],
                "distance": comp['hybrid_score'],
                "image_base64": image_base64,
            })

        return JSONResponse(content={
            "success": True,
            "thread_id": thread_id,
            "input_analysis": result.get('input_analysis', ''),
            "similar_designs": similar_designs,
        })

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"분석 중 오류: {str(e)}")


@app.post("/chat/select")
async def chat_select(
    thread_id: str = Form(...),
    selected_index: int = Form(...)
):
    """2단계: 디자인 선택 → 상세비교 + 리포트 반환"""
    try:
        config = {"configurable": {"thread_id": thread_id}}
        result = graph.invoke(Command(resume=str(selected_index)), config)
        return JSONResponse(content={
            "success": True,
            "detailed_comparison": result.get('detailed_comparison', ''),
            "final_report": result.get('final_report', ''),
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"분석 중 오류: {str(e)}")


@app.post("/chat/text")
async def chat_text(
    text_query: str = Form(...),
    thread_id: str = Form(None),
    image_thread_id: str = Form(None),
):
    """텍스트 질문 → LLM + Tools 답변"""
    try:
        is_new = thread_id is None
        thread_id = thread_id or str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}

        messages_history = []
        if not is_new:
            try:
                current = graph.get_state(config)
                messages_history = current.values.get('messages') or []
            except Exception:
                messages_history = []

        initial_state = {
            "input_type": "", "image_path": "",
            "text_query": text_query, "user_query": text_query,
            "base64_image": "", "input_analysis": "",
            "search_results": {}, "comparison_results": [],
            "selected_index": 0, "detailed_comparison": "",
            "final_report": "", "general_answer": "",
            "search_images": [], "messages": messages_history,
        }

        result = graph.invoke(initial_state, config)

        return JSONResponse(content={
            "success": True,
            "thread_id": thread_id,
            "answer": result.get('general_answer', ''),
            "search_images": [],
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"답변 중 오류: {str(e)}")


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "디자인 챗봇 GPT 버전"}


if __name__ == "__main__":
    print("=" * 60)
    print("디자인 유사성 분석 챗봇 API 서버 (GPT 버전)")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
