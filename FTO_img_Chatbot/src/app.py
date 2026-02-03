# src/app.py

from __future__ import annotations
import sys
import tempfile
import time
import datetime
from pathlib import Path
from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor
from typing import List, Tuple, Optional

import streamlit as st
import pandas as pd
import numpy as np
from htbuilder import div, styles
from htbuilder.units import rem

# 프로젝트 경로 설정
sys.path.insert(0, str(Path(__file__).parent))

from config import Config
from io_utils import build_index_by_key, load_embeddings_npz
from embedder import OpenCLIPEmbedder
from similarity import retrieve_similar, SimilarItem
from llm_explain import LLMExplainer
from report import build_markdown_report


# ============================================================
# 페이지 설정
# ============================================================
st.set_page_config(
    page_title="Image Similarity AI Assistant",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# 상수 및 설정
# ============================================================
HISTORY_LENGTH = 10
MIN_TIME_BETWEEN_REQUESTS = datetime.timedelta(seconds=1)

SUGGESTIONS = {
    ":blue[:material/gavel:] 특허를 침해하나요?": (
        "이 제품(아이디어)이 기존 특허를 침해하나요?"
    ),
    ":green[:material/warning:] 소송 가능성 알려주세요": (
        "이미 등록된 특허인데, 나중에 소송당할 수 있나요?"
    ),
    ":orange[:material/public:] 해외 특허가 국내에 영향이 있나요?": (
        "해외 특허도 국내에서 문제가 되나요?"
    ),
    ":violet[:material/description:] 특허 문서 보는 방법 알려주세요.": (
        "특허 문서가 너무 어려운데, 뭘 봐야 하나요?"
    ),
}

INSTRUCTIONS = """
You are a helpful AI assistant specialized in image similarity analysis.
Your role is to:
1. Help users understand image similarity results
2. Explain OpenCLIP embeddings and cosine similarity
3. Provide guidance on interpreting similarity scores
4. Answer questions about the analysis process

Use markdown for formatting. Be clear and educational.
Assume the user may be new to computer vision concepts.
"""

executor = ThreadPoolExecutor(max_workers=3)


# ============================================================
# 캐시된 리소스 로드
# ============================================================
@st.cache_resource
def load_config() -> Config:
    """Config 로드 (NPZ 차원 자동 감지 포함)."""
    return Config()


@st.cache_resource
def load_embedder(model_name: str, pretrained: str, device: str) -> OpenCLIPEmbedder:
    """자동 감지된 모델로 Embedder 생성."""
    return OpenCLIPEmbedder(model_name, pretrained, device)


@st.cache_resource
def load_data(_cfg: Config):
    metadata_idx = build_index_by_key(_cfg.metadata_jsonl, key_field="id")
    documents_idx = build_index_by_key(_cfg.documents_jsonl, key_field="id")
    ref_ids, ref_emb = load_embeddings_npz(_cfg.embeddings_npz)
    return metadata_idx, documents_idx, ref_ids, ref_emb


def get_explainer(_cfg: Config) -> LLMExplainer:
    return LLMExplainer(model=_cfg.llm_model, base_url=_cfg.ollama_base_url)


# ============================================================
# 핵심: 이미지 임베딩 및 유사도 계산 함수
# ============================================================
def embed_user_image(
    uploaded_file,
    embedder: OpenCLIPEmbedder,
) -> Tuple[np.ndarray, dict]:
    """
    유저가 업로드한 이미지를 OpenCLIP으로 임베딩.
    """
    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
        tmp.write(uploaded_file.getvalue())
        tmp_path = Path(tmp.name)

    try:
        embedding = embedder.embed_image_path(tmp_path, normalize=True)

        info = {
            "filename": uploaded_file.name,
            "embedding_dim": embedding.shape[0],
            "embedding_norm": float(np.linalg.norm(embedding)),
            "model": f"{embedder.model_name}/{embedder.pretrained}",
        }

        return embedding, info

    finally:
        tmp_path.unlink(missing_ok=True)


def validate_dimensions(user_embedding: np.ndarray, ref_emb: np.ndarray) -> Tuple[bool, str]:
    """임베딩 차원 검증."""
    user_dim = user_embedding.shape[0]
    ref_dim = ref_emb.shape[1]

    if user_dim != ref_dim:
        error_msg = (
            f"❌ 임베딩 차원 불일치!\n\n"
            f"- 유저 이미지: **{user_dim}차원**\n"
            f"- 참조 데이터: **{ref_dim}차원**\n\n"
            f"모델 자동 감지가 실패했을 수 있습니다. "
            f"config.py를 확인해주세요."
        )
        return False, error_msg

    return True, ""


def compute_all_similarities(
    user_embedding: np.ndarray,
    ref_ids: np.ndarray,
    ref_emb: np.ndarray,
) -> pd.DataFrame:
    """
    유저 임베딩과 모든 참조 이미지 간의 코사인 유사도 계산.
    """
    scores = ref_emb @ user_embedding

    df = pd.DataFrame({
        "image_id": ref_ids,
        "cosine_similarity": scores,
    })

    df = df.sort_values("cosine_similarity", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1

    df["strength"] = df["cosine_similarity"].apply(
        lambda x: "🟢 Strong" if x >= 0.7
        else "🟡 Moderate" if x >= 0.5
        else "🟠 Weak" if x >= 0.3
        else "🔴 Very Weak"
    )

    return df


def filter_similar_images(
    similarity_df: pd.DataFrame,
    min_similarity: float = 0.0,
    top_k: Optional[int] = None,
) -> pd.DataFrame:
    """유사도 임계값과 top_k로 필터링."""
    filtered = similarity_df[similarity_df["cosine_similarity"] >= min_similarity].copy()

    if top_k is not None and top_k > 0:
        filtered = filtered.head(top_k)

    return filtered


def get_similar_items_with_metadata(
    filtered_df: pd.DataFrame,
    metadata_idx: dict,
    documents_idx: dict,
) -> List[SimilarItem]:
    """필터링된 결과에 메타데이터와 문서 정보 추가."""
    items = []
    for _, row in filtered_df.iterrows():
        sid = str(row["image_id"])
        items.append(
            SimilarItem(
                reference_image_id=sid,
                cosine_similarity=float(row["cosine_similarity"]),
                metadata=metadata_idx.get(sid),
                document=documents_idx.get(sid),
            )
        )
    return items


# ============================================================
# 통합 분석 함수
# ============================================================
def analyze_image_full(
    uploaded_file,
    cfg: Config,
    embedder: OpenCLIPEmbedder,
    metadata_idx: dict,
    documents_idx: dict,
    ref_ids: np.ndarray,
    ref_emb: np.ndarray,
    min_similarity: float,
    top_k: Optional[int],
    use_llm: bool,
) -> dict:
    """이미지 분석 전체 파이프라인."""
    result = {}

    # 1. 이미지 임베딩
    user_embedding, embedding_info = embed_user_image(uploaded_file, embedder)
    result["embedding_info"] = embedding_info
    result["user_embedding"] = user_embedding

    # 2. 차원 검증
    is_valid, error_msg = validate_dimensions(user_embedding, ref_emb)
    if not is_valid:
        result["error"] = error_msg
        result["user_dim"] = user_embedding.shape[0]
        result["ref_dim"] = ref_emb.shape[1]
        return result

    # 3. 코사인 유사도 계산
    all_similarities = compute_all_similarities(user_embedding, ref_ids, ref_emb)
    result["all_similarities"] = all_similarities

    # 4. 통계 정보
    result["stats"] = {
        "total_references": len(ref_ids),
        "embedding_dim": user_embedding.shape[0],
        "max_similarity": float(all_similarities["cosine_similarity"].max()),
        "min_similarity": float(all_similarities["cosine_similarity"].min()),
        "mean_similarity": float(all_similarities["cosine_similarity"].mean()),
        "std_similarity": float(all_similarities["cosine_similarity"].std()),
        "above_threshold": int((all_similarities["cosine_similarity"] >= min_similarity).sum()),
    }

    # 5. 필터링
    filtered_df = filter_similar_images(all_similarities, min_similarity, top_k)
    result["filtered_similarities"] = filtered_df

    # 6. 메타데이터 추가
    similar_items = get_similar_items_with_metadata(filtered_df, metadata_idx, documents_idx)
    result["similar_items"] = similar_items

    # 7. LLM 설명
    result["explanation"] = None
    if use_llm and similar_items:
        try:
            explainer = get_explainer(cfg)
            llm_input = [
                {
                    "reference_image_id": it.reference_image_id,
                    "cosine_similarity": round(it.cosine_similarity, 4),
                    "metadata": it.metadata,
                    "document": it.document,
                }
                for it in similar_items[:20]
            ]
            result["explanation"] = explainer.explain(
                user_image_id=uploaded_file.name,
                items=llm_input,
            )
        except Exception as e:
            result["explanation"] = {"error": str(e)}

    return result


# ============================================================
# 유틸리티 함수
# ============================================================
def find_image_path(image_dir: Path, image_id: str, metadata: dict = None) -> Optional[Path]:
    """
    metadata의 image_local_path를 사용하여 이미지 파일 경로 찾기.
    
    metadata 구조: {"metadata": {"image_local_path": "img/xxx.JPG", ...}}
    """
    if not image_dir.exists():
        return None
    
    # metadata에서 image_local_path 사용
    if metadata and isinstance(metadata, dict):
        inner_meta = metadata.get("metadata", metadata)
        if isinstance(inner_meta, dict) and inner_meta.get("image_local_path"):
            local_path = inner_meta["image_local_path"]
            
            # "img/xxx.JPG" 형식에서 파일명만 추출
            filename = Path(local_path).name
            candidate = image_dir / filename
            if candidate.exists():
                return candidate
    
    # fallback: image_id의 "::"를 "__"로 변환
    filename_base = image_id.replace("::", "__")
    for ext in ["JPG", "jpg", "png", "jpeg"]:
        candidate = image_dir / f"{filename_base}.{ext}"
        if candidate.exists():
            return candidate
    
    return None


def get_application_number(metadata: dict) -> str:
    """메타데이터에서 출원번호 추출."""
    if not metadata or not isinstance(metadata, dict):
        return ""
    inner_meta = metadata.get("metadata", metadata)
    if isinstance(inner_meta, dict):
        return inner_meta.get("applicationNumber", "")
    return ""


def history_to_text(chat_history):
    return "\n".join(f"[{h['role']}]: {h['content']}" for h in chat_history)


def build_prompt(**kwargs):
    prompt = []
    for name, contents in kwargs.items():
        if contents:
            prompt.append(f"<{name}>\n{contents}\n</{name}>")
    return "\n".join(prompt)


def clean_xml_tags(text: str) -> str:
    """
    XML 태그를 제거하고 자연스러운 문장으로 변환.
    예: '<P N="1">내용</P>' -> '내용'
    """
    import re
    if not text:
        return text
    
    # <P N="숫자">...</P> 형식의 태그 제거
    cleaned = re.sub(r'<P\s+N="?\d+"?>(.+?)</P>', r'\1', text, flags=re.DOTALL)
    
    # 기타 XML 태그 제거
    cleaned = re.sub(r'<[^>]+>', '', cleaned)
    
    # 여러 공백을 하나로
    cleaned = re.sub(r'\s+', ' ', cleaned)
    
    return cleaned.strip()


def format_document_text(doc_text: str) -> str:
    """
    document 텍스트에서 '요점' 필드의 XML 태그를 제거하고 자연스럽게 포맷.
    """
    if not doc_text:
        return doc_text
    
    lines = doc_text.split('\n')
    formatted_lines = []
    
    for line in lines:
        # '요점:' 또는 '설명:' 필드에서 XML 태그 제거
        if line.startswith('요점:') or line.startswith('설명:'):
            # 필드명과 내용 분리
            colon_idx = line.find(':')
            if colon_idx != -1:
                field_name = line[:colon_idx + 1]
                field_content = line[colon_idx + 1:].strip()
                cleaned_content = clean_xml_tags(field_content)
                formatted_lines.append(f"{field_name} {cleaned_content}")
            else:
                formatted_lines.append(clean_xml_tags(line))
        else:
            formatted_lines.append(line)
    
    return '\n'.join(formatted_lines)


# ============================================================
# 사이드바
# ============================================================
def render_sidebar(cfg: Config):
    st.sidebar.title("⚙️ Settings")

    # 모델 정보 표시
    st.sidebar.markdown("### 🤖 Model Info")
    st.sidebar.info(
        f"**모델**: {cfg.model_name}\n\n"
        f"**가중치**: {cfg.pretrained}\n\n"
        f"**임베딩 차원**: {cfg.embedding_dim or 'N/A'}"
    )

    st.sidebar.markdown("### 🔍 Search Parameters")

    top_k = st.sidebar.slider(
        "Top K Results",
        min_value=5,
        max_value=100,
        value=30,
        step=5,
        help="상위 K개 결과만 표시",
    )

    min_similarity = st.sidebar.slider(
        "Min Similarity",
        min_value=0.0,
        max_value=1.0,
        value=0.5,
        step=0.05,
        help="최소 코사인 유사도 임계값",
    )

    return_all = st.sidebar.checkbox(
        "Return All Similar Images",
        value=False,
        help="임계값 이상의 모든 이미지 반환",
    )

    st.sidebar.markdown("### 🤖 AI Options")

    use_llm = st.sidebar.checkbox(
        "Enable AI Explanation",
        value=True,
        help="로컬 LLM으로 결과 설명 생성",
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📊 Display Options")

    show_histogram = st.sidebar.checkbox("Show Histogram", value=True)
    show_all_data = st.sidebar.checkbox("Show Full Table", value=False)

    return {
        "top_k": top_k if not return_all else None,
        "min_similarity": min_similarity,
        "return_all": return_all,
        "use_llm": use_llm,
        "show_histogram": show_histogram,
        "show_all_data": show_all_data,
    }


# ============================================================
# 피드백 / 다이얼로그
# ============================================================
def show_feedback_controls(message_index):
    st.write("")
    with st.popover("이 답변이 도움이 되었나요?"):
        with st.form(key=f"feedback-{message_index}", border=False):
            st.markdown(":small[평점]")
            rating = st.feedback(options="stars")
            details = st.text_area("추가 의견 (선택)")
            if st.form_submit_button("피드백 보내기"):
                st.success("감사합니다!")


@st.dialog("사용 안내")
def show_disclaimer_dialog():
    st.caption("""
        **이미지 유사도 분석 파이프라인:**
        1. 업로드 이미지 → OpenCLIP 임베딩
        2. 참조 이미지들과 코사인 유사도 계산
        3. 임계값 이상의 유사 이미지 반환
        4. (선택) LLM으로 결과 설명

        업로드된 이미지는 분석 후 즉시 삭제됩니다.
    """)


# ============================================================
# 결과 표시 함수
# ============================================================
def display_analysis_results(analysis_result: dict, settings: dict):
    """분석 결과 표시."""

    # 에러 체크
    if "error" in analysis_result:
        st.error(analysis_result["error"])
        return

    stats = analysis_result["stats"]
    filtered_df = analysis_result["filtered_similarities"]
    all_df = analysis_result["all_similarities"]
    embedding_info = analysis_result["embedding_info"]

    # # 임베딩 정보
    # st.markdown("### 📊 임베딩 정보")
    # col1, col2, col3, col4 = st.columns(4)
    # col1.metric("파일명", embedding_info["filename"])
    # col2.metric("임베딩 차원", embedding_info["embedding_dim"])
    # col3.metric("모델", embedding_info["model"].split("/")[0])
    # col4.metric("벡터 노름", f"{embedding_info['embedding_norm']:.4f}")

    # st.markdown("---")

    # # 통계 요약
    # st.markdown("### 📈 유사도 통계")
    # col1, col2, col3, col4 = st.columns(4)
    # col1.metric("전체 참조 이미지", stats["total_references"])
    # col2.metric("임계값 이상", stats["above_threshold"])
    # col3.metric("최대 유사도", f"{stats['max_similarity']:.4f}")
    # col4.metric("평균 유사도", f"{stats['mean_similarity']:.4f}")

    # # 히스토그램
    # if settings["show_histogram"]:
    #     st.markdown("### 📊 유사도 분포")
    #     try:
    #         import plotly.express as px
    #         fig = px.histogram(
    #             all_df,
    #             x="cosine_similarity",
    #             nbins=50,
    #             title="코사인 유사도 분포",
    #         )
    #         fig.add_vline(
    #             x=settings["min_similarity"],
    #             line_dash="dash",
    #             line_color="red",
    #             annotation_text=f"Threshold: {settings['min_similarity']}",
    #         )
    #         st.plotly_chart(fig, use_container_width=True)
    #     except ImportError:
    #         st.warning("Plotly가 설치되지 않아 히스토그램을 표시할 수 없습니다.")

    # st.markdown("---")

    # 필터링된 결과
    st.markdown(f"### 🎯 유사 이미지 결과 ({len(filtered_df)}개)")

    if len(filtered_df) == 0:
        st.warning("⚠️ 임계값 이상의 유사한 이미지가 없습니다.")
        return

    # similar_items에서 출원번호 매핑 생성
    similar_items = analysis_result.get("similar_items", [])
    app_num_map = {item.reference_image_id: get_application_number(item.metadata) for item in similar_items}
    
    display_df = filtered_df[["rank", "image_id", "cosine_similarity"]].copy()
    display_df["출원번호"] = display_df["image_id"].apply(lambda x: app_num_map.get(str(x), ""))
    display_df = display_df[["rank", "출원번호", "cosine_similarity"]]
    display_df.columns = ["순위", "출원번호", "유사도"]
    display_df["유사도"] = display_df["유사도"].apply(lambda x: f"{x:.4f}")

    st.dataframe(display_df, use_container_width=True, hide_index=True, height=400)

    # 다운로드 버튼
    col1, col2 = st.columns(2)
    with col1:
        csv = filtered_df[["rank", "image_id", "cosine_similarity"]].to_csv(index=False)
        st.download_button("📥 필터링 결과 (CSV)", csv, "filtered_results.csv", "text/csv")
    with col2:
        csv_all = all_df[["rank", "image_id", "cosine_similarity"]].to_csv(index=False)
        st.download_button("📥 전체 결과 (CSV)", csv_all, "all_results.csv", "text/csv")

    # 전체 테이블
    if settings["show_all_data"]:
        st.markdown("---")
        st.markdown("### 📋 전체 유사도 테이블")
        st.dataframe(all_df, use_container_width=True, hide_index=True, height=600)

    # LLM 설명
    explanation = analysis_result.get("explanation")
    if explanation and "error" not in explanation:
        st.markdown("---")
        st.markdown("### 🤖 AI 분석 설명")

        summary = explanation.get("summary", {})
        if summary.get("notes"):
            st.info(summary.get("notes"))

        ranking = explanation.get("ranking", [])
        for r in ranking[:10]:
            with st.expander(f"🖼️ {r.get('reference_image_id')} — {r.get('cosine_similarity', 0):.4f}"):
                st.markdown("**유사한 이유:**")
                for reason in r.get("why_similar", []) or []:
                    st.markdown(f"- {reason}")

    # 유사 이미지 카드 표시 (이미지 + document 정보)
    st.markdown("---")
    st.markdown("### 🖼️ 유사 이미지 상세 정보")
    
    similar_items = analysis_result.get("similar_items", [])
    cfg = load_config()
    
    # image_dir이 존재하지 않으면 현재 파일 기준으로 다시 설정
    image_dir = cfg.image_dir
    if not image_dir.exists():
        image_dir = Path(__file__).parent.parent / "data/img"
    
    # 3열로 이미지 카드 표시
    for i in range(0, min(len(similar_items), 12), 3):
        cols = st.columns(3)
        for j, col in enumerate(cols):
            idx = i + j
            if idx >= len(similar_items):
                break
            
            item = similar_items[idx]
            with col:
                # 이미지 찾기 및 표시
                image_id = item.reference_image_id
                
                image_path = find_image_path(image_dir, image_id, item.metadata)
                
                if image_path and image_path.exists():
                    st.image(str(image_path), caption=f"#{idx+1} {image_id}", width=100)
                else:
                    st.warning(f"이미지 없음: {image_id}")
                
                # 유사도 표시
                similarity = item.cosine_similarity
                strength = "🟢 강함" if similarity >= 0.7 else "🟡 보통" if similarity >= 0.5 else "🟠 약함"
                st.metric("유사도", f"{similarity:.4f}", delta=strength)
                
                # Document 정보 표시
                if item.document:
                    with st.expander("📄 디자인 정보"):
                        doc = item.document
                        # document 필드가 문자열인 경우 (텍스트 형태)
                        if isinstance(doc, dict) and "document" in doc:
                            doc_text = doc["document"]
                            # XML 태그 제거 및 자연스러운 문장으로 변환
                            formatted_text = format_document_text(doc_text.replace("\\n", "\n"))
                            st.markdown(formatted_text)
                        elif isinstance(doc, dict):
                            # 구조화된 딕셔너리인 경우
                            if doc.get("title"):
                                st.markdown(f"**제목**: {doc.get('title')}")
                            if doc.get("applicant"):
                                st.markdown(f"**출원인**: {doc.get('applicant')}")
                            if doc.get("registration_date"):
                                st.markdown(f"**등록일**: {doc.get('registration_date')}")
                            if doc.get("class_code"):
                                st.markdown(f"**분류코드**: {doc.get('class_code')}")
                            if doc.get("description"):
                                # 설명에도 XML 태그가 있을 수 있으므로 정리
                                cleaned_desc = clean_xml_tags(doc.get('description')[:200])
                                st.markdown(f"**설명**: {cleaned_desc}...")
                            # 추가 필드 표시
                            for key, value in doc.items():
                                if key not in ["title", "applicant", "registration_date", "class_code", "description", "id", "document"] and value:
                                    # 요점 필드 등에서 XML 태그 제거
                                    if isinstance(value, str):
                                        value = clean_xml_tags(value)
                                    st.markdown(f"**{key}**: {value}")
                        else:
                            # 문자열인 경우 XML 태그 제거 후 표시
                            formatted_text = format_document_text(str(doc))
                            st.markdown(formatted_text)
                
                # Metadata 정보 표시
                if item.metadata:
                    with st.expander("🏷️ 상품 데이터"):
                        meta = item.metadata
                        if isinstance(meta, dict):
                            inner_meta = meta.get("metadata", meta)
                            if isinstance(inner_meta, dict):
                                if inner_meta.get("articleName"):
                                    st.markdown(f"**제품명**: {inner_meta.get('articleName')}")
                                if inner_meta.get("applicationNumber"):
                                    st.markdown(f"**출원번호**: {inner_meta.get('applicationNumber')}")
                                if inner_meta.get("registrationNumber"):
                                    st.markdown(f"**등록번호**: {inner_meta.get('registrationNumber')}")
                                if inner_meta.get("LCCode"):
                                    st.markdown(f"**로카르노 분류**: {inner_meta.get('LCCode')}")
                                if inner_meta.get("design_id"):
                                    st.markdown(f"**디자인 ID**: {inner_meta.get('design_id')}")


def format_analysis_response(analysis_result: dict) -> str:
    """분석 결과를 마크다운으로 포맷."""
    if "error" in analysis_result:
        return analysis_result["error"]

    stats = analysis_result["stats"]
    filtered_df = analysis_result["filtered_similarities"]
    embedding_info = analysis_result["embedding_info"]
    similar_items = analysis_result.get("similar_items", [])
    
    # 출원번호 매핑 생성
    app_num_map = {item.reference_image_id: get_application_number(item.metadata) for item in similar_items}

    lines = [
        f"## 📊 이미지 분석 완료\n",
        f"**{embedding_info['filename']}** 분석 결과:\n",
        f"- 임베딩 차원: {embedding_info['embedding_dim']}",
        f"- 전체 참조 이미지: {stats['total_references']}개",
        f"- 임계값 이상 유사 이미지: **{stats['above_threshold']}개**",
        f"- 최대 유사도: {stats['max_similarity']:.4f}\n",
    ]

    if len(filtered_df) > 0:
        lines.append("### 상위 유사 이미지")
        lines.append("| 순위 | 출원번호 | 유사도 |")
        lines.append("|-----:|----------|------:|")
        for _, row in filtered_df.head(10).iterrows():
            app_num = app_num_map.get(str(row['image_id']), row['image_id'])
            lines.append(f"| {int(row['rank'])} | {app_num} | {row['cosine_similarity']:.4f} |")

    return "\n".join(lines)


# ============================================================
# 채팅 응답
# ============================================================
def get_chat_response(user_message, cfg):
    import requests
    import json

    url = f"{cfg.ollama_base_url}/api/chat"
    payload = {
        "model": cfg.llm_model,
        "stream": True,
        "messages": [
            {"role": "system", "content": INSTRUCTIONS},
            {"role": "user", "content": user_message},
        ],
        "options": {"temperature": 0.7},
    }

    try:
        with requests.post(url, json=payload, stream=True, timeout=60) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if line:
                    data = json.loads(line)
                    if "message" in data and "content" in data["message"]:
                        yield data["message"]["content"]
    except Exception as e:
        yield f"⚠️ LLM 연결 오류: {str(e)}"


# ============================================================
# 메인 UI
# ============================================================
def main():
    # Config 로드 (NPZ 차원 자동 감지)
    cfg = load_config()

    # 사이드바
    settings = render_sidebar(cfg)

    # 데이터 로드
    try:
        # 자동 감지된 모델로 Embedder 생성
        embedder = load_embedder(cfg.model_name, cfg.pretrained, cfg.device)
        metadata_idx, documents_idx, ref_ids, ref_emb = load_data(cfg)
        data_loaded = True
    except Exception as e:
        data_loaded = False
        data_error = str(e)

    # 헤더
    st.html(div(style=styles(font_size=rem(4), line_height=1))["🔍"])

    title_row = st.columns([4, 1])
    with title_row[0]:
        st.title("Image Similarity AI Assistant", anchor=False)

    # 세션 상태 초기화
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "prev_question_timestamp" not in st.session_state:
        st.session_state.prev_question_timestamp = datetime.datetime.fromtimestamp(0)
    if "analysis_result" not in st.session_state:
        st.session_state.analysis_result = None

    # 초기 화면 체크
    user_just_asked = "initial_question" in st.session_state and st.session_state.initial_question
    user_clicked_suggestion = "selected_suggestion" in st.session_state and st.session_state.selected_suggestion
    user_uploaded_image = "uploaded_image" in st.session_state and st.session_state.uploaded_image is not None
    user_initial_chat_image = "initial_chat_image" in st.session_state and st.session_state.initial_chat_image is not None

    first_interaction = user_just_asked or user_clicked_suggestion or user_uploaded_image or user_initial_chat_image
    has_history = len(st.session_state.messages) > 0

    # ============================================================
    # 초기 화면
    # ============================================================
    if not first_interaction and not has_history:
        st.markdown("**이미지를 업로드**하거나 **질문**을 입력하세요.")

        col1, col2 = st.columns([1, 1])

        with col1:
            st.markdown("### 📷 이미지 유사도 분석")
            st.markdown("""
            1. 이미지 업로드
            2. OpenCLIP 임베딩 생성
            3. 코사인 유사도 계산
            4. 유사 이미지 반환
            """)
            uploaded = st.file_uploader(
                "이미지 업로드",
                type=["jpg", "jpeg", "png", "webp", "bmp"],
                key="uploaded_image",
                label_visibility="collapsed",
            )

        with col2:
            st.markdown("### 💬 질문하기")
            
            # 질문 입력창과 이미지 첨부 버튼
            q_col1, q_col2 = st.columns([5, 1])
            with q_col1:
                st.chat_input("질문을 입력하세요...", key="initial_question")
            with q_col2:
                with st.popover("📎", help="이미지 첨부"):
                    st.file_uploader(
                        "이미지 첨부",
                        type=["jpg", "jpeg", "png", "webp", "bmp"],
                        key="initial_chat_image",
                        label_visibility="collapsed",
                    )
            
            st.markdown("**예시 질문:**")
            st.pills(
                label="Examples",
                label_visibility="collapsed",
                options=SUGGESTIONS.keys(),
                key="selected_suggestion",
            )

        st.button(
            "&nbsp;:small[:gray[:material/info: 사용 안내]]",
            type="tertiary",
            on_click=show_disclaimer_dialog,
        )

        #if data_loaded:
        #    st.success(f"✅ {len(ref_ids)}개 참조 이미지 | {ref_emb.shape[1]}차원 | 모델: {cfg.model_name}")
        #else:
        # 데이터 로드 실패 시에만 에러 표시
        if not data_loaded:
            st.error(f"❌ 데이터 로드 실패: {data_error}")

        st.stop()
    
    # 분석 중이면 초기 화면 요소 숨기기 (이미지 업로드 직후)
    if first_interaction and not has_history:
        # 분석 중 로딩 표시
        with st.spinner("🔄 유사한 이미지 찾는 중입니다. 잠시만 기다려주세요 ☺️"):
            pass  # 아래 로직에서 처리됨

    # ============================================================
    # 대화 시작 후 UI
    # ============================================================
    with title_row[1]:
        def clear_conversation():
            st.session_state.messages = []
            st.session_state.initial_question = None
            st.session_state.selected_suggestion = None
            st.session_state.uploaded_image = None
            st.session_state.analysis_result = None
            # additional_image는 위젯 key이므로 직접 수정하지 않음
            st.session_state.initial_chat_image = None

        st.button("다시 시작", icon=":material/refresh:", on_click=clear_conversation)

    # 추가 질문 입력창과 이미지 첨부 버튼
    input_col1, input_col2 = st.columns([6, 1])
    
    with input_col1:
        user_message = st.chat_input("추가 질문을 입력하세요...")
    
    with input_col2:
        with st.popover("📎", help="이미지 첨부"):
            additional_image = st.file_uploader(
                "이미지 첨부",
                type=["jpg", "jpeg", "png", "webp", "bmp"],
                key="additional_image",
                label_visibility="collapsed",
            )

    if not user_message:
        if user_just_asked:
            user_message = st.session_state.initial_question
        elif user_clicked_suggestion:
            user_message = SUGGESTIONS[st.session_state.selected_suggestion]

    uploaded_file = None
    if user_uploaded_image:
        uploaded_file = st.session_state.uploaded_image
        user_message = f"[이미지: {uploaded_file.name}] 와 유사 이미지를 찾아주세요."
    
    # 초기 질문창에서 이미지 업로드 처리
    if user_initial_chat_image:
        uploaded_file = st.session_state.initial_chat_image
        if not user_message:
            user_message = f"[이미지: {uploaded_file.name}] 와 유사 이미지를 찾아주세요."
    
    # 대화 중 추가 이미지 업로드 처리
    if additional_image is not None:
        uploaded_file = additional_image
        if not user_message:
            user_message = f"[이미지: {uploaded_file.name}] 와 유사 이미지를 찾아주세요."

    # 대화 히스토리 표시
    for i, message in enumerate(st.session_state.messages):
        with st.chat_message(message["role"]):
            if message["role"] == "assistant":
                st.container()
            if "image" in message:
                st.image(message["image"], width=100)
            st.markdown(message["content"])
            if "analysis_result" in message and message["analysis_result"]:
                display_analysis_results(message["analysis_result"], settings)
            if message["role"] == "assistant":
                show_feedback_controls(i)

    # 새 메시지 처리
    if user_message:
        question_timestamp = datetime.datetime.now()
        time_diff = question_timestamp - st.session_state.prev_question_timestamp
        st.session_state.prev_question_timestamp = question_timestamp

        if time_diff < MIN_TIME_BETWEEN_REQUESTS:
            time.sleep(time_diff.seconds + time_diff.microseconds * 0.000001)

        display_message = user_message.replace("$", r"\$")

        with st.chat_message("user"):
            if uploaded_file:
                st.image(uploaded_file, width=100)
            st.text(display_message)

        with st.chat_message("assistant"):
            if uploaded_file and data_loaded:
                # 이미지 분석 - 로딩 중 placeholder 사용
                loading_placeholder = st.empty()
                
                with loading_placeholder.container():
                    st.spinner("🔄 OpenCLIP 임베딩 생성 중...")
                    st.info("📊 유사한 이미지 찾는 중입니다. \n 잠시만 기다려주세요 ☺️")
                
                analysis_result = analyze_image_full(
                    uploaded_file=uploaded_file,
                    cfg=cfg,
                    embedder=embedder,
                    metadata_idx=metadata_idx,
                    documents_idx=documents_idx,
                    ref_ids=ref_ids,
                    ref_emb=ref_emb,
                    min_similarity=settings["min_similarity"],
                    top_k=settings["top_k"],
                    use_llm=settings["use_llm"],
                )
                
                # 로딩 완료 후 placeholder 제거
                loading_placeholder.empty()

                with st.container():
                    response = format_analysis_response(analysis_result)
                    st.markdown(response)

                    if "error" not in analysis_result:
                        display_analysis_results(analysis_result, settings)

                    user_msg = {"role": "user", "content": display_message}
                    if uploaded_file:
                        user_msg["image"] = uploaded_file.getvalue()

                    assistant_msg = {
                        "role": "assistant",
                        "content": response,
                        "analysis_result": analysis_result if "error" not in analysis_result else None,
                    }

                    st.session_state.messages.append(user_msg)
                    st.session_state.messages.append(assistant_msg)
                    st.session_state.analysis_result = analysis_result

                    show_feedback_controls(len(st.session_state.messages) - 1)
            else:
                # 일반 채팅
                with st.spinner("생각 중..."):
                    response_gen = get_chat_response(user_message, cfg)

                with st.container():
                    response = st.write_stream(response_gen)

                    st.session_state.messages.append({"role": "user", "content": display_message})
                    st.session_state.messages.append({"role": "assistant", "content": response})

                    show_feedback_controls(len(st.session_state.messages) - 1)

        st.session_state.initial_question = None
        st.session_state.selected_suggestion = None
        st.session_state.uploaded_image = None
        # additional_image는 위젯 key이므로 직접 수정하지 않음
        st.session_state.initial_chat_image = None


if __name__ == "__main__":
    main()