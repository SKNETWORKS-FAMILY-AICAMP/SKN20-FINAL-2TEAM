import time
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from app.models.analysis import Analysis, AnalysisKeyword, ClaimMatch, InputTypeEnum, RiskLevelEnum, MatchResultEnum
from app.models.patent import Claim, Patent
# TODO: RAG 팀 연동 후 활성화
# from app.models.patent import ClaimEmbedding
from app.config import settings


class TextAnalyzerService:
    """
    텍스트 분석 서비스

    플로우:
    1. 키워드 추출
    2. 청구항 RAG 검색
    3. Rerank
    4. sLLM 분석
    """

    def __init__(self, db: Session):
        self.db = db
        self.model = None  # sLLM 모델 (lazy loading)

    def analyze(self, message_id: int, product_description: str) -> Analysis:
        """텍스트 분석 수행"""
        start_time = time.time()

        # 1. 키워드 추출
        keywords = self._extract_keywords(product_description)

        # 2. 청구항 RAG 검색
        candidate_claims = self._search_claims(keywords)

        # 3. Rerank (추후 구현)
        reranked_claims = self._rerank_claims(product_description, candidate_claims)

        # 4. sLLM 분석
        result = self._analyze_with_sllm(product_description, reranked_claims)

        processing_time = int((time.time() - start_time) * 1000)

        # 분석 결과 저장
        analysis = Analysis(
            message_id=message_id,
            input_type=InputTypeEnum.text,
            risk_level=RiskLevelEnum(result.get("risk_level", "low")),
            result_json=result,
            model_used=settings.SLLM_MODEL_PATH,
            processing_time_ms=processing_time
        )

        self.db.add(analysis)
        self.db.flush()

        # 키워드 저장
        for kw in keywords:
            keyword_obj = AnalysisKeyword(
                analysis_id=analysis.id,
                keyword=kw["keyword"],
                importance=kw.get("importance", 1.0)
            )
            self.db.add(keyword_obj)

        # 청구항 매칭 결과 저장
        for rank, claim_data in enumerate(reranked_claims[:10], 1):
            claim_match = ClaimMatch(
                analysis_id=analysis.id,
                claim_id=claim_data["claim_id"],
                rag_score=claim_data.get("rag_score"),
                rerank_score=claim_data.get("rerank_score"),
                match_result=MatchResultEnum(claim_data.get("match_result", "uncertain")),
                rank=rank
            )
            self.db.add(claim_match)

        self.db.commit()
        self.db.refresh(analysis)

        return analysis

    def _extract_keywords(self, text: str) -> List[Dict[str, Any]]:
        """
        키워드 추출

        TODO: 실제 키워드 추출 로직 구현
        - 형태소 분석
        - 화학물질명 추출
        - 제품 유형 추출
        """
        # 임시 구현: 단순 분리
        words = text.replace(",", " ").replace(".", " ").split()
        keywords = []

        for word in words:
            if len(word) > 2:  # 2글자 이상만
                keywords.append({
                    "keyword": word,
                    "importance": 1.0
                })

        return keywords[:10]  # 최대 10개

    def _search_claims(self, keywords: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        청구항 RAG 검색

        TODO: 실제 벡터 검색 구현
        - 키워드 임베딩
        - pgvector 유사도 검색
        """
        # 임시 구현: 전체 청구항 반환 (실제로는 벡터 검색 필요)
        claims = (
            self.db.query(Claim)
            .join(Patent)
            .limit(20)
            .all()
        )

        results = []
        for claim in claims:
            results.append({
                "claim_id": claim.id,
                "patent_regit_num": claim.patent.regit_num,
                "claim_text": claim.claim_text,
                "rag_score": 0.8,  # 임시 점수
                "match_result": "uncertain"
            })

        return results

    def _rerank_claims(
        self,
        query: str,
        claims: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Reranker로 청구항 재정렬

        TODO: bge-reranker 구현
        """
        # 임시 구현: 기존 순서 유지
        for claim in claims:
            claim["rerank_score"] = claim.get("rag_score", 0.5)

        return sorted(claims, key=lambda x: x.get("rerank_score", 0), reverse=True)

    def _analyze_with_sllm(
        self,
        product_description: str,
        claims: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        sLLM으로 특허 침해 분석

        TODO: 실제 sLLM 추론 구현
        - Gemma 모델 로드
        - 프롬프트 구성
        - 추론 실행
        """
        if not claims:
            return {
                "regit_num": "",
                "comparisons": [],
                "risk_level": "low",
                "decision_reason": "비교할 특허 청구항을 찾지 못했습니다."
            }

        # 임시 구현: 첫 번째 청구항과 비교
        top_claim = claims[0]

        # 실제로는 sLLM이 생성해야 하는 결과
        result = {
            "regit_num": top_claim.get("patent_regit_num", ""),
            "comparisons": [
                {
                    "patent_element": "청구항 구성요소",
                    "user_product_element": product_description[:50],
                    "match": "판단불가"
                }
            ],
            "risk_level": "medium",
            "decision_reason": "sLLM 분석이 필요합니다. 현재는 임시 응답입니다."
        }

        return result

    def _load_model(self):
        """sLLM 모델 로드 (lazy loading)"""
        if self.model is None:
            # TODO: 실제 모델 로드 구현
            pass
