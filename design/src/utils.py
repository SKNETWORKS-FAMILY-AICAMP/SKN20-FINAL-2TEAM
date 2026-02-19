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
import clip
import torch
from pathlib import Path
from PIL import Image


# ==================== 전역 변수 ====================
# CLIP 모델 로드 (ViT-B/32)
device = "cuda" if torch.cuda.is_available() else "cpu"
model, preprocess = clip.load("ViT-B/32", device=device)


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

# utils.py 기준 상대 경로로 이미지 디렉토리 설정
_DEFAULT_IMAGES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "images")


def design_id_to_local_image(design_id, images_dir=None):
    """
    ChromaDB design_id를 로컬 이미지 경로로 변환

    Args:
        design_id: ChromaDB의 디자인 ID
                   예: "3020250000208-09-01-0-IMG-0"
        images_dir: 이미지 디렉토리 경로 (기본값: ../data/images)

    Returns:
        str: 로컬 이미지 파일 경로
        None: 파일이 존재하지 않을 경우
    """
    if images_dir is None:
        images_dir = _DEFAULT_IMAGES_DIR

    # IMG 부분 제거
    parts = design_id.split('-IMG-')
    if len(parts) == 2:
        prefix = parts[0]      # 3020250000208-09-01-0
        image_num = parts[1]   # 0

        # 3자리 숫자로 변환
        image_num_padded = image_num.zfill(3)  # 000

        # 파일명 생성
        filename = f"{prefix}_{image_num_padded}.jpg"
        local_path = os.path.join(images_dir, filename)

        return local_path if os.path.exists(local_path) else None

    return None


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
