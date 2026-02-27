"""
유틸리티 함수 모듈 — GPT 전용 버전

원본: utils.py
변경: llm (한국어 번역용)을 vLLM → OpenAI GPT-4o-mini로 교체

나머지 (CLIP, hybrid_retrieve 등)는 원본과 동일.
"""

import os
import re
import cv2
import numpy as np
import clip
import torch
from pathlib import Path
from PIL import Image
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
load_dotenv()

# ==================== 경로 설정 ====================
BASE_DIR   = Path(__file__).resolve().parent.parent
IMAGES_DIR = str(BASE_DIR / "data" / "images")

# ==================== 전역 변수 ====================
# CLIP 모델 로드 (ViT-B/32)
device = "cuda" if torch.cuda.is_available() else "cpu"
model, preprocess = clip.load("ViT-B/32", device=device)

# ── 변경: OpenAI GPT-4o-mini 사용 (vLLM 대신) ──
llm = ChatOpenAI(
    model="gpt-4o-mini",
    api_key=os.getenv("OPENAI_API_KEY"),
    temperature=0,
)

# Hybrid Retrieval 파라미터
RETRIEVAL_TOP_K = 50
TOP_K           = 10
DENSE_WEIGHT    = 0.7


# ==================== 이미지 임베딩 함수 ====================

def get_image_embedding(image_path):
    """이미지 파일 경로 -> CLIP 임베딩 벡터 반환"""
    try:
        image = preprocess(Image.open(image_path)).unsqueeze(0).to(device)
        with torch.no_grad():
            embedding = model.encode_image(image)
            embedding = embedding.cpu().numpy()[0].tolist()
        return embedding
    except Exception as e:
        print(f"임베딩 생성 실패: {e}")
        return None


# ==================== 텍스트 임베딩 함수 ====================

def get_text_embedding(text, translate_korean=True) -> tuple[list, str]:
    """텍스트 -> CLIP 임베딩 벡터 반환 (한글 자동 번역)"""
    try:
        query_text = text

        if translate_korean and any('\uac00' <= char <= '\ud7a3' for char in text):
            print(f"   한글 감지: '{text}' → 영어로 번역 중...")
            translation_prompt = f"""다음 한글에서 CLIP 이미지 검색에 쓸 핵심 물품명(명사)만 영어로 출력하세요.
'찾아줘', '검색해줘', '보여줘' 등 지시어는 제외하세요.
단어나 짧은 구(2~4단어)만 출력하세요.

예: '펌프형 용기 디자인 찾아줘' → pump container
예: '둥근 화장품 병 보여줘' → round cosmetic bottle
예: '사각형 화장품 용기' → square cosmetic container

한글: {text}
영어:"""
            query_text = llm.invoke(translation_prompt).content.strip()
            print(f"   번역 완료: '{query_text}'")

        text_tokens = clip.tokenize([query_text]).to(device)
        with torch.no_grad():
            text_embedding = model.encode_text(text_tokens)
            embedding = text_embedding.cpu().numpy()[0].tolist()

        return embedding, query_text

    except Exception as e:
        print(f"텍스트 임베딩 생성 실패: {e}")
        return None, text


# ==================== 이미지 경로 변환 함수 ====================

def design_id_to_local_image(design_id, images_dir=None):
    """ChromaDB design_id를 로컬 이미지 경로로 변환"""
    if images_dir is None:
        images_dir = IMAGES_DIR

    prefix = design_id.split('-IMG-')[0]

    for fname in os.listdir(images_dir):
        if fname.startswith(prefix + '_'):
            return os.path.join(images_dir, fname)

    return None


# ==================== 이미지 전처리 함수 ====================

def convert_to_sketch_query(image: Image.Image) -> Image.Image:
    """쿼리 이미지 → Canny Edge 스케치 변환"""
    img_array  = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
    blurred    = cv2.GaussianBlur(img_array, (5, 5), 1.0)
    edges      = cv2.Canny(blurred, 30, 120)
    edges      = cv2.dilate(edges, np.ones((2, 2), np.uint8), iterations=1)
    sketch     = 255 - edges
    sketch_rgb = cv2.cvtColor(sketch, cv2.COLOR_GRAY2RGB)
    return Image.fromarray(sketch_rgb)


# ==================== Hybrid Retrieval 함수 ====================

def hybrid_retrieve(
    image_path: str,
    image_collection,
    bm25,
    all_ids: list,
    all_metadatas: list,
    top_k: int = TOP_K,
    retrieval_top_k: int = RETRIEVAL_TOP_K,
    dense_weight: float = DENSE_WEIGHT,
) -> list[dict]:
    """Hybrid Retrieval (Dense-first 재랭킹 방식)"""
    bm25_weight = 1.0 - dense_weight

    id_to_meta = {id_: meta for id_, meta in zip(all_ids, all_metadatas)}
    id_to_idx  = {id_: i   for i,   id_  in enumerate(all_ids)}

    query_emb = get_image_embedding(image_path)
    if query_emb is None:
        return []

    dense_results = image_collection.query(
        query_embeddings=[query_emb],
        n_results=min(retrieval_top_k, image_collection.count()),
        include=["metadatas", "distances"],
    )
    dense_ids     = dense_results["ids"][0]
    dense_scores  = {
        did: 1.0 - d
        for did, d in zip(dense_ids, dense_results["distances"][0])
    }

    top_meta     = id_to_meta.get(dense_ids[0], {}) if dense_ids else {}
    query_text   = top_meta.get("articleName", "").strip()
    query_tokens = [t for t in re.split(r"\s+", query_text) if t] or ["검색"]

    bm25_all_scores = bm25.get_scores(query_tokens)
    bm25_scores = {
        did: float(bm25_all_scores[id_to_idx[did]])
        for did in dense_ids
        if did in id_to_idx
    }

    def _minmax(score_map: dict) -> dict:
        vals = list(score_map.values())
        lo, hi = min(vals), max(vals)
        r = hi - lo if hi != lo else 1e-8
        return {k: (v - lo) / r for k, v in score_map.items()}

    d_norm = _minmax(dense_scores)
    b_norm = _minmax(bm25_scores)

    scored = [
        {
            "id":           did,
            "metadata":     id_to_meta.get(did, {}),
            "dense_score":  round(dense_scores.get(did, 0.0), 4),
            "bm25_score":   round(bm25_scores.get(did, 0.0), 4),
            "hybrid_score": round(
                dense_weight * d_norm.get(did, 0.0)
                + bm25_weight * b_norm.get(did, 0.0), 4
            ),
        }
        for did in dense_ids
    ]

    deduped: dict[str, dict] = {}
    for item in scored:
        app_num = item["metadata"].get("applicationNumber", "N/A")
        if app_num not in deduped or item["hybrid_score"] > deduped[app_num]["hybrid_score"]:
            deduped[app_num] = item

    return sorted(deduped.values(), key=lambda x: x["hybrid_score"], reverse=True)[:top_k]


# ==================== 벡터 검색 및 필터링 함수 ====================

def search_and_filter_similar_designs(image_collection, query_embedding, n_results=10):
    """벡터DB에서 유사 디자인 검색 후 필터링"""
    results = image_collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results
    )

    filtered_data = {}
    for i in range(len(results["ids"][0])):
        design_id = results["ids"][0][i]
        distance = results["distances"][0][i]
        metadata = results["metadatas"][0][i]
        app_number = metadata.get('applicationNumber', 'N/A')

        if app_number not in filtered_data or distance < filtered_data[app_number]['distance']:
            filtered_data[app_number] = {
                'id': design_id,
                'distance': distance,
                'metadata': metadata
            }

    filtered_results = {
        'ids': [[item['id'] for item in filtered_data.values()]],
        'distances': [[item['distance'] for item in filtered_data.values()]],
        'metadatas': [[item['metadata'] for item in filtered_data.values()]]
    }

    return filtered_results
