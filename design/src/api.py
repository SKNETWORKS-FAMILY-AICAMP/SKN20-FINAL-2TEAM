"""
디자인 유사성 분석 챗봇 - API 서버

엔드포인트:
- POST /chat/image    : 이미지 업로드 → 유사 디자인 10개 반환 (1단계)
- POST /chat/select   : 디자인 선택 → 상세비교 + 리포트 반환 (2단계)
- POST /chat/text     : 텍스트 질문 → LLM + Tools 답변
- GET  /health        : 서버 상태 확인

실행: python api.py
"""

import os
import uuid
import base64

from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import uvicorn

from langgraph.types import Command

# design_chatbot_v3에서 그래프와 유틸 가져오기
from design_chatbot import graph, design_id_to_local_image


# ==================== FastAPI 초기화 ====================

app = FastAPI(
    title="디자인 유사성 분석 챗봇",
    description="이미지/텍스트 기반 디자인 FTO 분석 API",
    version="1.0.0"
)

# CORS 미들웨어 설정 
# 브라우저에서 이 API 호출시 교차 출처 요청(Cross-Origin, CORS) 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # 모든 도메인에서 접근 허용
    allow_methods=["*"], 
    allow_headers=["*"],
)

# ./temp_uploads : 사용자가 업로드한 이미지를 임시 저장하는 폴더
UPLOAD_DIR = "./temp_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)



# ==================== API 엔드포인트 ====================

@app.post("/chat/image")
async def chat_image(
    image: UploadFile = File(...),
    user_query: str = Form("이 제품과 유사한 디자인을 분석해줘")
):
    """
    1단계: 이미지 업로드 → 유사 디자인 10개 반환

    interrupt에서 멈추고, 유사 디자인 목록 + thread_id를 반환.
    사용자가 선택 후 /chat/select로 2단계 요청.
    """
    try:
        # 사용자가 입력한 이미지 저장
        image_path = os.path.join(UPLOAD_DIR, image.filename)
        contents = await image.read()
        with open(image_path, "wb") as f:
            f.write(contents)

        # 이미지 유효성 검증
        try:
            img = Image.open(image_path)
            img.verify()
        except Exception:
            raise HTTPException(status_code=400, detail="유효하지 않은 이미지입니다.")

        # 세션 ID 생성 (interrupt 재개용)
        thread_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}

        # 초기 상태
        initial_state = {
            "input_type": "",
            "image_path": image_path,
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
        }

        # 그래프 실행 → show_results_node의 interrupt에서 멈춤
        result = graph.invoke(initial_state, config)

        # 유사 디자인 목록 구성 (이미지 base64 포함)
        similar_designs = []
        for comp in result.get('comparison_results', []):
            # 이미지를 base64로 인코딩
            image_base64 = None
            if comp.get('image_path') and os.path.exists(comp['image_path']):
                try:
                    with open(comp['image_path'], 'rb') as f:
                        image_base64 = base64.b64encode(f.read()).decode('utf-8')
                except Exception:
                    pass

            similar_designs.append({
                "index": comp['index'],
                "application_number": comp['application_number'],
                "article_name": comp['article_name'],
                "admst_stat": comp['admst_stat'],
                "distance": comp['distance'],
                "image_base64": image_base64,
            })

        return JSONResponse(content={
            "success": True,
            "thread_id": thread_id,  # 2단계에서 필요
            "input_analysis": result.get('input_analysis', ''),
            "similar_designs": similar_designs,
            "message": "상세 비교할 디자인 번호를 선택하세요 (POST /chat/select)"
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
    """
    2단계: 디자인 선택 → 상세비교 + 리포트 반환

    /chat/image에서 받은 thread_id & 선택 번호를 전달하면,
    interrupt 이후 그래프가 재개되어 상세비교 → 리포트 생성.
    """
    try:
        config = {"configurable": {"thread_id": thread_id}}

        # interrupt 재개: 선택한 번호 전달
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
    text_query: str = Form(...)
):
    """
    텍스트 질문 → LLM + Tools(웹검색, DB검색) 답변

    interrupt 없이 한 번에 완료.
    """
    try:
        thread_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}

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
        }

        result = graph.invoke(initial_state, config)

        return JSONResponse(content={
            "success": True,
            "answer": result.get('general_answer', ''),
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"답변 중 오류: {str(e)}")


@app.get("/health")
async def health():
    """서버 상태 확인"""
    return {"status": "healthy", "service": "디자인 챗봇 v3"}


# ==================== 서버 실행 ====================

if __name__ == "__main__":
    print("=" * 60)
    print("디자인 유사성 분석 챗봇 v3 API 서버")
    print("=" * 60)
    print("웹 인터페이스: http://localhost:8000")
    print("API 문서:      http://localhost:8000/docs")
    print("=" * 60)

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
