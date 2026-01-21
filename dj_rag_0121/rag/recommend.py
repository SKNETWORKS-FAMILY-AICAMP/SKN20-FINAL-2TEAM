"""
패션 코디 추천 시스템 핵심 로직
"""

import base64
from pathlib import Path
from dataclasses import dataclass
from openai import OpenAI
import chromadb

from config import (
    OPENAI_API_KEY,
    CHROMA_DB_DIR,
    VISION_MODEL,
    EMBEDDING_MODEL,
    COLLECTION_NAME,
    FASHION_ANALYSIS_PROMPT,
    TOP_K_RESULTS,
)


@dataclass
class RecommendationResult:
    """추천 결과 데이터 클래스"""
    celeb_id: str
    image_path: str
    description: str
    similarity_score: float


class FashionRecommender:
    """패션 코디 추천 시스템"""

    def __init__(self):
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY 환경 변수를 설정해주세요.")

        self.client = OpenAI(api_key=OPENAI_API_KEY)
        self.chroma_client = chromadb.PersistentClient(path=str(CHROMA_DB_DIR))

        try:
            self.collection = self.chroma_client.get_collection(name=COLLECTION_NAME)
        except Exception:
            raise ValueError(
                f"'{COLLECTION_NAME}' 컬렉션이 없습니다. "
                "먼저 embed_celeb_fashion.py를 실행해주세요."
            )

    def _encode_image_to_base64(self, image_path: str) -> str:
        """이미지를 base64로 인코딩"""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def _get_image_extension(self, image_path: str) -> str:
        """이미지 확장자에 따른 MIME 타입 반환"""
        ext = Path(image_path).suffix.lower()
        mime_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        return mime_types.get(ext, "image/jpeg")

    def analyze_user_fashion(self, image_path: str) -> str:
        """사용자 이미지에서 패션 특성 추출"""
        base64_image = self._encode_image_to_base64(image_path)
        mime_type = self._get_image_extension(image_path)

        response = self.client.chat.completions.create(
            model=VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": FASHION_ANALYSIS_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{base64_image}",
                                "detail": "high"
                            },
                        },
                    ],
                }
            ],
            max_tokens=1000,
        )

        return response.choices[0].message.content

    def get_embedding(self, text: str) -> list[float]:
        """텍스트를 벡터로 임베딩"""
        response = self.client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text
        )
        return response.data[0].embedding

    def find_similar_fashion(
        self,
        image_path: str,
        top_k: int = TOP_K_RESULTS
    ) -> tuple[str, list[RecommendationResult]]:
        """
        사용자 이미지와 유사한 셀럽 코디 찾기

        Returns:
            tuple: (사용자 이미지 분석 결과, 추천 결과 리스트)
        """
        # 1. 사용자 이미지 분석
        user_fashion_desc = self.analyze_user_fashion(image_path)

        # 2. 텍스트 임베딩
        user_embedding = self.get_embedding(user_fashion_desc)

        # 3. 유사한 코디 검색
        results = self.collection.query(
            query_embeddings=[user_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"]
        )

        # 4. 결과 정리
        recommendations = []
        for i in range(len(results["ids"][0])):
            # ChromaDB의 distance를 유사도 점수로 변환 (거리가 작을수록 유사)
            distance = results["distances"][0][i]
            similarity = 1 / (1 + distance)  # 0~1 범위로 정규화

            rec = RecommendationResult(
                celeb_id=results["ids"][0][i],
                image_path=results["metadatas"][0][i]["filepath"],
                description=results["documents"][0][i],
                similarity_score=similarity
            )
            recommendations.append(rec)

        return user_fashion_desc, recommendations

    def generate_recommendation_text(
        self,
        user_desc: str,
        recommendations: list[RecommendationResult]
    ) -> str:
        """추천 결과를 자연스러운 텍스트로 생성"""
        if not recommendations:
            return "유사한 코디를 찾을 수 없습니다."

        rec_texts = []
        for i, rec in enumerate(recommendations, 1):
            rec_texts.append(
                f"{i}. {rec.celeb_id} (유사도: {rec.similarity_score:.1%})\n"
                f"   스타일: {rec.description[:200]}..."
            )

        prompt = f"""사용자의 패션:
{user_desc}

유사한 셀럽 코디:
{chr(10).join(rec_texts)}

위 정보를 바탕으로 사용자에게 친근하게 코디 추천 메시지를 작성해주세요.
왜 이 코디들이 유사한지, 어떤 점을 참고하면 좋을지 간단히 설명해주세요."""

        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
        )

        return response.choices[0].message.content


# 테스트용 코드
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python recommend.py <image_path>")
        sys.exit(1)

    image_path = sys.argv[1]

    recommender = FashionRecommender()
    user_desc, recommendations = recommender.find_similar_fashion(image_path)

    print("\n" + "=" * 50)
    print("내 옷 분석 결과:")
    print("=" * 50)
    print(user_desc)

    print("\n" + "=" * 50)
    print("추천 셀럽 코디:")
    print("=" * 50)
    for rec in recommendations:
        print(f"\n{rec.celeb_id} (유사도: {rec.similarity_score:.1%})")
        print(f"이미지: {rec.image_path}")
        print(f"설명: {rec.description[:200]}...")
