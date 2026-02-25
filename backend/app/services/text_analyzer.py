import time
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import text
from huggingface_hub import InferenceClient

from app.models.analysis import Analysis, AnalysisKeyword, ClaimMatch, InputTypeEnum, RiskLevelEnum, MatchResultEnum
from app.models.patent import Claim, Patent
from app.config import settings


# HuggingFace 모델 ID (Inference API 지원 모델)
HF_MODELS = {
    "llama-3b": "meta-llama/Llama-3.2-3B-Instruct",
    "mistral-7b": "mistralai/Mistral-7B-Instruct-v0.3",
    "default": "meta-llama/Llama-3.2-3B-Instruct",
}


class TextAnalyzerService:
    """
    텍스트 분석 서비스

    플로우:
    1. 키워드 추출 (형태소 분석)
    2. Pre-filter (claim_keywords에서 매칭)
    3. 청구항 RAG 검색 (BM25 + Dense)
    4. sLLM 분석 (HuggingFace API)
    """

    def __init__(self, db: Session):
        self.db = db
        self.hf_client = None
        self.model_id = HF_MODELS.get("14b")  # 기본값: 14B 모델

    def _get_hf_client(self) -> InferenceClient:
        """HuggingFace 클라이언트 (lazy loading)"""
        if self.hf_client is None:
            self.hf_client = InferenceClient(token=settings.HF_TOKEN)
        return self.hf_client

    def analyze(self, message_id: int, product_description: str) -> Analysis:
        """텍스트 분석 수행"""
        start_time = time.time()

        # 1. 키워드 추출
        keywords = self._extract_keywords(product_description)

        # 2. Pre-filter: claim_keywords에서 매칭되는 patent_id 추출
        patent_ids = self._prefilter_patents(keywords)

        # 3. 청구항 검색 (필터된 특허 내에서)
        candidate_claims = self._search_claims(keywords, patent_ids)

        # 4. sLLM 분석
        result = self._analyze_with_sllm(product_description, candidate_claims)

        processing_time = int((time.time() - start_time) * 1000)

        # 분석 결과 저장
        analysis = Analysis(
            message_id=message_id,
            input_type=InputTypeEnum.text,
            risk_level=RiskLevelEnum(result.get("risk_level", "low")),
            result_json=result,
            model_used=self.model_id,
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
        for rank, claim_data in enumerate(candidate_claims[:10], 1):
            match_result = result.get("label", "uncertain")
            if match_result == "침해":
                match_result = "match"
            elif match_result == "비침해":
                match_result = "no_match"
            else:
                match_result = "uncertain"

            claim_match = ClaimMatch(
                analysis_id=analysis.id,
                claim_id=claim_data.get("claim_id"),
                rag_score=claim_data.get("rag_score"),
                rerank_score=claim_data.get("rerank_score"),
                match_result=MatchResultEnum(match_result),
                rank=rank
            )
            self.db.add(claim_match)

        self.db.commit()
        self.db.refresh(analysis)

        return analysis

    def _extract_keywords(self, text: str) -> List[Dict[str, Any]]:
        """키워드 추출 (단순 토큰화)"""
        # TODO: kiwipiepy 형태소 분석으로 개선 가능
        words = text.replace(",", " ").replace(".", " ").replace("(", " ").replace(")", " ").split()
        keywords = []
        seen = set()

        for word in words:
            word = word.strip()
            if len(word) > 1 and word not in seen:
                seen.add(word)
                keywords.append({
                    "keyword": word,
                    "importance": 1.0
                })

        return keywords[:20]  # 최대 20개

    def _prefilter_patents(self, keywords: List[Dict[str, Any]], limit: int = 1000) -> List[str]:
        """
        Pre-filter: claim_keywords 테이블에서 매칭되는 patent_id 추출

        Args:
            keywords: 추출된 키워드 목록
            limit: 최대 특허 수

        Returns:
            매칭된 patent_id 목록
        """
        if not keywords:
            return []

        keyword_list = [kw["keyword"] for kw in keywords]

        # claim_keywords 테이블에서 매칭 검색
        query = text("""
            SELECT DISTINCT patent_id, COUNT(*) as match_count
            FROM claim_keywords
            WHERE keyword IN :keywords
            GROUP BY patent_id
            ORDER BY match_count DESC
            LIMIT :limit
        """)

        result = self.db.execute(query, {"keywords": tuple(keyword_list), "limit": limit})
        patent_ids = [row[0] for row in result.fetchall()]

        return patent_ids

    def _search_claims(
        self,
        keywords: List[Dict[str, Any]],
        patent_ids: List[str],
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        청구항 검색 (필터된 특허 내에서)

        Args:
            keywords: 키워드 목록
            patent_ids: Pre-filter된 patent_id 목록
            limit: 반환할 청구항 수

        Returns:
            청구항 정보 목록
        """
        if not patent_ids:
            # Pre-filter 결과가 없으면 전체에서 검색
            claims = self.db.query(Claim).join(Patent).limit(limit).all()
        else:
            # 필터된 특허 내에서 검색
            claims = (
                self.db.query(Claim)
                .join(Patent)
                .filter(Patent.application_num.in_(patent_ids[:100]))  # 상위 100개 특허
                .limit(limit)
                .all()
            )

        results = []
        for claim in claims:
            # 구성요소 가져오기
            component = self.db.execute(
                text("SELECT components FROM claim_components WHERE chunk_id = :chunk_id"),
                {"chunk_id": f"{claim.patent.application_num}_claim_{claim.claim_number}"}
            ).fetchone()

            results.append({
                "claim_id": claim.id,
                "patent_id": claim.patent.application_num,
                "patent_title": claim.patent.title,
                "claim_number": claim.claim_number,
                "claim_text": claim.claim_text,
                "components": component[0] if component else "",
                "rag_score": 0.8,
                "rerank_score": 0.8
            })

        return results

    def _analyze_with_sllm(
        self,
        product_description: str,
        claims: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        sLLM으로 특허 침해 분석 (HuggingFace API 호출)

        Args:
            product_description: 사용자 제품 설명
            claims: 후보 청구항 목록

        Returns:
            분석 결과
        """
        if not claims:
            return {
                "patent_id": "",
                "label": "비침해",
                "risk_level": "low",
                "decision_reason": "비교할 특허 청구항을 찾지 못했습니다.",
                "comparisons": []
            }

        # 첫 번째 청구항과 비교
        top_claim = claims[0]

        prompt = self._build_prompt(
            product_description,
            top_claim.get("claim_text", ""),
            top_claim.get("components", "")
        )

        try:
            client = self._get_hf_client()
            response = client.text_generation(
                prompt,
                model=self.model_id,
                max_new_tokens=1024,
                temperature=0.1,
                do_sample=True,
            )

            result = self._parse_response(response, top_claim)
            result["analyzed_claims"] = [
                {
                    "patent_id": c.get("patent_id"),
                    "claim_number": c.get("claim_number"),
                    "patent_title": c.get("patent_title")
                }
                for c in claims
            ]
            return result

        except Exception as e:
            # API 호출 실패 시 기본 응답
            return {
                "patent_id": top_claim.get("patent_id", ""),
                "label": "애매",
                "risk_level": "medium",
                "decision_reason": f"분석 중 오류 발생: {str(e)}. 전문가 검토가 필요합니다.",
                "comparisons": [],
                "error": str(e)
            }

    def _build_prompt(self, user_product: str, claim_text: str, components: str) -> str:
        """분석용 프롬프트 생성"""
        prompt = f"""당신은 특허 침해 분석 전문가입니다. 사용자 제품이 특허 청구항을 침해하는지 분석해주세요.

## 사용자 제품
{user_product}

## 특허 청구항
{claim_text}

## 청구항 구성요소
{components}

## 분석 지침
1. 각 구성요소별로 사용자 제품과 대응 여부를 분석하세요.
2. 모든 구성요소가 대응되면 "침해", 일부만 대응되면 "애매", 대응되지 않으면 "비침해"로 판단하세요.
3. 전문가 검토가 필요한 경우 "침해_전문가"로 판단하세요.

## 응답 형식
◆구성 대비◆
| 번호 | 특허 구성요소 | 사용자 제품 대응 | 대응 여부 |
|-----|-------------|----------------|----------|
| 1 | ... | ... | O/X/△ |

◆판단◆
[상세 판단 근거]

◆결론◆
[침해/비침해/애매/침해_전문가]
"""
        return prompt

    def _parse_response(self, response: str, claim: Dict[str, Any]) -> Dict[str, Any]:
        """응답 파싱"""
        # 결론 추출
        label = "애매"
        if "◆결론◆" in response:
            conclusion = response.split("◆결론◆")[-1].strip()
            if "비침해" in conclusion:
                label = "비침해"
            elif "침해_전문가" in conclusion:
                label = "침해_전문가"
            elif "침해" in conclusion:
                label = "침해"
            elif "애매" in conclusion:
                label = "애매"

        # 리스크 레벨 매핑
        risk_map = {
            "침해": "high",
            "침해_전문가": "high",
            "애매": "medium",
            "비침해": "low"
        }

        return {
            "patent_id": claim.get("patent_id", ""),
            "patent_title": claim.get("patent_title", ""),
            "claim_number": claim.get("claim_number", 1),
            "label": label,
            "risk_level": risk_map.get(label, "medium"),
            "decision_reason": response,
            "raw_response": response
        }
