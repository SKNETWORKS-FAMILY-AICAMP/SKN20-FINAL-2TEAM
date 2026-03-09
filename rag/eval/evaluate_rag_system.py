"""
LangGraph 기반 RAG 시스템

HuggingFace Weekly Papers 데이터를 기반으로 한 AI/ML/DL/LLM 논문 검색 및 답변 시스템
"""

import sys
from pathlib import Path
import json
import re
import hashlib
from typing import List, Dict, Any, Optional, Literal, Set

try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict

from dotenv import load_dotenv

from langchain_core.documents import Document
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser
from langchain_community.retrievers import BM25Retriever

from langgraph.graph import StateGraph, START, END

# 프롬프트 및 Query 확장 import
from .prompts import (
    TRANSLATION_PROMPT,
    AI_ML_CLASSIFICATION_PROMPT,
    ANSWER_GENERATION_PROMPT,
    expand_query_for_papers,
)

# VectorDB 로드 함수 import (상대 import 사용)
from ..utils.vectordb import load_vectordb

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()


# ===== GraphState 정의 =====
class GraphState(TypedDict):
    """LangGraph 상태 관리"""

    question: str
    original_question: str
    translated_question: Optional[str]
    is_korean: bool
    documents: List[Document]
    doc_scores: List[float]
    search_type: str
    relevance_level: str
    answer: str
    sources: List[Dict[str, Any]]
    is_ai_ml_related: bool
    _vectorstore: Any
    _llm: Any
    _bm25_retriever: Any


# ===== Helper Functions =====
def get_doc_hash_key(doc: Document) -> str:
    """문서 고유 키 생성"""
    content = doc.page_content[:1000]
    source = doc.metadata.get("source", "")
    data_to_hash = f"{content}|{source}"
    return hashlib.sha256(data_to_hash.encode("utf-8")).hexdigest()


def is_korean_text(text: str) -> bool:
    """한글 포함 여부 확인"""
    korean_pattern = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣ]")
    return bool(korean_pattern.search(text))


def extract_keywords(text: str) -> Set[str]:
    """키워드 추출"""
    keywords = set()

    # 패턴 1: 모델명 (예: GPT-4, BERT-base)
    pattern1 = r"\b[a-zA-Z]+-?\w*\d+\w*\b"
    keywords.update(re.findall(pattern1, text.lower()))

    # 패턴 2: 약어 (예: LLM, CNN)
    pattern2 = r"\b[A-Z]{2,}[a-z]?\d*\b"
    keywords.update([w.lower() for w in re.findall(pattern2, text)])

    # 패턴 3: 하이픈/언더스코어 연결어 (다중 하이픈 지원)
    # 예: Cache-to-Cache, BERT-base, Multi-Head-Attention
    pattern3 = r"\b\w+(?:[-_]\w+)+\b"
    keywords.update(re.findall(pattern3, text.lower()))

    # 기술 용어
    tech_terms = {
        "transformer", "attention", "diffusion", "gan",
        "vae", "bert", "gpt", "llama",
        "sam", "clip", "vit","resnet",
        "unet", "rag", "retrieval", "embedding",
        "tokenizer", "langchain", "pytorch", "tensorflow",
        "huggingface", "audio", "model", "paper",
        "papers",
    }
    words = set(re.findall(r"\b\w+\b", text.lower()))
    keywords.update(words & tech_terms)

    return keywords


def calculate_metadata_boost(doc: Document, query_keywords: Set[str]) -> float:
    """메타데이터 기반 부스팅 점수 계산"""
    boost = 0.0
    metadata = doc.metadata or {}

    # Title 매칭
    title = metadata.get("title", "").lower()
    for keyword in query_keywords:
        if keyword in title:
            boost += 0.05
            break

    # doc_id 매칭 (논문 고유 ID)
    doc_id = metadata.get("doc_id", "").lower()
    for keyword in query_keywords:
        if keyword in doc_id:
            boost += 0.01
            break

    return boost


def is_ai_ml_related_by_llm(question: str, llm) -> bool:
    """LLM으로 AI/ML/DL/LLM 관련성 판별"""
    if not question or llm is None:
        return False

    chain = AI_ML_CLASSIFICATION_PROMPT | llm | StrOutputParser()
    try:
        result = chain.invoke({"question": question}).strip().upper()
        return result.startswith("Y")
    except Exception as e:
        print(f"[WARN] LLM topic classification failed: {e}")
        return True


# ===== Reranker Classes =====
class CrossEncoderReranker:
    """Cross-encoder 기반 재랭커"""

    def __init__(self, model_name: str = "BAAI/bge-reranker-large"):
        """
        Args:
            model_name: Cross-encoder 모델 이름
                - cross-encoder/ms-marco-MiniLM-L-6-v2 (빠름, 작음)
                - cross-encoder/ms-marco-MiniLM-L-12-v2 (중간)
                - BAAI/bge-reranker-base (정확함, 중간 크기)
                - BAAI/bge-reranker-large (가장 정확함, 논문 검색에 최적) [기본값]
        """
        try:
            from sentence_transformers import CrossEncoder

            self.model = CrossEncoder(model_name)
            self.model_name = model_name
            print(f"[Reranker] Cross-encoder 로드 완료: {model_name}")
        except ImportError:
            print(
                "[ERROR] sentence-transformers 설치 필요: pip install sentence-transformers"
            )
            self.model = None
        except Exception as e:
            print(f"[ERROR] Cross-encoder 로드 실패: {e}")
            self.model = None

    def rerank(
        self, question: str, documents: List[Document], top_k: int = 5
    ) -> List[tuple]:
        """
        문서 재랭킹

        Args:
            question: 사용자 질문
            documents: 검색된 문서 리스트
            top_k: 상위 k개 반환

        Returns:
            [(Document, score), ...] 정렬된 리스트
        """
        if not self.model or not documents:
            return [(doc, 0.0) for doc in documents[:top_k]]

        try:
            # Query-Document 쌍 생성
            pairs = []
            for doc in documents:
                # Abstract 일부만 사용 (너무 길면 성능 저하)
                content = doc.page_content[:1000]
                pairs.append([question, content])

            # 재랭킹 점수 계산
            scores = self.model.predict(pairs)

            # (Document, score) 쌍 생성
            doc_score_pairs = list(zip(documents, scores))

            # 점수 기반 정렬 (내림차순)
            doc_score_pairs.sort(key=lambda x: x[1], reverse=True)

            # 상위 k개 선택
            top_results = doc_score_pairs[:top_k]

            print(
                f"[Reranker] 재랭킹 완료: {len(documents)}개 → {len(top_results)}개"
            )
            print(
                f"[Reranker] Top 점수: {top_results[0][1]:.4f} ~ {top_results[-1][1]:.4f}"
            )

            return top_results

        except Exception as e:
            print(f"[ERROR] 재랭킹 실패: {e}")
            return [(doc, 0.0) for doc in documents[:top_k]]

    def is_available(self) -> bool:
        """재랭커 사용 가능 여부"""
        return self.model is not None


class LLMReranker:
    """LLM 기반 재랭커 (Cross-encoder 대안)"""

    def __init__(self, llm):
        """
        Args:
            llm: ChatOpenAI 등 LLM 인스턴스
        """
        self.llm = llm
        print("[Reranker] LLM 재랭커 초기화 완료")

    def rerank(
        self, question: str, documents: List[Document], top_k: int = 5
    ) -> List[tuple]:
        """
        LLM으로 문서 관련성 점수 매기기

        Args:
            question: 사용자 질문
            documents: 검색된 문서 리스트
            top_k: 상위 k개 반환

        Returns:
            [(Document, score), ...] 정렬된 리스트
        """
        from langchain_core.prompts import ChatPromptTemplate

        if not documents:
            return []

        try:
            doc_scores = []

            prompt = ChatPromptTemplate.from_messages(
                [
                    (
                        "system",
                        """Rate the relevance of the document to the question on a scale of 0-100.
- 0: Completely irrelevant
- 50: Somewhat relevant
- 100: Highly relevant

Output only the number.""",
                    ),
                    (
                        "human",
                        """Question: {question}

Document:
{document}

Relevance score (0-100):""",
                    ),
                ]
            )

            chain = prompt | self.llm | StrOutputParser()

            for doc in documents[:10]:  # 최대 10개만 재랭킹 (비용 절감)
                content = doc.page_content[:800]
                result = chain.invoke(
                    {"question": question, "document": content}
                ).strip()

                try:
                    score = float(result) / 100.0  # 0-1 스케일로 변환
                except:
                    score = 0.5  # 파싱 실패 시 중간값

                doc_scores.append((doc, score))

            # 점수 기반 정렬
            doc_scores.sort(key=lambda x: x[1], reverse=True)

            print(f"[LLM Reranker] 재랭킹 완료: {len(doc_scores)}개 평가")
            return doc_scores[:top_k]

        except Exception as e:
            print(f"[ERROR] LLM 재랭킹 실패: {e}")
            return [(doc, 0.0) for doc in documents[:top_k]]

    def is_available(self) -> bool:
        """재랭커 사용 가능 여부"""
        return True


def create_reranker(
    reranker_type: str = "cross-encoder",
    model_name: str = "BAAI/bge-reranker-large",
    llm=None,
):
    """
    재랭커 생성

    Args:
        reranker_type: "cross-encoder" 또는 "llm"
        model_name: Cross-encoder 모델 이름 (기본값: BAAI/bge-reranker-large)
        llm: LLM 인스턴스 (reranker_type="llm"인 경우)

    Returns:
        Reranker 인스턴스
    """
    if reranker_type == "cross-encoder":
        return CrossEncoderReranker(model_name)
    elif reranker_type == "llm":
        if llm is None:
            raise ValueError("LLM reranker requires llm parameter")
        return LLMReranker(llm)
    else:
        raise ValueError(
            f"Unknown reranker type: {reranker_type}. Use 'cross-encoder' or 'llm'"
        )


# ===== Node Functions =====
def translate_node(state: GraphState) -> dict:
    """노드 0: 한글 질문 번역"""
    print("\n" + "=" * 60)
    print("[NODE: translate] 질문 언어 확인 및 번역")
    print("=" * 60)

    original_question = state["original_question"]
    llm = state.get("_llm")
    has_korean = is_korean_text(original_question)

    if not has_korean:
        print("[translate] 영어 질문 - 번역 스킵")
        return {
            "question": original_question,
            "original_question": original_question,
            "translated_question": None,
            "is_korean": False,
        }

    print("[translate] 한글 질문 - 영어로 번역 중...")
    try:
        chain = TRANSLATION_PROMPT | llm | StrOutputParser()
        translated = chain.invoke({"korean_text": original_question}).strip()
        print(f"[translate] 번역 완료: {translated}")
        return {
            "question": translated,
            "original_question": original_question,
            "translated_question": translated,
            "is_korean": True,
        }
    except Exception as e:
        print(f"[ERROR] 번역 실패: {e}")
        return {
            "question": original_question,
            "original_question": original_question,
            "translated_question": None,
            "is_korean": True,
        }


def topic_guard_node(state: GraphState) -> dict:
    """노드 1: AI/ML/DL/LLM 관련성 사전 체크"""
    print("\n" + "=" * 60)
    print("[NODE: topic_guard] AI/ML/DL/LLM 관련성 사전 체크")
    print("=" * 60)

    original_q = state.get("original_question", "")
    question = state.get("question", "")
    llm = state.get("_llm")

    print(f"[topic_guard] 질문: {original_q}")

    try:
        is_related = is_ai_ml_related_by_llm(
            question if question else original_q, llm
        )
        if is_related:
            print("[topic_guard] ✅ AI/ML/DL/LLM 관련 → 검색 진행")
            return {"is_ai_ml_related": True}
        else:
            print("[topic_guard] ❌ 비 AI/ML/DL/LLM → 검색 스킵")
            return {"is_ai_ml_related": False}
    except Exception as e:
        print(f"[WARN] 토픽 가드 실패: {e}")
        return {"is_ai_ml_related": True}


def retrieve_node(state: GraphState) -> dict:
    """노드 2: Multi-Query 하이브리드 검색 + 메타데이터 부스팅 + 재랭킹"""
    print("\n" + "=" * 60)
    print("[NODE: retrieve] Multi-Query 하이브리드 검색")
    print("=" * 60)

    question = state["question"]
    vectorstore = state.get("_vectorstore")
    bm25_retriever = state.get("_bm25_retriever")
    llm = state.get("_llm")

    if vectorstore is None:
        print("[ERROR] VectorStore 없음")
        return {
            "documents": [],
            "doc_scores": [],
            "search_type": "vector",
        }

    # ===== 1. Query 확장 =====
    try:
        # expanded_queries = expand_query_for_papers(question, llm)
        expanded_queries = [question]
    except Exception as e:
        print(f"[WARN] Query 확장 실패: {e}")
        expanded_queries = [question]

    query_keywords = extract_keywords(question)
    if query_keywords:
        print(f"[retrieve] 키워드: {query_keywords}")

    use_bm25 = bm25_retriever is not None

    try:
        # ===== 2. Multi-Query 검색 =====
        all_vector_docs_with_scores = []
        all_bm25_docs = []

        # 각 쿼리로 검색
        for i, query in enumerate(expanded_queries):
            print(f"[retrieve] 쿼리 {i+1}/{len(expanded_queries)}: {query[:50]}...")

            # Vector 검색
            vector_results = vectorstore.similarity_search_with_score(query, k=3)
            all_vector_docs_with_scores.extend(vector_results)

            # BM25 검색
            if use_bm25:
                bm25_results = bm25_retriever.invoke(query)
                all_bm25_docs.extend(bm25_results[:3])

        print(
            f"[retrieve] 총 벡터 검색: {len(all_vector_docs_with_scores)}개 (중복 포함)"
        )
        if use_bm25:
            print(f"[retrieve] 총 BM25 검색: {len(all_bm25_docs)}개 (중복 포함)")

        # BM25가 없으면 Vector만 사용
        if not use_bm25:
            print("[retrieve] BM25 없음 → 벡터만 사용")

            # 중복 제거 및 부스팅
            doc_map = {}
            for doc, score in all_vector_docs_with_scores:
                doc_key = get_doc_hash_key(doc)
                if doc_key not in doc_map or score < doc_map[doc_key][1]:
                    doc_map[doc_key] = (doc, score)

            boosted_docs = []
            boosted_scores = []
            for doc, score in sorted(
                doc_map.values(), key=lambda x: x[1]
            )[:10]:
                boost = calculate_metadata_boost(doc, query_keywords)
                adjusted_score = max(0.0, score - boost * 2.0)
                boosted_docs.append(doc)
                boosted_scores.append(adjusted_score)
                if boost > 0:
                    print(
                        f"[retrieve] 부스팅: {doc.metadata.get('title', 'N/A')[:50]} (+{boost:.3f})"
                    )

            # ===== 3. 재랭킹 적용 =====
            if _reranker and _reranker.is_available():
                reranked_results = _reranker.rerank(question, boosted_docs, top_k=3)
                final_docs = [doc for doc, score in reranked_results]
                final_scores = [score for doc, score in reranked_results]
            else:
                final_docs = boosted_docs[:3]
                final_scores = boosted_scores[:3]

            return {
                "documents": final_docs,
                "doc_scores": final_scores,
                "search_type": "vector",
            }

        # ===== 4. RRF (Reciprocal Rank Fusion) for Hybrid Search =====
        RRF_K = 60
        fusion_scores = {}
        doc_map = {}
        metadata_boosts = {}

        # Vector 문서 처리 (Multi-Query 결과)
        for rank, (doc, _score) in enumerate(all_vector_docs_with_scores):
            doc_key = get_doc_hash_key(doc)
            if doc_key not in doc_map:
                doc_map[doc_key] = doc
            score = 1.5 / (RRF_K + rank + 1)
            fusion_scores[doc_key] = fusion_scores.get(doc_key, 0.0) + score
            if doc_key not in metadata_boosts:
                metadata_boosts[doc_key] = calculate_metadata_boost(
                    doc, query_keywords
                )

        # BM25 문서 처리 (Multi-Query 결과)
        for rank, doc in enumerate(all_bm25_docs):
            doc_key = get_doc_hash_key(doc)
            if doc_key not in doc_map:
                doc_map[doc_key] = doc
            score = 0.5 / (RRF_K + rank + 1)
            fusion_scores[doc_key] = fusion_scores.get(doc_key, 0.0) + score
            if doc_key not in metadata_boosts:
                metadata_boosts[doc_key] = calculate_metadata_boost(
                    doc, query_keywords
                )

        # 메타데이터 부스팅 적용
        for doc_key in fusion_scores:
            boost = metadata_boosts.get(doc_key, 0.0)
            if boost > 0:
                original_score = fusion_scores[doc_key]
                fusion_scores[doc_key] += boost
                doc = doc_map[doc_key]
                print(
                    f"[retrieve] 부스팅: {doc.metadata.get('title', 'N/A')[:50]}"
                )
                print(
                    f"           {original_score:.4f} → {fusion_scores[doc_key]:.4f} (+{boost:.4f})"
                )

        # 정렬 및 상위 10개 선택 (재랭킹 전)
        sorted_items = sorted(
            fusion_scores.items(), key=lambda x: x[1], reverse=True
        )
        documents = []
        scores = []
        for doc_key, score in sorted_items[:10]:
            documents.append(doc_map[doc_key])
            scores.append(score)

        if not documents:
            print("[retrieve] 문서 없음")
            return {
                "documents": [],
                "doc_scores": [],
                "search_type": "hybrid",
            }

        # ===== 5. 재랭킹 적용 =====
        if _reranker and _reranker.is_available():
            reranked_results = _reranker.rerank(question, documents, top_k=3)
            final_docs = [doc for doc, score in reranked_results]
            final_scores = [score for doc, score in reranked_results]
        else:
            final_docs = documents[:3]
            final_scores = scores[:3]

        print(
            f"[retrieve] 완료: {len(final_docs)}개, 최상위={final_scores[0]:.4f}"
        )

        return {
            "documents": final_docs,
            "doc_scores": final_scores,
            "search_type": "hybrid",
        }

    except Exception as e:
        print(f"[ERROR] 검색 오류: {e}")
        import traceback

        traceback.print_exc()
        return {
            "documents": [],
            "doc_scores": [],
            "search_type": "hybrid",
        }


def evaluate_document_relevance_node(state: GraphState) -> dict:
    """노드 3: 문서 관련성 평가"""
    print("\n" + "=" * 60)
    print("[NODE: evaluate] 문서 관련성 평가")
    print("=" * 60)

    original_q = state.get("original_question", "")
    question = state.get("question", "")
    documents = state["documents"]
    scores = state["doc_scores"]
    is_ai_ml_related = state.get("is_ai_ml_related", True)

    print(f"[evaluate] AI/ML/DL/LLM 관련성: {is_ai_ml_related}")

    # 키워드 매칭 체크
    query_keywords = extract_keywords(question)
    if not query_keywords:
        query_keywords = extract_keywords(original_q)

    print(f"[evaluate] 추출된 키워드: {query_keywords}")

    if documents and query_keywords:
        for doc in documents[:3]:
            metadata = doc.metadata or {}
            title = metadata.get("title", "").lower()
            for keyword in query_keywords:
                if keyword in title:
                    print(f"[evaluate] ✅ 메타데이터 매칭: '{keyword}' in '{metadata.get('title', '')}'")
                    return {
                        "relevance_level": "high",
                        "is_ai_ml_related": is_ai_ml_related,
                    }

    if not documents or not scores:
        print("[evaluate] 문서 없음 → LOW")
        return {
            "relevance_level": "low",
            "is_ai_ml_related": is_ai_ml_related,
        }

    # 점수 기반 평가
    best_score = max(scores)
    if best_score >= 0.0325:
        level = "high"
    elif best_score >= 0.0120:
        level = "medium"
    else:
        level = "low"

    print(f"[evaluate] RRF={best_score:.6f} → {level.upper()}")
    return {"relevance_level": level, "is_ai_ml_related": is_ai_ml_related}


def web_search_node(state: GraphState) -> dict:
    """노드 4: 웹 검색"""
    print("\n" + "=" * 60)
    print("[NODE: web_search] 웹 검색 시작")
    print("=" * 60)

    question = state["question"]

    try:
        from langchain_community.retrievers import TavilySearchAPIRetriever

        print("[web_search] Tavily API 사용")

        retriever = TavilySearchAPIRetriever(k=3)
        web_docs_raw = retriever.invoke(question)
        print(f"[web_search] Tavily: {len(web_docs_raw)}개")

        processed_web_docs = []
        for i, doc in enumerate(web_docs_raw):
            original_meta = doc.metadata
            title = original_meta.get("title", "웹 검색 결과")
            source_url = original_meta.get("source", "")
            score = original_meta.get("score", 0.5)

            web_doc = Document(
                page_content=doc.page_content,
                metadata={
                    "title": title,
                    "source": source_url,
                    "source_type": "web",
                    "score": score,
                    "index": i,
                },
            )
            processed_web_docs.append(web_doc)
            print(f"  [{i+1}] {title[:60]}")

        return {
            "documents": processed_web_docs,
            "search_type": "web",
            "doc_scores": [doc.metadata["score"] for doc in processed_web_docs],
        }

    except Exception as e:
        print(f"[web_search] Tavily 실패: {e}")
        return {
            "documents": [
                Document(
                    page_content="웹 검색 실패",
                    metadata={"source": "system", "source_type": "error"},
                )
            ],
            "search_type": "web_failed",
            "doc_scores": [2.0],
        }


def generate_final_answer_node(state: GraphState) -> dict:
    """노드 5: 최종 답변 생성 + Sources 구성"""
    print("\n" + "=" * 60)
    print("[NODE: generate] 최종 답변 생성")
    print("=" * 60)

    original_question = state["original_question"]
    documents = state["documents"]
    search_type = state.get("search_type", "internal")
    is_korean = state.get("is_korean", False)
    llm = state.get("_llm")

    if is_korean:
        print(f"[generate] 원본(한글): {original_question}")
        print(f"[generate] 검색(영어): {state.get('question')}")

    # 1) CONTEXT 블록
    if not documents:
        context_str = "NO_RELEVANT_PAPERS"
    else:
        context_blocks = []
        for i, doc in enumerate(documents[:3], 1):
            meta = doc.metadata or {}
            title = meta.get("title", "No information")
            authors = meta.get("authors", "No information")

            # authors가 JSON 문자열이면 파싱
            if isinstance(authors, str) and authors.startswith("["):
                try:
                    authors = json.loads(authors)
                except:
                    pass

            hf_url = meta.get("huggingface_url", meta.get("source", "No information"))
            gh_url = meta.get("github_url", "No information")
            upvote = meta.get("upvote", "No information")
            year = meta.get("publication_year", "No information")
            doc_id = meta.get("doc_id", "No information")

            block = f"""
[DOCUMENT {i}]
page_content:
{doc.page_content}

metadata:
  title: {title}
  huggingface_url: {hf_url}
  github_url: {gh_url}
  upvote: {upvote}
  authors: {authors}
  publication_year: {year}
  doc_id: {doc_id}
"""
            context_blocks.append(block)
        context_str = "\n".join(context_blocks)

    # 2) 답변 생성
    try:
        chain = ANSWER_GENERATION_PROMPT | llm | StrOutputParser()
        answer = chain.invoke(
            {"question": original_question, "context": context_str}
        )
        print("[generate] 답변 생성 완료")
    except Exception as e:
        print(f"[ERROR] 답변 생성 오류: {e}")
        answer = f"답변 생성 중 오류가 발생했습니다: {str(e)}"

    # 3) SOURCES 구성 - 중복 제거
    seen_docs = set()
    sources: List[Dict[str, Any]] = []

    for doc in documents[:3]:
        meta = doc.metadata or {}
        doc_id = meta.get("doc_id")

        # doc_id가 있는 경우 중복 체크
        if doc_id and doc_id in seen_docs:
            print(f"[generate] 중복 문서 스킵: doc_id={doc_id}")
            continue

        # doc_id 기록
        if doc_id:
            seen_docs.add(doc_id)

        # 웹 검색 결과인 경우
        if meta.get("source_type") == "web":
            sources.append(
                {
                    "type": "web",
                    "title": meta.get("title", "웹 검색 결과"),
                    "url": meta.get("source", ""),
                    "score": meta.get("score", 0.5),
                }
            )
            print(f"[generate] 웹 출처 추가: {meta.get('title', 'Unknown')[:50]}")
        # 논문 문서인 경우
        else:
            title = meta.get("title", "Unknown")
            hf_url = meta.get("huggingface_url", meta.get("source", ""))
            gh_url = meta.get("github_url", "")
            authors = meta.get("authors", "Unknown")

            # authors가 JSON 문자열이면 파싱
            if isinstance(authors, str) and authors.startswith("["):
                try:
                    authors = json.loads(authors)
                except:
                    pass

            year = meta.get("publication_year", "Unknown")
            upvote = meta.get("upvote", 0)

            sources.append(
                {
                    "type": "paper",
                    "title": title,
                    "huggingface_url": hf_url,
                    "github_url": gh_url,
                    "authors": authors,
                    "year": year,
                    "upvote": upvote,
                    "doc_id": doc_id,
                }
            )
            print(f"[generate] 논문 출처 추가: {title[:50]}")

    print(f"[generate] 총 {len(sources)}개 고유 출처 추가됨")

    return {"answer": answer, "sources": sources}


def reject_node(state: GraphState) -> dict:
    """노드 6: 거부 응답"""
    print("\n" + "=" * 60)
    print("[NODE: reject] 질문 거부")
    print("=" * 60)

    question = state["original_question"]
    is_ai_ml_related = state.get("is_ai_ml_related", False)

    if not is_ai_ml_related:
        answer = f"""죄송합니다. "{question}"는 AI/ML/DL/LLM 연구 논문과 관련이 없는 질문입니다.

이 시스템은 다음과 같은 질문에 답변할 수 있습니다:
• AI/ML/DL/LLM 모델 및 아키텍처 (GPT, BERT, SAM, Diffusion 등)
• AI/ML/DL/LLM 개념 및 기술 (Transformer, Attention, Fine-tuning 등)
• AI/ML/DL/LLM 도구 및 라이브러리 (LangChain, Transformers, PyTorch 등)
• 최근 AI/ML/DL/LLM 연구 동향 및 논문

AI/ML/DL/LLM 관련 질문으로 다시 시도해주세요!"""
        print("[reject] 비 AI/ML/DL/LLM 질문 거부")
    else:
        answer = f"""죄송합니다. '{question}'와 관련된 적절한 문서를 찾지 못했습니다.

다음과 같이 시도해보세요:
1. 더 구체적인 키워드 사용 (예: "transformer", "attention mechanism")
2. 영어 학술 용어 사용
3. 질문을 다시 표현해보기
4. 최근 발표된 논문 키워드로 검색

이 시스템은 HuggingFace에 게시된 최근 AI/ML 연구 논문을 기반으로 답변합니다."""
        print("[reject] AI/ML 관련이지만 문서 없음")

    return {"answer": answer, "sources": [], "search_type": "rejected"}


# ===== Conditional Edge Functions =====
def route_after_topic_guard(
    state: GraphState,
) -> Literal["retrieve", "reject"]:
    """topic_guard 이후 라우팅"""
    is_ai_ml_related = state.get("is_ai_ml_related", True)
    print("\n[ROUTING] topic_guard → ", end="")
    if is_ai_ml_related:
        print("retrieve")
        return "retrieve"
    else:
        print("reject")
        return "reject"


def route_after_evaluate(
    state: GraphState,
) -> Literal["generate", "web_search", "reject"]:
    """evaluate 이후 라우팅"""
    level = state.get("relevance_level", "low")
    documents = state.get("documents", [])
    is_ai_ml_related = state.get("is_ai_ml_related", True)

    print(
        f"\n[ROUTING] evaluate → {level.upper()} (AI/ML: {is_ai_ml_related})",
        end=" → ",
    )

    if level == "high":
        print("generate")
        return "generate"
    elif level == "medium":
        print("generate")
        return "generate"
    else:  # level == "low"
        if is_ai_ml_related:
            # AI/ML 관련 질문이지만 LOW 점수 → 무조건 웹 검색
            print("web_search (LOW score)")
            return "web_search"
        else:
            print("reject")
            return "reject"


# ===== Graph Builder =====
def build_langgraph_rag():
    """LangGraph RAG 시스템 구축"""
    print("\n" + "=" * 60)
    print("[GRAPH BUILD] LangGraph 구축")
    print("=" * 60)

    graph = StateGraph(GraphState)

    # 노드 추가
    graph.add_node("translate", translate_node)
    graph.add_node("topic_guard", topic_guard_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("evaluate", evaluate_document_relevance_node)
    graph.add_node("web_search", web_search_node)
    graph.add_node("generate", generate_final_answer_node)
    graph.add_node("reject", reject_node)

    print("[GRAPH] 7개 노드 추가 완료")

    # 엣지 추가
    graph.add_edge(START, "translate")
    graph.add_edge("translate", "topic_guard")
    graph.add_edge("retrieve", "evaluate")

    # 조건부 엣지
    graph.add_conditional_edges(
        "topic_guard",
        route_after_topic_guard,
        {"retrieve": "retrieve", "reject": "reject"},
    )
    graph.add_conditional_edges(
        "evaluate",
        route_after_evaluate,
        {
            "generate": "generate",
            "web_search": "web_search",
            "reject": "reject",
        },
    )

    graph.add_edge("web_search", "generate")
    graph.add_edge("generate", END)
    graph.add_edge("reject", END)

    print("[GRAPH] 엣지 추가 완료")

    compiled_graph = graph.compile()
    print("[GRAPH] 컴파일 완료")

    return compiled_graph


# ===== External API Functions =====
_vectorstore = None
_llm = None
_bm25_retriever = None
_langgraph_app = None
_reranker = None


def initialize_rag_system(
    model_name: str = "text-embedding-3-small",
    llm_model: str = "gpt-4o-mini",
    llm_temperature: float = 0,
    use_reranker: bool = True,
    reranker_type: str = "cross-encoder",
) -> dict:
    """
    RAG 시스템 초기화

    Args:
        model_name: 임베딩 모델 이름 (기본: text-embedding-3-small, 차원: 1536)
                   - OpenAI: text-embedding-3-small, text-embedding-3-large
                   - HuggingFace: sentence-transformers/all-MiniLM-L6-v2 (차원: 384)
        llm_model: LLM 모델 이름
        llm_temperature: LLM temperature
        use_reranker: 재랭커 사용 여부
        reranker_type: "cross-encoder" 또는 "llm"
    """
    global _vectorstore, _llm, _bm25_retriever, _langgraph_app, _reranker

    try:
        print("\n[INIT] 초기화 중...")

        # VectorStore 로드
        print(f"[LOADING] VectorStore: {model_name}")
        _vectorstore = load_vectordb(
            persist_directory=str(
                PROJECT_ROOT / "data" / "vector_db" / "chroma"
            ),
            model_name=model_name,
        )

        # BM25 Retriever 생성
        print("[LOADING] BM25 Retriever")
        collection_data = _vectorstore._collection.get(
            include=["documents", "metadatas"]
        )
        all_documents = [
            Document(page_content=content, metadata=metadata)
            for content, metadata in zip(
                collection_data["documents"], collection_data["metadatas"]
            )
        ]
        if not all_documents:
            raise ValueError("문서 없음")

        _bm25_retriever = BM25Retriever.from_documents(all_documents)
        _bm25_retriever.k = 3
        print(f"[SUCCESS] BM25: {len(all_documents)}개")

        # LLM 로드
        print(f"[LOADING] LLM: {llm_model}")
        _llm = ChatOpenAI(model=llm_model, temperature=llm_temperature)

        # 재랭커 초기화
        if use_reranker:
            print(f"[LOADING] Reranker: {reranker_type}")
            try:
                _reranker = create_reranker(
                    reranker_type=reranker_type,
                    model_name="BAAI/bge-reranker-large",  # 논문 검색 정확도 향상
                    llm=_llm if reranker_type == "llm" else None,
                )
                print("[SUCCESS] 재랭커 로드 완료")
            except Exception as e:
                print(f"[WARN] 재랭커 로드 실패 (계속 진행): {e}")
                _reranker = None
        else:
            print("[INFO] 재랭커 비활성화")
            _reranker = None

        # LangGraph 컴파일
        print("[LOADING] LangGraph 컴파일")
        _langgraph_app = build_langgraph_rag()

        print("[SUCCESS] 초기화 완료!\n")

        return {"status": "success", "message": "Initialized successfully"}

    except Exception as e:
        print(f"[ERROR] 초기화 실패: {e}")
        import traceback

        traceback.print_exc()
        return {"status": "error", "message": str(e)}


def ask_question(question: str, verbose: bool = False) -> dict:
    """질문 처리"""
    global _vectorstore, _llm, _bm25_retriever, _langgraph_app

    if _langgraph_app is None:
        return {"success": False, "error": "Not initialized"}

    try:
        if verbose:
            print(f"\n[QUESTION] {question}")

        initial_state = {
            "question": "",
            "original_question": question,
            "translated_question": None,
            "is_korean": False,
            "documents": [],
            "doc_scores": [],
            "search_type": "",
            "relevance_level": "",
            "answer": "",
            "sources": [],
            "is_ai_ml_related": True,
            "_vectorstore": _vectorstore,
            "_llm": _llm,
            "_bm25_retriever": _bm25_retriever,
        }

        result = _langgraph_app.invoke(initial_state)

        if verbose:
            print("[ANSWER] 완료")
            print(f"[SOURCES] {len(result.get('sources', []))}개")

        # 실제 사용된 문서 추출 (RAGAS 평가용 - 메타데이터 포함)
        documents = result.get("documents", [])
        contexts = []
        for doc in documents:
            if hasattr(doc, "page_content"):
                # 메타데이터 포함하여 context 구성
                meta = doc.metadata if hasattr(doc, "metadata") else {}
                context_text = doc.page_content
                if meta:
                    context_text += f"\n\n[메타데이터]"
                    if meta.get("title"):
                        context_text += f"\ntitle: {meta.get('title')}"
                    if meta.get("huggingface_url"):
                        context_text += f"\nhuggingface_url: {meta.get('huggingface_url')}"
                    if meta.get("github_url"):
                        context_text += f"\ngithub_url: {meta.get('github_url')}"
                    if meta.get("authors"):
                        context_text += f"\nauthors: {meta.get('authors')}"
                    if meta.get("upvote"):
                        context_text += f"\nupvote: {meta.get('upvote')}"
                contexts.append(context_text)

        return {
            "success": True,
            "question": question,
            "answer": result.get("answer", ""),
            "sources": result.get("sources", []),
            "contexts": contexts,  # 실제 사용된 context 추가
            "metadata": {
                "search_type": result.get("search_type", ""),
                "relevance_level": result.get("relevance_level", ""),
                "is_korean": result.get("is_korean", False),
                "translated_question": result.get("translated_question"),
                "is_ai_ml_related": result.get("is_ai_ml_related", True),
            },
        }

    except Exception as e:
        print(f"[ERROR] 질문 처리 오류: {e}")
        import traceback

        traceback.print_exc()
        return {"success": False, "error": str(e)}


def get_system_status() -> dict:
    """시스템 상태 조회"""
    return {
        "initialized": _langgraph_app is not None,
        "vectorstore_loaded": _vectorstore is not None,
        "llm_loaded": _llm is not None,
        "bm25_retriever_loaded": _bm25_retriever is not None,
    }


# ===== Test Functions =====
def run_interactive_test():
    """대화형 테스트 모드"""
    print("\n" + "=" * 60)
    print("RAG 시스템 대화형 테스트")
    print("=" * 60)
    print("명령어:")
    print("  - 질문 입력: 자유롭게 질문 입력")
    print("  - 'status': 시스템 상태 확인")
    print("  - 'quit' 또는 'exit': 종료")
    print("=" * 60 + "\n")

    while True:
        try:
            question = input("\n질문> ").strip()

            if not question:
                continue

            if question.lower() in ["quit", "exit", "q"]:
                print("\n[INFO] 테스트 종료")
                break

            if question.lower() == "status":
                status = get_system_status()
                print("\n[시스템 상태]")
                for key, value in status.items():
                    print(f"  {key}: {value}")
                continue

            # 질문 처리
            result = ask_question(question, verbose=True)

            if result["success"]:
                print("\n" + "=" * 60)
                print("[답변]")
                print("=" * 60)
                print(result["answer"])

                if result["sources"]:
                    print("\n" + "-" * 60)
                    print(f"[출처] {len(result['sources'])}개")
                    print("-" * 60)
                    for i, source in enumerate(result["sources"], 1):
                        if source["type"] == "paper":
                            print(f"\n{i}. {source['title']}")
                            print(f"   Authors: {source['authors']}")
                            print(f"   Year: {source['year']}")
                            print(f"   HuggingFace: {source['huggingface_url']}")
                            if source.get("github_url"):
                                print(f"   GitHub: {source['github_url']}")
                            print(f"   Upvotes: {source['upvote']}")
                        else:
                            print(f"\n{i}. {source['title']}")
                            print(f"   URL: {source['url']}")

                # 메타데이터 출력
                metadata = result.get("metadata", {})
                print("\n" + "-" * 60)
                print("[메타데이터]")
                print("-" * 60)
                print(f"검색 타입: {metadata.get('search_type', 'N/A')}")
                print(f"관련성 레벨: {metadata.get('relevance_level', 'N/A')}")
                print(f"AI/ML 관련: {metadata.get('is_ai_ml_related', 'N/A')}")
                if metadata.get("is_korean"):
                    print(f"번역된 질문: {metadata.get('translated_question', 'N/A')}")

            else:
                print(f"\n[ERROR] {result.get('error', 'Unknown error')}")

        except KeyboardInterrupt:
            print("\n\n[INFO] 테스트 종료")
            break
        except Exception as e:
            print(f"\n[ERROR] 예외 발생: {e}")
            import traceback

            traceback.print_exc()


def run_batch_test(test_questions: List[str] = None):
    """배치 테스트 모드"""
    if test_questions is None:
        test_questions = [
            "Transformer란 무엇인가요?",
            "What is RAG?",
            "최신 diffusion model에 대해 알려주세요",
            "GPT-4와 Claude의 차이는?",
            "LangChain은 어떻게 사용하나요?",
        ]

    print("\n" + "=" * 60)
    print(f"배치 테스트: {len(test_questions)}개 질문")
    print("=" * 60)

    results = []
    for i, question in enumerate(test_questions, 1):
        print(f"\n[{i}/{len(test_questions)}] 질문: {question}")
        print("-" * 60)

        result = ask_question(question, verbose=False)

        if result["success"]:
            print(f"✅ 성공")
            print(f"답변 길이: {len(result['answer'])} 자")
            print(f"출처 개수: {len(result['sources'])}")
            print(f"검색 타입: {result['metadata'].get('search_type', 'N/A')}")
        else:
            print(f"❌ 실패: {result.get('error', 'Unknown')}")

        results.append(result)

    # 요약
    print("\n" + "=" * 60)
    print("테스트 요약")
    print("=" * 60)
    success_count = sum(1 for r in results if r["success"])
    print(f"성공: {success_count}/{len(test_questions)}")
    print(f"실패: {len(test_questions) - success_count}/{len(test_questions)}")

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="RAG 시스템 테스트")
    parser.add_argument(
        "--mode",
        type=str,
        default="interactive",
        choices=["interactive", "batch"],
        help="테스트 모드: interactive (대화형) 또는 batch (배치)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="text-embedding-3-small",
        help="임베딩 모델 이름 (OpenAI: text-embedding-3-small/large, HF: sentence-transformers/all-MiniLM-L6-v2)",
    )
    parser.add_argument(
        "--llm", type=str, default="gpt-4o-mini", help="LLM 모델 이름"
    )
    parser.add_argument(
        "--reranker",
        type=str,
        default="cross-encoder",
        choices=["cross-encoder", "llm", "none"],
        help="재랭커 타입",
    )
    parser.add_argument(
        "--question", type=str, default=None, help="단일 질문 (batch 모드에서 무시됨)"
    )

    args = parser.parse_args()

    # 시스템 초기화
    print("\n" + "=" * 60)
    print("RAG 시스템 초기화 중...")
    print("=" * 60)

    init_result = initialize_rag_system(
        model_name=args.model,
        llm_model=args.llm,
        llm_temperature=0,
        use_reranker=args.reranker != "none",
        reranker_type=args.reranker if args.reranker != "none" else "cross-encoder",
    )

    if init_result["status"] != "success":
        print(f"[ERROR] 초기화 실패: {init_result['message']}")
        exit(1)

    # 시스템 상태 확인
    status = get_system_status()
    print("\n[시스템 상태]")
    for key, value in status.items():
        print(f"  {key}: {'✅' if value else '❌'}")

    # 테스트 실행
    if args.mode == "interactive":
        # 단일 질문이 제공된 경우
        if args.question:
            print(f"\n[질문] {args.question}")
            result = ask_question(args.question, verbose=True)
            if result["success"]:
                print(f"\n[답변]\n{result['answer']}")
                print(f"\n[출처] {len(result['sources'])}개")
            else:
                print(f"\n[ERROR] {result.get('error')}")
        else:
            run_interactive_test()
    elif args.mode == "batch":
        run_batch_test()
