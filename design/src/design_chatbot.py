"""
디자인 유사성 분석 챗봇

기능:
1. 이미지 → 유사 디자인 10개 검색 (CLIP + ChromaDB)
2. 사용자가 1개 선택 → 상세 비교 분석 (interrupt + VLM)
3. 최종 리포트 생성 (LLM)
4. 일반 질문 + 웹 검색 + DB 검색 (Tool)

그래프 구조 (2갈래):
    [입력] → [라우터]
      ├─ image ─→ [VLM분석] → [벡터검색] → ★interrupt(선택대기)★ → [상세비교] → [리포트] → END
      └─ text  ─→ [LLM + Tools(웹검색, DB검색)] → END
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
# config.py에서 경로 관리 (data/chroma-design/ → Docker/EC2 공유용)
# 기존: design/chroma_db  → 변경: data/chroma-design
CHROMA_DB     = None  # config import 후 설정 (아래 LLM 초기화 섹션에서)

# 벡터DB 유사 디자인 검색 결과 개수
N_RESULTS     = 15

# LangChain & LangGraph
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from langgraph.types import interrupt, Command  # interrupt: 사용자 개입 기능
from langgraph.checkpoint.memory import MemorySaver  # interrupt 사용시 필수
from langgraph.prebuilt import ToolNode

# 웹 검색
from langchain_tavily import TavilySearch

# 벡터DB
import chromadb
from rank_bm25 import BM25Okapi

# 기존 유틸 함수 재사용
from utils import (
    get_text_embedding,               # 텍스트 → CLIP 임베딩 (DB검색 Tool용)
    search_and_filter_similar_designs,# 벡터DB 검색 + 중복 필터링 (텍스트 Tool용)
    hybrid_retrieve,                  # Hybrid Retrieval (이미지 검색용)
    convert_to_sketch_query           # 쿼리 이미지 → 스케치 변환
)

# 기존 프롬프트 재사용
from prompts import (
    IMAGE_ANALYSIS_PROMPT,    # 이미지 형상 분석
    IMAGE_COMPARISON_PROMPT,  # 두 이미지 비교
    REPORT_PROMPT,            # 최종 리포트 생성
    FORMAT_ANALYSIS_PROMPT    # 분석 결과 포맷팅
)

from dotenv import load_dotenv
load_dotenv()

import config as design_config


# ==================== LLM & ChromaDB 초기화 ====================

if design_config.USE_RUNPOD:
    # RunPod 서버리스 VLM (Qwen2.5-VL-7B-Instruct)
    llm = ChatOpenAI(
        model=design_config.VLLM_MODEL_NAME,
        openai_api_base=design_config.RUNPOD_DESIGN_BASE_URL,
        openai_api_key=design_config.RUNPOD_API_KEY,
        temperature=0,
        timeout=design_config.VLLM_TIMEOUT,
    )
    print(f"[design] VLM 모드: {design_config.VLLM_MODEL_NAME}")
else:
    # GPT 폴백 (보안 정책: 비활성화 — 외부 API로 데이터 유출 방지)
    # llm = ChatOpenAI(model=design_config.GPT_FALLBACK_MODEL, temperature=0)
    # print(f"[design] GPT 폴백 모드: {design_config.GPT_FALLBACK_MODEL}")
    raise RuntimeError(
        "[design] RUNPOD_API_KEY 또는 RUNPOD_DESIGN_BASE_URL 미설정. "
        ".env 파일을 확인하세요."
    )

output_parser = StrOutputParser()

# Docker: HttpClient (CHROMA_IMAGE_HOST 설정 시), 로컬: PersistentClient
_chroma_host = os.environ.get("CHROMA_IMAGE_HOST")
_chroma_port = int(os.environ.get("CHROMA_IMAGE_PORT", "8000"))
if _chroma_host:
    chroma_client = chromadb.HttpClient(host=_chroma_host, port=_chroma_port)
    print(f"[design] ChromaDB HttpClient: {_chroma_host}:{_chroma_port}")
else:
    CHROMA_DB = design_config.CHROMA_DB_PATH
    chroma_client = chromadb.PersistentClient(path=CHROMA_DB)
    print(f"[design] ChromaDB PersistentClient: {CHROMA_DB}")

# 컬렉션 목록 확인 후 'design' 컬렉션 로드
_collections = [col.name for col in chroma_client.list_collections()]
print(f"[design] 사용 가능한 컬렉션: {_collections}")
_design_col_name = "design" if "design" in _collections else (_collections[0] if _collections else "design")
image_collection = chroma_client.get_collection(name=_design_col_name)
print(f"[design] 컬렉션 '{_design_col_name}' 로드: {image_collection.count()}개")

# BM25 인덱스 빌드 (전체 코퍼스 1회 로드)
_all          = image_collection.get(include=["metadatas"])
all_ids       = _all["ids"]
all_metadatas = _all["metadatas"]
corpus_tokens = [
    re.split(r"\s+", (m.get("articleName", "") + " " + m.get("designSummary", "")).strip())
    for m in all_metadatas
]
bm25 = BM25Okapi(corpus_tokens)


# ==================== State 정의 ====================
# State = 노드 간에 주고받는 데이터 구조(스키마)
# 모든 노드가 같은 state 딕셔너리를 받아서 읽고/업뎃,수정하고/다음 노드로 넘김

class GraphState(TypedDict):
    """그래프 전체에서 공유되는 상태"""

    #입력 관련 필드
    input_type: str          # "image" | "text"
    image_path: str          # 사용자가 입력한 이미지 경로
    text_query: str          # 텍스트 질문
    user_query: str          # 사용자 질문
    base64_image: str        # base64 인코딩된 입력 이미지

    # 이미지 검색&분석 관련 필드
    input_analysis: str              # VLM 분석 결과
    search_results: Dict[str, Any]   # 벡터DB 검색 원본
    comparison_results: List[Dict]   # 검색 원본을 깔끔하게 정리 -> 최종 유사 디자인 목록
    selected_index: int              # 사용자가 선택한 디자인 번호
    detailed_comparison: str         # 선택한 디자인 vlm 상세 비교 결과
    final_report: str                # 최종 리포트

    # 텍스트 관련 필드
    general_answer: str              # 일반 질문 답변
    search_images: List[Dict]        # DB 검색 시 추출한 이미지 URL 목록

    # 멀티턴: 대화 히스토리
    messages: List[Dict]             # [{"role": "user"|"assistant", "content": "..."}]


# ==================== Tool 정의 ====================

# search_design_db 호출 시 이미지 URL을 임시 저장하는 모듈 레벨 변수
# (general_question_node에서 읽어 state['search_images']에 저장)
_search_image_results: List[Dict] = []

# Tool 1: 웹 검색 (TAVILY_API_KEY 필요!)
@tool
def web_search(query: str) -> str:
    """웹 검색 tool. 특허 뉴스, 법률 정보, 일반 질문 등에 활용됨."""
    search = TavilySearch(max_results=3)
    results = search.invoke(query)

    # 결과 정리
    output = ""
    for r in results:
        if isinstance(r, dict):
            output += f"- {r.get('content', '')}\n  출처: {r.get('url', '')}\n\n"
        else:
            output += f"- {r}\n\n"
    return output


# Tool 2: 디자인 DB 검색 (텍스트 → CLIP 임베딩 → ChromaDB)
@tool
def search_design_db(query: str) -> str:
    """사용자가 자연어로 유사 디자인을 검색할 경우 사용되는 tool.
      예: 둥근 펌프 용기, 사각형 병"""
    global _search_image_results
    _search_image_results = []  # 매 호출마다 초기화

    # 텍스트 → CLIP 임베딩
    embedding, translated = get_text_embedding(query, translate_korean=True)
    if embedding is None:
        return "임베딩 생성 실패"

    # 벡터DB 검색
    results = search_and_filter_similar_designs(image_collection, embedding, n_results=N_RESULTS)

    # 결과 정리 + 이미지 URL 캡처
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
        # 이미지 URL이 있으면 모듈 변수에 임시 저장
        if meta.get('imagePath'):
            _search_image_results.append({
                'application_number': meta.get('applicationNumber', ''),
                'last_disposition_date': meta.get('lastDispositionDate', ''),
                'image_path': meta.get('imagePath', ''),
            })
    return output


# Tool 목록 & LLM 바인딩
# - GPT: bind_tools로 정확한 tool calling 지원
# - VLM (RunPod): tool calling 미지원 → fallback 사용 (448~474줄에서 텍스트 키워드로 직접 호출)
tools = [web_search, search_design_db]
if design_config.USE_RUNPOD:
    llm_with_tools = llm
else:
    llm_with_tools = llm.bind_tools(tools)


# ==================== 노드 함수 정의 ====================

# ===== 노드 0: router (2갈래: image / text) =====

def router_node(state: GraphState) -> GraphState:
    """입력 타입 판단: 이미지가 있으면 image, 아니면 text"""

    if state.get('image_path') and os.path.exists(state['image_path']):
        state['input_type'] = 'image'
        print("[router] 이미지 입력 → 유사 디자인 검색 경로로 라우팅합니다. ")
    else:
        state['input_type'] = 'text'
        print("[router] 텍스트 입력 → LLM + Tools 경로로 라우팅합니다. ")
    return state


def route_by_type(state: GraphState) -> str:
    """라우터 분기: 'image' 또는 'text'"""
    return state['input_type']


# ===== 이미지 경로: VLM 분석 + 벡터 검색 =====

def analyze_image_node(state: GraphState) -> GraphState:
    """이미지를 VLM으로 형상 분석"""
    print("[VLM분석] 입력 이미지 분석 중 ~")

    # 이미지 → base64
    with open(state['image_path'], "rb") as f:
        b64 = base64.b64encode(f.read()).decode('utf-8')
    url = f"data:image/jpeg;base64,{b64}"

    # VLM 분석 (IMAGE_ANALYSIS_PROMPT 사용)
    chain = IMAGE_ANALYSIS_PROMPT | llm | output_parser
    analysis = chain.invoke({"image_url": url}) # vlm 분석 결과가 나올것

    # JSON 분석 결과를 사용자 친화적인 텍스트로 변환
    format_chain = FORMAT_ANALYSIS_PROMPT | llm | output_parser
    formatted_analysis = format_chain.invoke({"analysis_json": analysis})

    # 상태 update
    state['base64_image'] = url
    state['input_analysis'] = formatted_analysis
    print(f"  분석 완료 ({len(analysis)}자)")
    return state


def image_search_node(state: GraphState) -> GraphState:
    """입력 이미지로 Hybrid Retrieval (Dense + BM25 재랭킹) 유사 디자인 검색"""
    print("[벡터검색] 유사 디자인 검색 중...")

    # 쿼리 이미지 → 스케치 변환 (DB 임베딩과 동일한 전처리 적용)
    pil_image    = PILImage.open(state['image_path']).convert('RGB')
    sketch_image = convert_to_sketch_query(pil_image)

    # 스케치 이미지를 임시 파일로 저장 후 hybrid_retrieve에 전달
    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
        sketch_image.save(tmp.name)
        sketch_path = tmp.name

    try:
        # Hybrid Retrieval (Dense → BM25 재랭킹 → 출원번호 중복제거 → top_k)
        hybrid_results = hybrid_retrieve(
            sketch_path,
            image_collection,
            bm25,
            all_ids,
            all_metadatas,
        )
    finally:
        os.unlink(sketch_path)  # 임시 파일 삭제

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


# ===== interrupt: 사용자 선택 대기 =====

def show_results_node(state: GraphState) -> GraphState:
    """검색 결과 10개를 보여주고, 사용자 선택을 기다림 (interrupt)"""
    print("\n" + "="*50)
    print("유사 디자인 검색 결과")
    print("="*50)

    for comp in state['comparison_results']:
        print(f"  [{comp['index']}] 출원번호: {comp['application_number']}",
              f"상품명: {comp['article_name']}, "
              f"등록상태: {comp['admst_stat']}, "
              f"점수: {comp['hybrid_score']:.4f}")

    # ★ interrupt: 여기서 그래프 실행이 멈추고, 사용자 입력을 기다림 ★
    selected = interrupt({
        "message": "상세 비교할 디자인 번호를 선택하세요! VLM이 선택한 디자인과 입력 디자인을 비교 분석해, 자세한 유사점/차이점을 알려드립니다.",
        "options": [comp['index'] for comp in state['comparison_results']]
    })

    state['selected_index'] = int(selected) # 선택된 디자인 번호 저장

    print(f"\n  → {selected}번 디자인 선택됨!")
    return state


# ===== 상세 비교 & 리포트 =====

def detailed_compare_node(state: GraphState) -> GraphState:
    """선택한 디자인 1개와 입력 디자인을 VLM 상세 비교"""

    print("[상세비교] 분석 중...")

    # comparison_results에서 선택한 디자인 찾기
    selected = next(
        (c for c in state['comparison_results'] if c['index'] == state['selected_index']),
        None
    )

    # 만약 선택한 디자인 번호가 존재하지 않거나 이미지 경로가 없을 시 오류 메시지 저장 후 종료
    if not selected or not selected['image_path']:
        state['detailed_comparison'] = "비교 대상 이미지를 찾을 수 없습니다."
        return state

    # 비교 대상 이미지 → base64 (URL 또는 로컬 파일 모두 지원)
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

    # 두 이미지 VLM 비교 (IMAGE_COMPARISON_PROMPT 사용)
    chain = IMAGE_COMPARISON_PROMPT | llm | output_parser
    result = chain.invoke({
        "input_image_url": state['base64_image'], # 입력 이미지
        "comparison_image_url": comp_url # 비교 대상 이미지
    })

    state['detailed_comparison'] = result # 비교 결과 state 저장

    print("  상세 비교 완료!")
    return state


def generate_report_node(state: GraphState) -> GraphState:
    """상세 비교 결과로 FTO 리포트 생성"""
    print("[리포트] 생성 중...")

    # comparison_results에서 선택한 디자인 정보 찾기
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

    # 리포트 생성
    chain = REPORT_PROMPT | llm | output_parser
    report = chain.invoke({
        "input_analysis": state.get('input_analysis', ''), # 입력 이미지 분석 결과
        "detailed_comparison": state.get('detailed_comparison', ''), # VLM 상세 비교 결과
        "selected_design_info": design_info, # 비교대상 디자인 정보
        "user_query": state.get('user_query', 'FTO 리포트를 작성해줘') # 사용자 요청
    })

    LEGAL_NOTICE = (
        "\n\n---\n"
        "## ⚠️ 법적 고지\n"
        "> **본 분석 결과는 AI 기반 자동화 도구에 의해 생성된 참고 자료이며, "
        "법적 자문이나 변리사의 공식 의견을 대체하지 않습니다. "
        "최종 제품 출시 전 반드시 변리사 또는 특허 변호사와 상담하시기 바랍니다.**"
    )
    state['final_report'] = report + LEGAL_NOTICE
    print(f"  리포트 완료 ({len(state['final_report'])}자)")
    return state


# ===== 텍스트 경로: 일반 질문 (LLM + Tools) =====

def general_question_node(state: GraphState) -> GraphState:
    """LLM이 필요에 따라 web_search, search_design_db Tool을 사용하여 답변 (멀티턴 지원)"""

    print("[일반질문] 답변 생성 중...")

    # 이전 대화 히스토리 가져오기
    history = state.get('messages') or []
    turn = len(history) // 2 + 1
    print(f"  현재 {turn}턴 (히스토리 {len(history)}개 메시지)")

    # system + 히스토리 + 현재 질문 순서로 구성
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

    # llm이 질문을 보고 tool을 쓸지 말지 스스로 판단
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

        # search_design_db 호출 시 캡처된 이미지 URL을 state에 저장
        called_tools = {tc['name'] for tc in response.tool_calls}
        if 'search_design_db' in called_tools:
            state['search_images'] = _search_image_results.copy()

    else:
        # Fallback: Qwen2.5-VL이 tool_calls JSON 대신 content에 도구 이름을 텍스트로
        # 언급하는 경우 직접 도구를 호출하고 결과를 LLM에 전달
        content = response.content
        tool_result = None

        _web_kw  = ['통계', '최신 뉴스', '트렌드', '현황', '출원 건수', '최근 동향', '출원 통계']

        if "search_design_db" in content:
            print(f"  [Fallback] search_design_db 직접 호출")
            tool_result = search_design_db.invoke({"query": state['text_query']})

        elif ("web_search" in content or "웹 검색" in content
              or any(kw in state['text_query'] for kw in _web_kw)):
            print(f"  [Fallback] web_search 직접 호출")
            tool_result = web_search.invoke({"query": state['text_query']})

        if tool_result:
            # 모델의 "결과 없음" 응답을 이어받지 않도록 시스템+쿼리만 남기고 결과 전달
            summary_messages = [
                messages[0],  # system 메시지
                {"role": "user", "content": state['text_query']},
                {"role": "assistant", "content": "도구로 검색을 완료했습니다."},
                {"role": "user", "content": f"검색 결과입니다. 반드시 아래 결과를 사용해서 답변하세요:\n\n{tool_result}"},
            ]
            final = llm.invoke(summary_messages)
            answer = final.content
        else:
            answer = content

    # 대화 히스토리 업데이트 (user + assistant 추가)
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
    """
    그래프 생성 (2갈래)

    image: 라우터 → VLM분석 → 벡터DB검색 → interrupt → 상세비교 → 리포트 → END
    text:  라우터 → 일반질문(+Tools) → END
    """
    workflow = StateGraph(GraphState)

    # 노드 등록
    # add_node(노드명, 함수)
    workflow.add_node("router", router_node)
    workflow.add_node("analyze_image", analyze_image_node)
    workflow.add_node("image_search", image_search_node)
    workflow.add_node("show_results_and_interrupt", show_results_node)       # interrupt 포함
    workflow.add_node("detailed_compare", detailed_compare_node)
    workflow.add_node("generate_report", generate_report_node)
    workflow.add_node("general_question", general_question_node)

    # 시작점
    workflow.set_entry_point("router")

    # 엣지 추가
    # 라우터 → 2갈래 분기
    workflow.add_conditional_edges(  # 조건부 분기
        "router",
        route_by_type,
        {
            'image': 'analyze_image',       # 이미지면 → VLM 분석
            'text': 'general_question'      # 텍스트면 → LLM + Tools
        }
    )

    # 이미지 경로
    workflow.add_edge("analyze_image", "image_search")
    workflow.add_edge("image_search", "show_results_and_interrupt")
    workflow.add_edge("show_results_and_interrupt", "detailed_compare")
    workflow.add_edge("detailed_compare", "generate_report")
    workflow.add_edge("generate_report", END)

    # 텍스트 경로
    workflow.add_edge("general_question", END)

    # 컴파일 (MemorySaver: interrupt에 필수)
    graph = workflow.compile(checkpointer=MemorySaver())
    return graph


# ==================== 실행 함수 ====================

def run_chatbot(image_path=None, text_query=None, user_query="이 제품과 유사한 디자인을 분석해줘"):
    """
    챗봇 실행

    이미지 검색:  run_chatbot(image_path="path/to/image.jpg")
    일반 질문:    run_chatbot(text_query="디자인 특허란?")
    DB 검색:     run_chatbot(text_query="펌프형 용기 디자인 찾아줘")
    웹 검색:     run_chatbot(text_query="2024년 디자인 특허 트렌드")
    """
    # 초기 상태
    initial_state = {
        "input_type": "",
        "image_path": image_path or "",
        "text_query": text_query or "",
        "user_query": user_query,
        "base64_image": "",
        "input_analysis": "",
        "search_results": {},
        "comparison_results": [],
        "selected_index": 0,
        "detailed_comparison": "",
        "final_report": "",
        "general_answer": "",
        "search_images": [],
        "messages": [],
    }

    config = {"configurable": {"thread_id": "session-1"}}

    print("\n" + "="*60)
    print("디자인 유사성 분석 챗봇 v3")
    print("="*60)

    # 1단계: 그래프 실행 (이미지면 interrupt에서 멈춤)
    result = graph.invoke(initial_state, config)

    # 텍스트 경로면 바로 답변 출력 후 종료
    if result.get('general_answer'):
        print("\n" + "="*60)
        print(result['general_answer'])
        print("="*60)
        return result

    # 2단계: 이미지 경로 → interrupt에서 멈춤 → 사용자 선택
    user_choice = input("\n번호 입력 > ")

    # 3단계: 선택값으로 그래프 재개
    result = graph.invoke(Command(resume=user_choice), config)

    # 리포트 출력
    print("\n" + "="*60)
    print("최종 FTO 리포트")
    print("="*60)
    print(result.get('final_report', '리포트 생성 실패'))

    return result


# ==================== 메인 실행 ====================

# 그래프 생성
graph = create_graph()

if __name__ == "__main__":
    print(f"ChromaDB 로드 완료: {image_collection.count()}개 디자인")
    print("그래프 생성 완료! (노드 7개, 분기 2갈래)")
    result = run_chatbot(text_query="디자인 특허란?")
