"""
유틸리티 함수 모듈

디자인 분석에 필요한 헬퍼 함수들을 제공합니다.

목록:
1. get_image_embedding: 이미지 파일 -> CLIP 임베딩 벡터 반환
2. get_text_embedding: 텍스트 -> CLIP 임베딩 벡터 반환 (텍스트로 이미지 검색 가능!)
3. design_id_to_local_image : ChromaDB design_id를 로컬 이미지 경로로 변환
  (ChromaDB에서 유사 도면 벡터를 찾고, 해당 도면의 로컬 이미지를 불러올 때 사용)
4. search_and_filter_similar_designs: 벡터DB에서 유사 디자인 검색 후 필터링

"""

import os
import re
import cv2
import numpy as np
import clip
import torch
from pathlib import Path
from PIL import Image

# ==================== 경로 설정 ====================
# design/src/utils.py 기준 상위 폴더(= design/)
BASE_DIR   = Path(__file__).resolve().parent.parent

# design/data/images  ← design_id_to_local_image 기본 이미지 디렉토리
IMAGES_DIR = str(BASE_DIR / "data" / "images")

# ==================== 전역 변수 ====================
# CLIP 모델 로드 (ViT-B/32)
device = "cuda" if torch.cuda.is_available() else "cpu"
model, preprocess = clip.load("ViT-B/32", device=device)

# Hybrid Retrieval 파라미터
RETRIEVAL_TOP_K = 50   # Dense 1차 검색 개수 (BM25 재랭킹 전 후보 수)
TOP_K           = 10   # 최종 반환 개수
DENSE_WEIGHT    = 0.7  # Dense 가중치 (BM25 가중치 = 1 - DENSE_WEIGHT)


# ==================== 이미지 임베딩 함수 ====================

def get_image_embedding(image_path):
    """
    이미지 파일 경로 -> CLIP 임베딩 벡터 반환
    
    Args:
        image_path: 분석할 이미지 파일 경로
    
    Returns:
        list: CLIP 임베딩 벡터 (512차원)
        None: 에러 발생 시
    """
    try:
        image = preprocess(Image.open(image_path)).unsqueeze(0).to(device)
        with torch.no_grad():
            embedding = model.encode_image(image)  # 이미지 임베딩
            embedding = embedding.cpu().numpy()[0].tolist() 
        return embedding
    except Exception as e:
        print(f"임베딩 생성 실패: {e}")
        return None


# ==================== 텍스트 임베딩 함수 ====================

def get_text_embedding(text, translate_korean=True) -> tuple[list, str]:
    """
    텍스트 -> CLIP 임베딩 벡터 반환 (한글 자동 번역)
    
    CLIP은 텍스트와 이미지를 같은 임베딩 공간에 매핑하므로
    텍스트로 이미지를 검색할 수 있다!
    
    Args:
        text (str): 검색할 텍스트
                   예: "펌프형 용기", "둥근 모양의 튜브"
        translate_korean (bool): 한글 감지시 영어로 자동 번역 (기본값: True)
    
    Returns:
        tuple: (임베딩 벡터, 사용된 텍스트) 또는 (None, text)
               예: ([0.1, 0.2, ...], "pump bottle")
        
    Examples:
        >>> embedding, translated = get_text_embedding("펌프형 용기")
        >>> results = image_collection.query(query_embeddings=[embedding], n_results=5)
    """
    try:
        query_text = text
        
        # 한글일 경우 영어로 번역(clip은 영어 기반이므로)
        if translate_korean and any('\uac00' <= char <= '\ud7a3' for char in text):
            from langchain_openai import ChatOpenAI
            print(f"   한글 감지: '{text}' → 영어로 번역 중...")
            llm_translator = ChatOpenAI(model="gpt-4o-mini", temperature=0)
            translation_prompt = f"""다음 한글을 간단명료한 영어로 번역하세요. 
디자인/제품 검색용이므로 핵심 키워드만 간단히.

한글: {text}
영어:"""
            query_text = llm_translator.invoke(translation_prompt).content.strip()
            print(f"   ✅ 번역 완료: '{query_text}'")
        
        # 텍스트를 토큰화
        text_tokens = clip.tokenize([query_text]).to(device)
        with torch.no_grad():
            # CLIP 텍스트 인코더로 임베딩
            text_embedding = model.encode_text(text_tokens)
            embedding = text_embedding.cpu().numpy()[0].tolist()
        
        return embedding, query_text
        
    except Exception as e:
        print(f"텍스트 임베딩 생성 실패: {e}")
        return None, text


# ==================== 이미지 경로 변환 함수 ====================

def design_id_to_local_image(design_id, images_dir=None):
    """
    ChromaDB design_id를 로컬 이미지 경로로 변환

    DB ID 형식:   {출원번호}-api_xml-{img_num}            예: '3020120015713-api_xml-1'
                  {출원번호}-api_xml-{img_num}-IMG-{n}    예: '3020120015713-api_xml-1-IMG-1'
    파일명 형식:  {출원번호}-api_xml-{img_num}_{frame}.JPG 예: '3020120015713-api_xml-1_001.JPG'

    prefix({출원번호}-api_xml-{img_num})로 시작하는 파일을 images_dir에서 탐색.
    """
    if images_dir is None:
        images_dir = IMAGES_DIR

    # '-IMG-' 이후 부분은 무시하고 prefix만 추출
    # '3020120015713-api_xml-1-IMG-1' → '3020120015713-api_xml-1'
    # '3020120015713-api_xml-1'       → '3020120015713-api_xml-1'
    prefix = design_id.split('-IMG-')[0]

    # images_dir에서 '{prefix}_'로 시작하는 파일 탐색
    for fname in os.listdir(images_dir):
        if fname.startswith(prefix + '_'):
            return os.path.join(images_dir, fname)

    return None


# ==================== 이미지 전처리 함수 ====================

def convert_to_sketch_query(image: Image.Image) -> Image.Image:
    """
    업로드된 쿼리 이미지에 벡터 DB에 임베딩해서 넣은 사진들과 동일한
    Canny Edge Detection 전처리를 적용.

    저장된 DB 임베딩 = 스케치 변환 이미지 기반
    쿼리 임베딩      = 원본 이미지 기반  ← 불일치 → 이 함수로 해결

    파라미터: GaussianBlur(5,5,1.0) / Canny(30,120) / dilate(2x2, 1회)
    결과: 흰 배경 + 검은 윤곽선 PIL Image
    """
    img_array  = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
    blurred    = cv2.GaussianBlur(img_array, (5, 5), 1.0)
    edges      = cv2.Canny(blurred, 30, 120)
    edges      = cv2.dilate(edges, np.ones((2, 2), np.uint8), iterations=1)
    sketch     = 255 - edges              # 흰 배경, 검은 선
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
    """
    Hybrid Retrieval (Dense-first 재랭킹 방식):

      1) Dense:  CLIP 임베딩 → ChromaDB에서 retrieval_top_k개 검색
      2) BM25:   Dense 1위 articleName → Dense 결과 내 BM25 재점수
      3) min-max 정규화 후 가중 합산 (dense_weight : 1-dense_weight)
      4) 동일 출원번호 중복 제거 (hybrid_score 높은 도면 유지)
      5) 최종 top_k 반환

    Args:
        image_path      : 쿼리 이미지 파일 경로
        image_collection: ChromaDB 컬렉션
        bm25            : 사전 빌드된 BM25Okapi 인덱스
        all_ids         : ChromaDB 전체 ID 리스트 (bm25 코퍼스와 순서 일치)
        all_metadatas   : ChromaDB 전체 메타데이터 리스트
        top_k           : 최종 반환 개수
        retrieval_top_k : Dense 1차 검색 개수
        dense_weight    : Dense 점수 가중치 (0~1)

    Returns:
        list[dict]: 정렬된 검색 결과
            [{"id": ..., "metadata": ..., "dense_score": ...,
              "bm25_score": ..., "hybrid_score": ...}, ...]
    """
    bm25_weight = 1.0 - dense_weight

    # O(1) 탐색을 위한 사전 구성
    id_to_meta = {id_: meta for id_, meta in zip(all_ids, all_metadatas)}
    id_to_idx  = {id_: i   for i,   id_  in enumerate(all_ids)}

    # ── Step 1: Dense 검색 ──
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
    }  # cosine distance(0~2) → similarity(0~1)

    # ── Step 2: BM25 재점수 (Dense 결과만 대상) ──
    # Dense 1위 articleName → BM25 쿼리 토큰
    top_meta     = id_to_meta.get(dense_ids[0], {}) if dense_ids else {}
    query_text   = top_meta.get("articleName", "").strip()
    query_tokens = [t for t in re.split(r"\s+", query_text) if t] or ["검색"]

    # 전체 코퍼스 BM25 스코어에서 Dense 결과 ID에 해당하는 것만 추출
    bm25_all_scores = bm25.get_scores(query_tokens)
    bm25_scores = {
        did: float(bm25_all_scores[id_to_idx[did]])
        for did in dense_ids
        if did in id_to_idx
    }

    # ── Step 3: min-max 정규화 ──
    def _minmax(score_map: dict) -> dict:
        vals = list(score_map.values())
        lo, hi = min(vals), max(vals)
        r = hi - lo if hi != lo else 1e-8
        return {k: (v - lo) / r for k, v in score_map.items()}

    d_norm = _minmax(dense_scores)
    b_norm = _minmax(bm25_scores)

    # ── Step 4: 가중 합산 ──
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

    # ── Step 5: 동일 출원번호 중복 제거 (hybrid_score 높은 도면 유지) ──
    deduped: dict[str, dict] = {}
    for item in scored:
        app_num = item["metadata"].get("applicationNumber", "N/A")
        if app_num not in deduped or item["hybrid_score"] > deduped[app_num]["hybrid_score"]:
            deduped[app_num] = item

    # ── Step 6: 정렬 후 top_k 반환 ──
    return sorted(deduped.values(), key=lambda x: x["hybrid_score"], reverse=True)[:top_k]


# ==================== 벡터 검색 및 필터링 함수 ====================

def search_and_filter_similar_designs(image_collection, query_embedding, n_results=10):
    """
    벡터DB에서 유사 디자인 검색 후 필터링
    
    필터링 규칙:
    - 같은 출원번호 중 가장 유사도 거리가 짧은 것만 유지
      (하나의 출원에 여러 도면이 있을 경우 대표 도면만 선택)
    
    Args:
        image_collection: ChromaDB 컬렉션
        query_embedding: 입력 이미지의 CLIP 임베딩 벡터
        n_results: 검색할 결과 개수 (기본값: 10)
    
    Returns:
        dict: 필터링된 검색 결과
            {
                'ids': [[design_id, ...]],
                'distances': [[distance, ...]],
                'metadatas': [[metadata, ...]]
            }
    """
    # 벡터DB에서 상위 N개 유사 도면 검색
    results = image_collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results
    )
    
    # 필터링: 같은 출원번호 중 가장 유사도 거리가 짧은 것만 유지
    filtered_data = {}
    for i in range(len(results["ids"][0])):
        design_id = results["ids"][0][i]
        distance = results["distances"][0][i]
        metadata = results["metadatas"][0][i]
        app_number = metadata.get('applicationNumber', 'N/A')
        
        # 같은 출원번호 중 가장 거리가 짧은 것만 유지
        if app_number not in filtered_data or distance < filtered_data[app_number]['distance']:
            filtered_data[app_number] = {
                'id': design_id,
                'distance': distance,
                'metadata': metadata
            }
    
    # 필터링된 결과로 변환
    filtered_results = {
        'ids': [[item['id'] for item in filtered_data.values()]],
        'distances': [[item['distance'] for item in filtered_data.values()]],
        'metadatas': [[item['metadata'] for item in filtered_data.values()]]
    }
    
    return filtered_results
