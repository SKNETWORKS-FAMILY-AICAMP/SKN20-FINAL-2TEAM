"""필요 모델 사전 다운로드.

빌드/검색 전에 실행하면 모델을 미리 받아둘 수 있습니다.
이미 다운로드된 모델은 스킵됩니다.

사용법:
    python download_models.py
"""
from sentence_transformers import SentenceTransformer, CrossEncoder

MODELS = {
    "임베딩 모델": ("nlpai-lab/KURE-v1", "SentenceTransformer"),
    # "리랭커 모델": ("dragonkue/bge-reranker-v2-m3-ko", "CrossEncoder"),
}

def main():
    for name, (model_id, model_type) in MODELS.items():
        print(f"\n[{name}] {model_id} 다운로드 중...")
        if model_type == "SentenceTransformer":
            SentenceTransformer(model_id)
        else:
            CrossEncoder(model_id)
        print(f"  완료")

    print("\n모든 모델 다운로드 완료.")


if __name__ == "__main__":
    main()
