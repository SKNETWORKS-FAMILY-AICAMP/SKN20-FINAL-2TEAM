"""텍스트 분석 서비스 — chat.py의 RAG 파이프라인으로 대체됨.

이 모듈은 하위 호환성을 위해 유지되지만, 실제 분석은
backend/app/routers/chat.py → rag.backend_adapter.analyze_product() 로 수행됩니다.
"""


class TextAnalyzerService:
    """텍스트 분석 서비스 (레거시 — 사용 안 됨)"""

    def __init__(self, db=None):
        self.db = db

    def analyze(self, message_id: int, product_description: str):
        raise NotImplementedError(
            "TextAnalyzerService는 RAG 파이프라인으로 대체되었습니다. "
            "chat.py의 send_chat_message()를 사용하세요."
        )
