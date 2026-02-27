import time
import os
import uuid
import httpx
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from fastapi import UploadFile

from app.models.analysis import Analysis, AnalysisImage, ImageMatch, InputTypeEnum, RiskLevelEnum
from app.models.patent import DesignPatent
# TODO: 디자인 팀 연동 후 활성화
# from app.models.patent import DesignEmbedding
from app.config import settings


class ImageAnalyzerService:
    """
    이미지 분석 서비스

    플로우:
    1. 이미지 저장
    2. 로카르노 분류 (자동)
    3. 이미지 RAG (Top 20)
    4. 유사도 모델 검증
    5. LLM 답변
    """

    def __init__(self, db: Session):
        self.db = db
        self.locarno_model = None  # 로카르노 분류 모델
        self.similarity_model = None  # 유사도 모델

    async def analyze(self, message_id: int, file: UploadFile) -> Analysis:
        """이미지 분석 수행"""
        start_time = time.time()

        # 1. 이미지 저장
        file_path, file_name = await self._save_image(file)

        # 2. 로카르노 분류
        locarno_class = self._classify_locarno(file_path)

        # 3. 이미지 RAG 검색
        candidate_patents = self._search_design_patents(locarno_class)

        # 4. 유사도 모델로 검증
        similar_patents = self._check_similarity(file_path, candidate_patents)

        # 5. LLM 응답 생성
        result = self._generate_response(similar_patents)

        processing_time = int((time.time() - start_time) * 1000)

        # 분석 결과 저장
        analysis = Analysis(
            message_id=message_id,
            input_type=InputTypeEnum.image,
            risk_level=RiskLevelEnum(result.get("risk_level", "low")),
            result_json=result,
            model_used="image_similarity_model",
            processing_time_ms=processing_time
        )

        self.db.add(analysis)
        self.db.flush()

        # 이미지 정보 저장
        analysis_image = AnalysisImage(
            analysis_id=analysis.id,
            file_path=file_path,
            file_name=file_name,
            locarno_class=locarno_class
        )
        self.db.add(analysis_image)

        # 이미지 매칭 결과 저장
        for rank, patent_data in enumerate(similar_patents[:10], 1):
            image_match = ImageMatch(
                analysis_id=analysis.id,
                design_patent_id=patent_data["design_patent_id"],
                rag_score=patent_data.get("rag_score"),
                model_score=patent_data.get("model_score"),
                is_similar=patent_data.get("is_similar", False),
                rank=rank
            )
            self.db.add(image_match)

        self.db.commit()
        self.db.refresh(analysis)

        return analysis

    async def analyze_url(
        self,
        message_id: int,
        image_url: str,
        description: Optional[str] = None
    ) -> Analysis:
        """URL 기반 이미지 분석 수행"""
        start_time = time.time()

        # 1. URL에서 이미지 다운로드
        file_path, file_name = await self._download_image(image_url)

        # 2. 로카르노 분류
        locarno_class = self._classify_locarno(file_path)

        # 3. 이미지 RAG 검색
        candidate_patents = self._search_design_patents(locarno_class)

        # 4. 유사도 모델로 검증
        similar_patents = self._check_similarity(file_path, candidate_patents)

        # 5. LLM 응답 생성
        result = self._generate_response(similar_patents)

        processing_time = int((time.time() - start_time) * 1000)

        # 분석 결과 저장
        analysis = Analysis(
            message_id=message_id,
            input_type=InputTypeEnum.image,
            risk_level=RiskLevelEnum(result.get("risk_level", "low")),
            result_json=result,
            model_used="image_similarity_model",
            processing_time_ms=processing_time
        )

        self.db.add(analysis)
        self.db.flush()

        # 이미지 정보 저장
        analysis_image = AnalysisImage(
            analysis_id=analysis.id,
            file_path=file_path,
            file_name=file_name,
            locarno_class=locarno_class
        )
        self.db.add(analysis_image)

        # 이미지 매칭 결과 저장 (특허 데이터가 있는 경우에만)
        for rank, patent_data in enumerate(similar_patents[:10], 1):
            if "design_patent_id" in patent_data:
                image_match = ImageMatch(
                    analysis_id=analysis.id,
                    design_patent_id=patent_data["design_patent_id"],
                    rag_score=patent_data.get("rag_score"),
                    model_score=patent_data.get("model_score"),
                    is_similar=patent_data.get("is_similar", False),
                    rank=rank
                )
                self.db.add(image_match)

        self.db.commit()
        self.db.refresh(analysis)

        return analysis

    async def _download_image(self, image_url: str) -> tuple[str, str]:
        """URL에서 이미지 다운로드"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(image_url, timeout=30.0)
                response.raise_for_status()

                # 파일 확장자 추출
                content_type = response.headers.get("content-type", "")
                ext_map = {
                    "image/jpeg": "jpg",
                    "image/png": "png",
                    "image/gif": "gif",
                    "image/webp": "webp"
                }
                file_ext = ext_map.get(content_type, "jpg")

                # 고유 파일명 생성
                unique_name = f"{uuid.uuid4()}.{file_ext}"
                file_path = os.path.join(settings.UPLOAD_DIR, unique_name)

                # 파일 저장
                with open(file_path, "wb") as f:
                    f.write(response.content)

                return file_path, unique_name
        except Exception as e:
            # 다운로드 실패 시 임시 경로 반환
            return "", f"download_failed_{uuid.uuid4()}"

    async def _save_image(self, file: UploadFile) -> tuple[str, str]:
        """이미지 파일 저장"""
        # 고유 파일명 생성
        file_ext = file.filename.split(".")[-1] if file.filename else "jpg"
        unique_name = f"{uuid.uuid4()}.{file_ext}"
        file_path = os.path.join(settings.UPLOAD_DIR, unique_name)

        # 파일 저장
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)

        return file_path, file.filename or unique_name

    def _classify_locarno(self, image_path: str) -> Optional[str]:
        """
        로카르노 분류

        TODO: 로카르노 분류 모델 구현
        - 이미지 → 로카르노 클래스 분류
        """
        # 임시 구현
        return "99-00"  # 기타 분류

    def _search_design_patents(self, locarno_class: Optional[str]) -> List[Dict[str, Any]]:
        """
        이미지 RAG 검색

        TODO: 실제 벡터 검색 구현
        - 같은 로카르노 클래스 필터링
        - CLIP 임베딩 유사도 검색
        """
        query = self.db.query(DesignPatent)

        if locarno_class:
            query = query.filter(DesignPatent.locarno_class == locarno_class)

        patents = query.limit(20).all()

        results = []
        for patent in patents:
            results.append({
                "design_patent_id": patent.id,
                "regit_num": patent.regit_num,
                "title": patent.title,
                "locarno_class": patent.locarno_class,
                "image_path": patent.image_path,
                "rag_score": 0.7,  # 임시 점수
                "is_similar": False
            })

        return results

    def _check_similarity(
        self,
        query_image_path: str,
        candidates: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        유사도 모델로 검증

        TODO: 학습된 유사도 모델 구현
        - 이미지 쌍 비교
        - 유사도 점수 계산
        - 임계값 기준 is_similar 판정
        """
        # 임시 구현: 기존 점수 유지
        for candidate in candidates:
            candidate["model_score"] = candidate.get("rag_score", 0.5)
            candidate["is_similar"] = candidate["model_score"] > 0.8

        return sorted(candidates, key=lambda x: x.get("model_score", 0), reverse=True)

    def _generate_response(self, similar_patents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        LLM 응답 생성

        TODO: 실제 LLM 응답 생성 구현
        """
        similar_count = sum(1 for p in similar_patents if p.get("is_similar"))

        if similar_count == 0:
            risk_level = "low"
            response = "유사한 디자인 특허를 찾지 못했습니다. 해당 디자인은 특허 침해 가능성이 낮습니다."
        elif similar_count <= 2:
            risk_level = "medium"
            response = f"유사한 디자인 특허 {similar_count}건이 발견되었습니다. 상세 검토가 필요합니다."
        else:
            risk_level = "high"
            response = f"유사한 디자인 특허 {similar_count}건이 발견되었습니다. 특허 침해 가능성이 높으니 전문가 상담을 권장합니다."

        return {
            "risk_level": risk_level,
            "similar_count": similar_count,
            "response": response,
            "similar_patents": [
                {
                    "regit_num": p["regit_num"],
                    "title": p["title"],
                    "similarity_score": p.get("model_score", 0)
                }
                for p in similar_patents[:5] if p.get("is_similar")
            ]
        }


class DesignAnalysisService:
    """
    디자인 분석 프록시 서비스

    design/src/api.py (CLIP + ChromaDB + VLM) 서비스로 요청을 전달합니다.
    실행 전 design 서비스가 port 8001에서 돌고 있어야 합니다:
        cd design/src && python api.py  (uvicorn port=8001)
    """

    @staticmethod
    async def analyze_image(file_content: bytes, filename: str, content_type: str, user_query: str) -> dict:
        """1단계: 이미지 업로드 → 유사 디자인 10개 반환"""
        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.DESIGN_SERVICE_TIMEOUT)) as client:
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
        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.DESIGN_SERVICE_TIMEOUT)) as client:
            response = await client.post(
                f"{settings.DESIGN_SERVICE_URL}/chat/select",
                data={"thread_id": thread_id, "selected_index": str(selected_index)},
            )
            response.raise_for_status()
            return response.json()

    @staticmethod
    async def text_query(text_query: str, thread_id: str = None, image_thread_id: str = None) -> dict:
        """텍스트 질문 → LLM + Tools 답변"""
        data = {"text_query": text_query}
        if thread_id:
            data["thread_id"] = thread_id
        if image_thread_id:
            data["image_thread_id"] = image_thread_id

        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.DESIGN_SERVICE_TIMEOUT)) as client:
            response = await client.post(
                f"{settings.DESIGN_SERVICE_URL}/chat/text",
                data=data,
            )
            response.raise_for_status()
            return response.json()
