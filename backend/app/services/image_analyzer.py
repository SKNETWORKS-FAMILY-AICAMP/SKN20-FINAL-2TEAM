"""이미지 분석 서비스 — design.py 라우터의 ChromaDB CLIP 파이프라인으로 대체됨.

이 모듈은 하위 호환성을 위해 유지되지만, 실제 분석은
backend/app/routers/design.py로 수행됩니다.

DesignAnalysisService: design/src/api.py(port 8001)로 프록시하는 서비스.
"""

import httpx

from app.config import settings


class ImageAnalyzerService:
    """이미지 분석 서비스 (레거시 — 사용 안 됨)"""

    def __init__(self, db=None):
        self.db = db

    async def analyze(self, message_id: int, file=None):
        raise NotImplementedError(
            "ImageAnalyzerService는 design.py 라우터로 대체되었습니다."
        )

    async def analyze_url(self, message_id: int, image_url: str, description=None):
        raise NotImplementedError(
            "ImageAnalyzerService는 design.py 라우터로 대체되었습니다."
        )


class DesignAnalysisService:
    """디자인 분석 프록시 서비스.

    design/src/api.py (CLIP + ChromaDB + VLM) 서비스로 요청을 전달합니다.
    실행 전 design 서비스가 port 8001에서 돌고 있어야 합니다:
        cd design/src && uvicorn api:app --port 8001
    """

    @staticmethod
    async def analyze_image(
        file_content: bytes, filename: str, content_type: str, user_query: str
    ) -> dict:
        """1단계: 이미지 업로드 → 유사 디자인 10개 반환"""
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.DESIGN_SERVICE_TIMEOUT)
        ) as client:
            response = await client.post(
                f"{settings.DESIGN_SERVICE_URL}/chat/image",
                files={"image": (filename, file_content, content_type or "image/jpeg")},
                data={"user_query": user_query},
            )
            response.raise_for_status()
            return response.json()

    @staticmethod
    async def select_design(thread_id: str, selected_index: int) -> dict:
        """2단계: 디자인 선택 → 상세비교 + 리포트 반환"""
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.DESIGN_SERVICE_TIMEOUT)
        ) as client:
            response = await client.post(
                f"{settings.DESIGN_SERVICE_URL}/chat/select",
                data={"thread_id": thread_id, "selected_index": str(selected_index)},
            )
            response.raise_for_status()
            return response.json()

    @staticmethod
    async def text_query(
        text_query: str, thread_id: str = None, image_thread_id: str = None
    ) -> dict:
        """텍스트 질문 → LLM + Tools 답변"""
        data = {"text_query": text_query}
        if thread_id:
            data["thread_id"] = thread_id
        if image_thread_id:
            data["image_thread_id"] = image_thread_id

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(settings.DESIGN_SERVICE_TIMEOUT)
        ) as client:
            response = await client.post(
                f"{settings.DESIGN_SERVICE_URL}/chat/text",
                data=data,
            )
            response.raise_for_status()
            return response.json()
