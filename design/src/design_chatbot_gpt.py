"""
디자인 유사성 분석 챗봇 — GPT 전용 버전

원본: design_chatbot.py
변경:
  1. llm = ChatOpenAI(model="gpt-4o-mini") — vLLM 대신 OpenAI API
  2. from utils_gpt import ... — GPT 버전 유틸 사용
"""

import os
import re
import base64
import requests
import tempfile
from PIL import Image as PILImage
from pathlib import Path
from typing import TypedDict, List, Dict, Any

# ==================== 경로 설정 ====================
BASE_DIR      = Path(__file__).resolve().parent.parent
CHROMA_DB     = str(BASE_DIR / "chroma_db")
N_RESULTS     = 15

# LangChain & LangGraph
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode

# 웹 검색
from langchain_community.tools import TavilySearchResults

# 벡터DB
import chromadb
from rank_bm25 import BM25Okapi

# ── 변경: utils_gpt에서 임포트 ──
from utils_gpt import (
    get_text_embedding,
    search_and_filter_similar_designs,
    hybrid_retrieve,
    convert_to_sketch_query
)

# 프롬프트 (원본 그대로)
from prompts import (
    IMAGE_ANALYSIS_PROMPT,
    IMAGE_COMPARISON_PROMPT,
    REPORT_PROMPT,
    FORMAT_ANALYSIS_PROMPT
)

from dotenv import load_dotenv
load_dotenv()


# ==================== LLM & ChromaDB 초기화 ====================

# ── 변경: OpenAI GPT-4o-mini 사용 (vLLM 대신) ──
llm = ChatOpenAI(
    model="gpt-4o-mini",
    api_key=os.getenv("OPENAI_API_KEY"),
    temperature=0,
)

output_parser = StrOutputParser()

chroma_client = chromadb.PersistentClient(path=CHROMA_DB)
image_collection = chroma_client.get_collection(name="design")

# BM25 인덱스 빌드
_all          = image_collection.get(include=["metadatas"])
all_ids       = _all["ids"]
all_metadatas = _all["metadatas"]
corpus_tokens = [
    re.split(r"\s+", (m.get("articleName", "") + " " + m.get("designSummary", "")).strip())
    for m in all_metadatas
]
bm25 = BM25Okapi(corpus_tokens)


# ==================== State 정의 ====================

class GraphState(TypedDict):
    """그래프 전체에서 공유되는 상태"""
    input_type: str
    image_path: str
    text_query: str
    user_query: str
    base64_image: str
    input_analysis: str
    search_results: Dict[str, Any]
    comparison_results: List[Dict]
    selected_index: int
    detailed_comparison: str
    final_report: str
    general_answer: str
    search_images: List[Dict]
    messages: List[Dict]


# ==================== Tool 정의 ====================

_search_image_results: List[Dict] = []

@tool
def web_search(query: str) -> str:
    """웹 검색 tool. 특허 뉴스, 법률 정보, 일반 질문 등에 활용됨."""
    search = TavilySearchResults(max_results=3)
    results = search.invoke(query)
    output = ""
    for r in results:
        output += f"- {r['content']}\n  출처: {r['url']}\n\n"
    return output


@tool
def search_design_db(query: str) -> str:
    """사용자가 자연어로 유사 디자인을 검색할 경우 사용되는 tool."""
    global _search_image_results
    _search_image_results = []

    embedding, translated = get_text_embedding(query, translate_korean=True)
    if embedding is None:
        return "임베딩 생성 실패"

    results = search_and_filter_similar_designs(image_collection, embedding, n_results=N_RESULTS)

    output = f"'{query}' 검색 결과 (번역: '{translated}'):\n\n"
    for i in range(len(results['ids'][0])):
        meta = results['metadatas'][0][i]
        dist = results['distances'][0][i]
        output += (
            f"{i+1}. {meta.get('articleName', 'N/A')}\n"
            f"   출원번호: {meta.get('applicationNumber', 'N/A')}\n"
            f"   등록상태: {meta.get('admstStat', 'N/A')}\n"
            f"   유사도 거리: {dist:.4f}\n\n"
        )
        if meta.get('imagePath'):
            _search_image_results.append({
                'application_number': meta.get('applicationNumber', ''),
                'last_disposition_date': meta.get('lastDispositionDate', ''),
                'image_path': meta.get('imagePath', ''),
            })
    return output


tools = [web_search, search_design_db]
llm_with_tools = llm.bind_tools(tools)


# ==================== 노드 함수 정의 ====================

def router_node(state: GraphState) -> GraphState:
    if state.get('image_path') and os.path.exists(state['image_path']):
        state['input_type'] = 'image'
        print("[router] 이미지 입력 → 유사 디자인 검색 경로로 라우팅합니다. ")
    else:
        state['input_type'] = 'text'
        print("[router] 텍스트 입력 → LLM + Tools 경로로 라우팅합니다. ")
    return state


def route_by_type(state: GraphState) -> str:
    return state['input_type']


def analyze_image_node(state: GraphState) -> GraphState:
    print("[VLM분석-GPT] 입력 이미지 분석 중 ~")
    with open(state['image_path'], "rb") as f:
        b64 = base64.b64encode(f.read()).decode('utf-8')
    url = f"data:image/jpeg;base64,{b64}"

    chain = IMAGE_ANALYSIS_PROMPT | llm | output_parser
    analysis = chain.invoke({"image_url": url})

    format_chain = FORMAT_ANALYSIS_PROMPT | llm | output_parser
    formatted_analysis = format_chain.invoke({"analysis_json": analysis})

    state['base64_image'] = url
    state['input_analysis'] = formatted_analysis
    print(f"  분석 완료 ({len(analysis)}자)")
    return state


def image_search_node(state: GraphState) -> GraphState:
    print("[벡터검색] 유사 디자인 검색 중...")
    pil_image    = PILImage.open(state['image_path']).convert('RGB')
    sketch_image = convert_to_sketch_query(pil_image)

    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
        sketch_image.save(tmp.name)
        sketch_path = tmp.name

    try:
        hybrid_results = hybrid_retrieve(
            sketch_path, image_collection, bm25, all_ids, all_metadatas,
        )
    finally:
        os.unlink(sketch_path)

    comparison_results = []
    for i, item in enumerate(hybrid_results):
        design_id = item['id']
        metadata  = item['metadata']
        comparison_results.append({
            'index':              i + 1,
            'design_id':          design_id,
            'hybrid_score':       item['hybrid_score'],
            'dense_score':        item['dense_score'],
            'bm25_score':         item['bm25_score'],
            'application_number': metadata.get('applicationNumber', 'N/A'),
            'article_name':       metadata.get('articleName', 'N/A'),
            'admst_stat':         metadata.get('admstStat', 'N/A'),
            'image_path':         metadata.get('imagePath', ''),
        })

    state['comparison_results'] = comparison_results
    print(f"  {len(comparison_results)}개 유사 디자인 발견")
    return state


def show_results_node(state: GraphState) -> GraphState:
    print("\n" + "="*50)
    print("유사 디자인 검색 결과")
    print("="*50)
    for comp in state['comparison_results']:
        print(f"  [{comp['index']}] 출원번호: {comp['application_number']}",
              f"상품명: {comp['article_name']}, "
              f"등록상태: {comp['admst_stat']}, "
              f"점수: {comp['hybrid_score']:.4f}")

    selected = interrupt({
        "message": "상세 비교할 디자인 번호를 선택하세요!",
        "options": [comp['index'] for comp in state['comparison_results']]
    })
    state['selected_index'] = int(selected)
    print(f"\n  → {selected}번 디자인 선택됨!")
    return state


def detailed_compare_node(state: GraphState) -> GraphState:
    print("[상세비교-GPT] 분석 중...")
    selected = next(
        (c for c in state['comparison_results'] if c['index'] == state['selected_index']),
        None
    )
    if not selected or not selected['image_path']:
        state['detailed_comparison'] = "비교 대상 이미지를 찾을 수 없습니다."
        return state

    img_path = selected['image_path']
    try:
        if img_path.startswith('http://') or img_path.startswith('https://'):
            resp = requests.get(img_path, timeout=10)
            if resp.status_code != 200:
                state['detailed_comparison'] = "비교 대상 이미지를 찾을 수 없습니다."
                return state
            b64 = base64.b64encode(resp.content).decode('utf-8')
        elif os.path.exists(img_path):
            with open(img_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode('utf-8')
        else:
            state['detailed_comparison'] = "비교 대상 이미지를 찾을 수 없습니다."
            return state
    except Exception as e:
        state['detailed_comparison'] = f"비교 대상 이미지 로드 실패: {e}"
        return state
    comp_url = f"data:image/jpeg;base64,{b64}"

    chain = IMAGE_COMPARISON_PROMPT | llm | output_parser
    result = chain.invoke({
        "input_image_url": state['base64_image'],
        "comparison_image_url": comp_url
    })
    state['detailed_comparison'] = result
    print("  상세 비교 완료!")
    return state


def generate_report_node(state: GraphState) -> GraphState:
    print("[리포트-GPT] 생성 중...")
    selected = next(
        (c for c in state['comparison_results'] if c['index'] == state['selected_index']),
        None
    )
    design_info = "정보 없음"
    if selected:
        design_info = (
            f"출원번호: {selected['application_number']}\n"
            f"상품명: {selected['article_name']}\n"
            f"등록상태: {selected['admst_stat']}\n"
            f"유사도 점수: {selected['hybrid_score']:.4f}"
        )
    chain = REPORT_PROMPT | llm | output_parser
    report = chain.invoke({
        "input_analysis": state.get('input_analysis', ''),
        "detailed_comparison": state.get('detailed_comparison', ''),
        "selected_design_info": design_info,
        "user_query": state.get('user_query', 'FTO 리포트를 작성해줘')
    })
    state['final_report'] = report
    print(f"  리포트 완료 ({len(report)}자)")
    return state


def general_question_node(state: GraphState) -> GraphState:
    print("[일반질문-GPT] 답변 생성 중...")
    history = state.get('messages') or []
    turn = len(history) // 2 + 1
    print(f"  현재 {turn}턴 (히스토리 {len(history)}개 메시지)")

    messages = [
        {"role": "system", "content": (
            "당신은 디자인 특허 전문 어시스턴트입니다.\n"
            "- 디자인 검색이 필요하면 search_design_db 도구를 사용하세요.\n"
            "- 최신 정보, 웹 검색이 필요하면 web_search 도구를 사용하세요.\n"
            "- 이전 대화 내용을 참고하여 일관성 있게 답변하세요.\n"
            "- 답변은 친절하고 정확하게."
        )}
    ] + history + [
        {"role": "user", "content": state['text_query']}
    ]

    response = llm_with_tools.invoke(messages)

    if response.tool_calls:
        for tc in response.tool_calls:
            print(f"  Tool 호출: {tc['name']}({tc['args']})")
        tool_node = ToolNode(tools)
        tool_results = tool_node.invoke({"messages": [response]})
        messages.append(response)
        for msg in tool_results['messages']:
            messages.append(msg)
        final = llm.invoke(messages)
        answer = final.content

        called_tools = {tc['name'] for tc in response.tool_calls}
        if 'search_design_db' in called_tools:
            state['search_images'] = _search_image_results.copy()
    else:
        answer = response.content

    updated_history = history + [
        {"role": "user", "content": state['text_query']},
        {"role": "assistant", "content": answer},
    ]
    state['messages'] = updated_history
    state['general_answer'] = answer
    print("  답변 완료")
    return state


# ==================== 그래프 조립 ====================

def create_graph():
    workflow = StateGraph(GraphState)
    workflow.add_node("router", router_node)
    workflow.add_node("analyze_image", analyze_image_node)
    workflow.add_node("image_search", image_search_node)
    workflow.add_node("show_results_and_interrupt", show_results_node)
    workflow.add_node("detailed_compare", detailed_compare_node)
    workflow.add_node("generate_report", generate_report_node)
    workflow.add_node("general_question", general_question_node)

    workflow.set_entry_point("router")
    workflow.add_conditional_edges(
        "router", route_by_type,
        {'image': 'analyze_image', 'text': 'general_question'}
    )
    workflow.add_edge("analyze_image", "image_search")
    workflow.add_edge("image_search", "show_results_and_interrupt")
    workflow.add_edge("show_results_and_interrupt", "detailed_compare")
    workflow.add_edge("detailed_compare", "generate_report")
    workflow.add_edge("generate_report", END)
    workflow.add_edge("general_question", END)

    graph = workflow.compile(checkpointer=MemorySaver())
    return graph


# ==================== 메인 실행 ====================

graph = create_graph()

if __name__ == "__main__":
    print(f"ChromaDB 로드 완료: {image_collection.count()}개 디자인")
    print("그래프 생성 완료! (GPT 버전, 노드 7개, 분기 2갈래)")
    from design_chatbot_gpt import graph
    result = graph.invoke(
        {"input_type": "", "image_path": "", "text_query": "디자인 특허란?",
         "user_query": "디자인 특허란?", "base64_image": "", "input_analysis": "",
         "search_results": {}, "comparison_results": [], "selected_index": 0,
         "detailed_comparison": "", "final_report": "", "general_answer": "",
         "search_images": [], "messages": []},
        {"configurable": {"thread_id": "test-gpt"}}
    )
    print(result.get('general_answer', ''))
