"""
디자인 유사 이미지 검색 Streamlit 앱
======================================
흐름: 이미지 업로드 → ChromaDB Hybrid Retrieval (Dense + BM25) → 유사 이미지 10개 + 메타데이터 표시
"""

import json
import os
import re
import cv2
import numpy as np
import streamlit as st
import torch
import torch.nn.functional as F
import chromadb
import clip
from pathlib import Path

PROJECT_ROOT     = Path(__file__).resolve().parent.parent
from typing import Optional
from PIL import Image
from rank_bm25 import BM25Okapi   # pip install rank-bm25

# ─────────────────────────────────────────────
# 0. 설정
# ─────────────────────────────────────────────
# ── 원본 CLIP 설정 ──
CHROMA_DB_PATH   = str(PROJECT_ROOT / "data/sketch/chroma_db_v2")
FINETUNED_MODEL_PATH = "" #str(PROJECT_ROOT / "train/checkpoints/clip_finetuned_best.pt")

COLLECTION_NAME  = "design"
CLIP_MODEL_NAME  = "ViT-B/32"
TOP_K            = 10
RETRIEVAL_TOP_K  = 50
DENSE_WEIGHT     = 0.8
BM25_WEIGHT      = 0.2

DEVICE = (
    "cuda"  if torch.cuda.is_available() else
    "mps"   if torch.backends.mps.is_available() else
    "cpu"
)

# ─────────────────────────────────────────────
# 1. 모델 & ChromaDB 로드 (캐싱)
# ─────────────────────────────────────────────
@st.cache_resource(show_spinner="🔄 CLIP 모델 로드 중...")
def load_clip():
    model, preprocess = clip.load(CLIP_MODEL_NAME, device=DEVICE)
    model = model.float()

    # 파인튜닝 모델이 지정된 경우 가중치 교체
    if FINETUNED_MODEL_PATH and os.path.exists(FINETUNED_MODEL_PATH):
        checkpoint = torch.load(FINETUNED_MODEL_PATH, map_location=DEVICE)
        model.load_state_dict(checkpoint["model_state_dict"])
        st.sidebar.success(
            f"🎯 파인튜닝 모델 로드\n"
            f"Epoch {checkpoint.get('epoch','?')} | "
            f"Gap {checkpoint.get('margin_gap', 0):.4f}"
        )
    else:
        st.sidebar.info("🔵 원본 CLIP 모델 사용 중")

    model.eval()
    return model, preprocess


@st.cache_resource(show_spinner="🔄 ChromaDB 연결 중...")
def load_collection():
    client     = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    collection = client.get_collection(name=COLLECTION_NAME)
    return collection


@st.cache_resource(show_spinner="🔄 BM25 인덱스 구축 중...")
def build_bm25_index(_collection):
    """
    ChromaDB의 모든 메타데이터를 불러와 BM25 인덱스 구축.
    articleName + designSummary를 토큰화하여 색인.
    """
    all_data  = _collection.get(include=["metadatas", "embeddings"])
    ids       = all_data["ids"]
    metadatas = all_data["metadatas"]

    corpus_tokens = []
    for m in metadatas:
        text  = _safe_str(m.get("articleName", ""))
        text += " " + _safe_str(m.get("designSummary", ""))
        tokens = [t for t in re.split(r"\s+", text.strip()) if len(t) >= 1]
        corpus_tokens.append(tokens if tokens else ["없음"])

    bm25 = BM25Okapi(corpus_tokens)
    return bm25, ids, metadatas, corpus_tokens


# ─────────────────────────────────────────────
# 2. 유틸 함수
# ─────────────────────────────────────────────
def _safe_str(val) -> str:
    if isinstance(val, dict):
        return json.dumps(val, ensure_ascii=False)
    return str(val) if val else ""


def _parse_status(metadata: dict) -> dict:
    status = metadata.get("status", {})
    if isinstance(status, str):
        try:
            status = json.loads(status)
        except Exception:
            status = {}
    return status if isinstance(status, dict) else {}


# ─────────────────────────────────────────────
# 3. 쿼리 이미지 스케치 전처리
#    embeddings_v2.py 와 동일한 Canny Edge Detection 적용
#    → 저장된 임베딩(스케치 기반)과 쿼리 임베딩의 도메인 통일
# ─────────────────────────────────────────────
def convert_to_sketch_query(image: Image.Image) -> Image.Image:
    """
    업로드된 쿼리 이미지에 embeddings_v2.py 와 동일한
    Canny Edge Detection 전처리를 적용.

    저장된 DB 임베딩 = 스케치 변환 이미지 기반
    쿼리 임베딩      = 원본 이미지 기반  ← 불일치 → 이 함수로 해결

    파라미터: GaussianBlur(5,5,1.0) / Canny(30,120) / dilate(2x2, 1회)
    결과: 흰 배경 + 검은 윤곽선 PIL Image
    """
    img_array  = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
    blurred    = cv2.GaussianBlur(img_array, (5, 5), 1.0)          # ← v2.py 동일
    edges      = cv2.Canny(blurred, 30, 120)                       # ← v2.py 동일
    edges      = cv2.dilate(edges, np.ones((2, 2), np.uint8), iterations=1)
    sketch     = 255 - edges              # 흰 배경, 검은 선
    sketch_rgb = cv2.cvtColor(sketch, cv2.COLOR_GRAY2RGB)
    return Image.fromarray(sketch_rgb)


def get_image_embedding(image: Image.Image, model, preprocess) -> np.ndarray:
    """
    PIL Image → Canny 전처리 → 정규화된 CLIP 임베딩 (unit vector)

    변경 사항:
      1) convert_to_sketch_query() 로 DB 임베딩과 동일한 전처리
      2) F.normalize 로 unit vector 보장 (DB 저장 벡터와 동일한 정규화)
    """
    image  = convert_to_sketch_query(image)            # ← Canny 스케치 전처리 (추가)
    tensor = preprocess(image).unsqueeze(0).to(DEVICE)
    with torch.no_grad():
        emb = model.encode_image(tensor).float()
        emb = F.normalize(emb, dim=-1)                 # ← unit vector
    return emb.cpu().numpy()[0]


# ─────────────────────────────────────────────
# 4. Hybrid Retriever (Dense + BM25)
# ─────────────────────────────────────────────
def hybrid_retrieve(
    query_image: Image.Image,
    model,
    preprocess,
    collection,
    bm25,
    all_ids,
    all_metadatas,
    top_k: int = TOP_K,
    dense_weight: float = DENSE_WEIGHT,
) -> list[dict]:
    """
    Hybrid Retrieval:
      1) Dense: CLIP 임베딩으로 ChromaDB에서 RETRIEVAL_TOP_K개 검색
      2) BM25:  articleName 텍스트 검색
      3) 점수 min-max 정규화 후 가중 합산 → 최종 top_k 반환
    """
    bm25_weight = 1.0 - dense_weight

    # ── Step 1: Dense 검색 ──
    query_emb = get_image_embedding(query_image, model, preprocess)

    dense_results   = collection.query(
        query_embeddings=[query_emb.tolist()],
        n_results=min(RETRIEVAL_TOP_K, collection.count()),
        include=["metadatas", "distances"],
    )
    dense_ids       = dense_results["ids"][0]
    dense_distances = dense_results["distances"][0]
    # cosine distance(0~2) → similarity(0~1)
    dense_scores_raw = [1.0 - d for d in dense_distances]
    dense_map = {did: score for did, score in zip(dense_ids, dense_scores_raw)}

    # ── Step 2: BM25 검색 ──
    # 이미지 쿼리이므로 Dense 1위 결과의 articleName을 BM25 쿼리 텍스트로 활용
    top_meta     = all_metadatas[all_ids.index(dense_ids[0])] if dense_ids else {}
    query_text   = _safe_str(top_meta.get("articleName", ""))
    query_tokens = [t for t in re.split(r"\s+", query_text.strip()) if t] or ["검색"]

    bm25_scores_raw = bm25.get_scores(query_tokens)
    bm25_map = {all_ids[i]: float(bm25_scores_raw[i]) for i in range(len(all_ids))}

    # ── Step 3: min-max 정규화 + 가중 합산 ──
    d_vals  = list(dense_map.values())
    d_min, d_max = min(d_vals), max(d_vals)
    d_range = d_max - d_min if d_max != d_min else 1e-8

    b_vals  = [bm25_map.get(did, 0.0) for did in dense_ids]
    b_min, b_max = min(b_vals), max(b_vals)
    b_range = b_max - b_min if b_max != b_min else 1e-8

    results = []
    for did in dense_ids:
        meta   = all_metadatas[all_ids.index(did)]
        d_norm = (dense_map[did] - d_min) / d_range
        b_norm = (bm25_map.get(did, 0.0) - b_min) / b_range
        hybrid = dense_weight * d_norm + bm25_weight * b_norm
        results.append({
            "id":           did,
            "metadata":     meta,
            "dense_score":  round(dense_map[did], 4),
            "bm25_score":   round(bm25_map.get(did, 0.0), 4),
            "hybrid_score": round(hybrid, 4),
        })

    results = sorted(results, key=lambda x: x["hybrid_score"], reverse=True)
    return results[:top_k]


# ─────────────────────────────────────────────
# 5. 결과 카드 렌더링
# ─────────────────────────────────────────────
def render_result_card(rank: int, item: dict):
    """한 건의 검색 결과를 Streamlit 카드 형태로 표시"""
    meta   = item["metadata"]
    status = _parse_status(meta)

    admst  = status.get("admstStat", meta.get("admstStat", ""))
    reg_fg = status.get("regFg",     meta.get("regFg", "N"))
    badge_color = {"등록": "🟢", "공개": "🔵", "출원": "🟡"}.get(admst, "⚪")

    with st.container():
        st.markdown(f"### #{rank}  {badge_color} {meta.get('articleName', '알 수 없음')}")

        col_img, col_info = st.columns([1, 2])

        # ── 이미지 ──
        with col_img:
            img_path = meta.get("imagePath", "")
            if img_path and os.path.exists(img_path):
                st.image(img_path, use_container_width=True)
            elif img_path and img_path.startswith("http"):
                st.image(img_path, use_container_width=True)
            else:
                st.caption("🖼️ 이미지 없음")

            st.metric("Hybrid Score", f"{item['hybrid_score']:.4f}")
            st.caption(
                f"Dense: {item['dense_score']:.4f} | "
                f"BM25: {item['bm25_score']:.2f}"
            )

        # ── 메타데이터 ──
        with col_info:
            app_num   = meta.get("applicationNumber", "")
            reg_num   = meta.get("registrationNumber", "")
            pub_num   = meta.get("publicationNumber",  meta.get("publication_number", ""))
            last_date = status.get("lastDispositionDate", meta.get("lastDispositionDate", ""))

            info_data = {
                "항목": ["출원번호", "등록번호", "공개번호", "물품명", "등록여부", "처리상태", "최종처분일"],
                "내용": [
                    app_num  or "-",
                    reg_num  or "-",
                    pub_num  or "-",
                    meta.get("articleName", "-"),
                    "등록" if reg_fg == "Y" else "미등록",
                    admst    or "-",
                    last_date or "-",
                ],
            }

            applicant = meta.get("applicantName", meta.get("applicant_name", ""))
            agent     = meta.get("agentName",     meta.get("agent_name", ""))
            if applicant:
                info_data["항목"].append("출원인")
                info_data["내용"].append(applicant)
            if agent:
                info_data["항목"].append("대리인")
                info_data["내용"].append(agent)

            import pandas as pd
            st.dataframe(
                pd.DataFrame(info_data),
                hide_index=True,
                use_container_width=True,
            )

            design_summary = meta.get("designSummary", meta.get("design_summary", ""))
            design_desc    = meta.get("designDescription", meta.get("design_description", ""))

            if design_summary:
                with st.expander("📝 창작의 요점"):
                    st.write(design_summary.replace("&quot;", '"'))

            if design_desc:
                with st.expander("📄 디자인 설명"):
                    st.write(design_desc.replace("&quot;", '"'))

        st.divider()


# ─────────────────────────────────────────────
# 6. Streamlit UI
# ─────────────────────────────────────────────
def main():
    st.set_page_config(
        page_title="디자인 유사 이미지 검색",
        page_icon="🔍",
        layout="wide",
    )

    st.title("🔍 디자인 유사 이미지 검색")
    st.caption(
        "이미지를 업로드하면 ChromaDB에서 Hybrid Retrieval (Dense CLIP + BM25)로 "
        f"유사 디자인 Top-{TOP_K}을 검색합니다."
    )

    # ── 모델 / DB 로드 ──
    try:
        clip_model, clip_preprocess = load_clip()
        collection                  = load_collection()
        bm25, all_ids, all_metadatas, _ = build_bm25_index(collection)
    except Exception as e:
        st.error(f"❌ 초기화 실패: {e}")
        st.info("ChromaDB 경로 및 컬렉션 이름을 확인하세요.")
        st.code(f"CHROMA_DB_PATH = '{CHROMA_DB_PATH}'\nCOLLECTION_NAME = '{COLLECTION_NAME}'")
        return

    st.success(f"✅ DB 연결 완료 | 총 {collection.count():,}건 | Device: {DEVICE}")

    # ── 사이드바 ──
    with st.sidebar:
        st.header("⚙️ 검색 설정")
        top_k   = st.slider("검색 결과 수",  min_value=1,  max_value=20,  value=TOP_K)
        dense_w = st.slider("Dense 가중치", 0.0, 1.0, DENSE_WEIGHT, 0.1)
        bm25_w  = round(1.0 - dense_w, 1)
        st.caption(f"BM25 가중치: {bm25_w} (자동)")
        st.divider()
        st.markdown("**점수 설명**")
        st.markdown("- **Dense**: CLIP 코사인 유사도 (스케치 전처리 통일)")
        st.markdown("- **BM25**: 물품명 텍스트 유사도")
        st.markdown("- **Hybrid**: 가중 합산 최종 점수")
        st.divider()
        show_sketch = st.checkbox("🖊️ 쿼리 스케치 변환 미리보기", value=False)

    # ── 이미지 업로드 ──
    uploaded = st.file_uploader(
        "🖼️ 검색할 이미지를 업로드하세요",
        type=["jpg", "jpeg", "png", "webp"],
    )

    if uploaded is None:
        st.info("👆 이미지를 업로드하면 유사 디자인을 검색합니다.")
        return

    query_image = Image.open(uploaded).convert("RGB")

    # ── 원본 + 스케치 미리보기 ──
    if show_sketch:
        col_orig, col_sketch = st.columns(2)
        with col_orig:
            st.image(query_image, caption="원본 이미지", use_container_width=True)
        with col_sketch:
            sketch_preview = convert_to_sketch_query(query_image)
            st.image(sketch_preview, caption="스케치 변환 후 (실제 임베딩 입력)", use_container_width=True)
    else:
        col1, col2 = st.columns([1, 3])
        with col1:
            st.image(query_image, caption="업로드된 이미지", use_container_width=True)
        with col2:
            st.markdown("### 검색 실행")
            st.write(f"- 파일명: `{uploaded.name}`")
            st.write(f"- 크기: {query_image.size[0]} × {query_image.size[1]}")

    search_btn = st.button("🔍 유사 이미지 검색", type="primary", use_container_width=True)

    if not search_btn:
        return

    # ── 검색 실행 ──
    with st.spinner("🔍 유사 이미지 검색 중..."):
        try:
            results = hybrid_retrieve(
                query_image   = query_image,
                model         = clip_model,
                preprocess    = clip_preprocess,
                collection    = collection,
                bm25          = bm25,
                all_ids       = all_ids,
                all_metadatas = all_metadatas,
                top_k         = top_k,
                dense_weight  = dense_w,
            )
        except Exception as e:
            st.error(f"❌ 검색 오류: {e}")
            return

    if not results:
        st.warning("유사한 디자인을 찾지 못했습니다.")
        return

    st.success(f"✅ 검색 완료 — {len(results)}건 발견")
    st.markdown("---")

    st.markdown(f"## 🎯 유사 디자인 Top-{len(results)}")
    for rank, item in enumerate(results, 1):
        render_result_card(rank, item)


if __name__ == "__main__":
    main()
