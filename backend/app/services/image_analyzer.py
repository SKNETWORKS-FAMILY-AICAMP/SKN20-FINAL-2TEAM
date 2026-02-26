"""이미지 분석 서비스 — design.py 라우터의 ChromaDB CLIP 파이프라인으로 대체됨.

이 모듈은 하위 호환성을 위해 유지되지만, 실제 분석은
backend/app/routers/design.py로 수행됩니다.
"""


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
