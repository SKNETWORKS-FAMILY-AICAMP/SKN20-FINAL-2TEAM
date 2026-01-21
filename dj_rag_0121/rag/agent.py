"""
LangGraph 기반 패션 코디 추천 Agent
Korean CLIP + LangChain Chroma 사용
"""

import open_clip
import torch
from PIL import Image
from pathlib import Path
from typing import TypedDict, Literal
import chromadb
from chromadb.config import Settings

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from config import (
    BASE_DIR,
    OPENAI_API_KEY,
    CHROMA_DB_DIR,
    CLIP_MODEL_NAME,
    CLIP_PRETRAINED,
    COLLECTION_NAME,
    RECOMMENDATION_PROMPT,
    TOP_K_RESULTS,
    DEVICE,
)


# ============================================================
# CLIP 임베딩 클래스 (싱글톤)
# ============================================================

class CLIPEmbedder:
    """Korean CLIP 임베딩 (싱글톤 패턴)"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        print(f"CLIP 모델 로딩 중... (Device: {DEVICE})")
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            CLIP_MODEL_NAME,
            pretrained=CLIP_PRETRAINED,
            device=DEVICE
        )
        self.model.eval()
        print("CLIP 모델 로딩 완료!")

    def embed_image(self, image_path: str) -> list[float]:
        """이미지를 벡터로 임베딩"""
        image = Image.open(image_path).convert("RGB")
        image_tensor = self.preprocess(image).unsqueeze(0).to(DEVICE)

        with torch.no_grad():
            image_features = self.model.encode_image(image_tensor)
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)

        return image_features.cpu().numpy().flatten().tolist()


# ============================================================
# State 정의
# ============================================================

class FashionAgentState(TypedDict):
    """Agent 상태 관리"""
    # 입력
    user_image_path: str

    # 중간 결과
    user_embedding: list[float]

    # 검색 결과
    recommendations: list[dict]

    # 최종 출력
    recommendation_message: str
    error: str | None


# ============================================================
# Graph 노드들
# ============================================================

def embed_image_node(state: FashionAgentState) -> FashionAgentState:
    """
    노드 1: 이미지 임베딩
    Korean CLIP으로 사용자 이미지를 벡터로 변환
    """
    try:
        image_path = state["user_image_path"]

        # CLIP 임베딩
        embedder = CLIPEmbedder()
        embedding = embedder.embed_image(image_path)

        state["user_embedding"] = embedding
        state["error"] = None

    except Exception as e:
        state["error"] = f"이미지 임베딩 실패: {str(e)}"

    return state


def search_similar_node(state: FashionAgentState) -> FashionAgentState:
    """
    노드 2: 유사 코디 검색
    LangChain Chroma에서 유사한 셀럽 코디 검색
    """
    if state.get("error"):
        return state

    try:
        # Chroma 클라이언트 연결
        client = chromadb.PersistentClient(
            path=str(CHROMA_DB_DIR),
            settings=Settings(anonymized_telemetry=False)
        )

        collection = client.get_collection(name=COLLECTION_NAME)

        # 유사도 검색
        results = collection.query(
            query_embeddings=[state["user_embedding"]],
            n_results=TOP_K_RESULTS,
            include=["documents", "metadatas", "distances"]
        )

        # 결과 정리
        recommendations = []
        for i in range(len(results["ids"][0])):
            distance = results["distances"][0][i]
            # 코사인 유사도로 변환 (거리가 작을수록 유사)
            similarity = 1 - (distance / 2)  # L2 거리를 유사도로 변환

            # 상대 경로를 절대 경로로 변환
            relative_path = results["metadatas"][0][i]["filepath"]
            absolute_path = str(BASE_DIR / relative_path)

            recommendations.append({
                "celeb_id": results["ids"][0][i],
                "image_path": absolute_path,
                "filename": results["metadatas"][0][i]["filename"],
                "similarity_score": max(0, min(1, similarity))
            })

        state["recommendations"] = recommendations

    except Exception as e:
        state["error"] = f"검색 실패: {str(e)}. embed_celeb_fashion.py를 먼저 실행하세요."

    return state


def generate_recommendation_node(state: FashionAgentState) -> FashionAgentState:
    """
    노드 3: 추천 메시지 생성
    GPT로 자연스러운 추천 메시지 생성
    """
    if state.get("error"):
        return state

    try:
        recommendations = state["recommendations"]

        if not recommendations:
            state["recommendation_message"] = "유사한 코디를 찾을 수 없습니다."
            return state

        # 추천 정보 텍스트로 정리
        rec_texts = []
        for i, rec in enumerate(recommendations, 1):
            rec_texts.append(
                f"{i}. {rec['celeb_id']} (유사도: {rec['similarity_score']:.1%})"
            )

        prompt = RECOMMENDATION_PROMPT.format(
            recommendations="\n".join(rec_texts)
        )

        llm = ChatOpenAI(
            model="gpt-4o-mini",
            api_key=OPENAI_API_KEY,
            max_tokens=800
        )

        response = llm.invoke([HumanMessage(content=prompt)])
        state["recommendation_message"] = response.content

    except Exception as e:
        # API 키 없어도 기본 메시지 제공
        rec_texts = []
        for i, rec in enumerate(state.get("recommendations", []), 1):
            rec_texts.append(f"{i}. {rec['celeb_id']} (유사도: {rec['similarity_score']:.1%})")

        state["recommendation_message"] = (
            "유사한 셀럽 코디를 찾았습니다:\n" + "\n".join(rec_texts)
        )

    return state


def should_continue(state: FashionAgentState) -> Literal["continue", "error"]:
    """에러 발생 시 중단, 아니면 계속"""
    if state.get("error"):
        return "error"
    return "continue"


# ============================================================
# Graph 생성
# ============================================================

def create_fashion_agent():
    """LangGraph 기반 패션 추천 Agent 생성"""

    workflow = StateGraph(FashionAgentState)

    # 노드 추가
    workflow.add_node("embed_image", embed_image_node)
    workflow.add_node("search_similar", search_similar_node)
    workflow.add_node("generate_recommendation", generate_recommendation_node)

    # 엣지 연결
    workflow.set_entry_point("embed_image")

    workflow.add_conditional_edges(
        "embed_image",
        should_continue,
        {"continue": "search_similar", "error": END}
    )

    workflow.add_conditional_edges(
        "search_similar",
        should_continue,
        {"continue": "generate_recommendation", "error": END}
    )

    workflow.add_edge("generate_recommendation", END)

    return workflow.compile()


# ============================================================
# Agent 클래스
# ============================================================

class FashionRecommendationAgent:
    """패션 추천 Agent 래퍼 클래스"""

    def __init__(self):
        self.agent = create_fashion_agent()

    def recommend(self, image_path: str) -> dict:
        """
        이미지 경로를 받아 추천 결과 반환

        Returns:
            dict: {
                "success": bool,
                "recommendations": list[dict],
                "recommendation_message": str,
                "error": str | None
            }
        """
        initial_state: FashionAgentState = {
            "user_image_path": image_path,
            "user_embedding": [],
            "recommendations": [],
            "recommendation_message": "",
            "error": None
        }

        final_state = self.agent.invoke(initial_state)

        return {
            "success": final_state.get("error") is None,
            "recommendations": final_state.get("recommendations", []),
            "recommendation_message": final_state.get("recommendation_message", ""),
            "error": final_state.get("error")
        }


# ============================================================
# 테스트
# ============================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python agent.py <image_path>")
        sys.exit(1)

    image_path = sys.argv[1]

    print("=" * 60)
    print("LangGraph 패션 추천 Agent (Korean CLIP)")
    print("=" * 60)

    agent = FashionRecommendationAgent()
    result = agent.recommend(image_path)

    if result["success"]:
        print("\n[추천 셀럽 코디]")
        for rec in result["recommendations"]:
            print(f"\n- {rec['celeb_id']} (유사도: {rec['similarity_score']:.1%})")
            print(f"  이미지: {rec['image_path']}")

        print("\n[AI 추천 메시지]")
        print(result["recommendation_message"])
    else:
        print(f"\n오류 발생: {result['error']}")
