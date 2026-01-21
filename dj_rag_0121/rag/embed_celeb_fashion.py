"""
셀럽 코디 이미지를 Korean CLIP으로 임베딩하고 LangChain Chroma에 저장하는 스크립트
최초 1회 실행하여 RAG 폴더의 모든 이미지를 인덱싱합니다.
"""

import open_clip
import torch
from PIL import Image
from pathlib import Path
from langchain_chroma import Chroma
from langchain_core.documents import Document

from config import (
    RAG_IMAGE_DIR,
    RAG_IMAGE_DIR_NAME,
    CHROMA_DB_DIR,
    CLIP_MODEL_NAME,
    CLIP_PRETRAINED,
    COLLECTION_NAME,
    EMBEDDING_DIM,
    DEVICE,
)


class CLIPEmbeddingFunction:
    """Korean CLIP 기반 이미지 임베딩 함수"""

    def __init__(self):
        print(f"CLIP 모델 로딩 중... (Device: {DEVICE})")
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            CLIP_MODEL_NAME,
            pretrained=CLIP_PRETRAINED,
            device=DEVICE
        )
        self.model.eval()
        print("모델 로딩 완료!")

    def embed_image(self, image_path: str) -> list[float]:
        """이미지를 벡터로 임베딩"""
        image = Image.open(image_path).convert("RGB")
        image_tensor = self.preprocess(image).unsqueeze(0).to(DEVICE)

        with torch.no_grad():
            image_features = self.model.encode_image(image_tensor)
            # 정규화
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)

        return image_features.cpu().numpy().flatten().tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """LangChain 호환: 텍스트 임베딩 (사용하지 않음)"""
        # 이미지 임베딩만 사용하므로 빈 리스트 반환
        return [[0.0] * EMBEDDING_DIM for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        """LangChain 호환: 쿼리 임베딩 (사용하지 않음)"""
        return [0.0] * EMBEDDING_DIM


def main():
    # CLIP 임베딩 함수 초기화
    clip_embedder = CLIPEmbeddingFunction()

    # 기존 DB 삭제 후 재생성
    import shutil
    if CHROMA_DB_DIR.exists():
        try:
            shutil.rmtree(CHROMA_DB_DIR)
            print(f"기존 '{CHROMA_DB_DIR}' 삭제됨")
        except PermissionError:
            print(f"Warning: 기존 DB 삭제 실패 (파일 사용 중). 덮어쓰기 시도...")

    CHROMA_DB_DIR.mkdir(exist_ok=True)

    # 이미지 파일 목록 가져오기
    image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
    image_files = [
        f for f in RAG_IMAGE_DIR.iterdir()
        if f.suffix.lower() in image_extensions
    ]

    if not image_files:
        print(f"Error: {RAG_IMAGE_DIR}에 이미지 파일이 없습니다.")
        return

    print(f"\n총 {len(image_files)}개의 이미지를 처리합니다.\n")

    # 각 이미지 임베딩
    documents = []
    embeddings = []
    ids = []

    for i, image_path in enumerate(image_files, 1):
        print(f"[{i}/{len(image_files)}] {image_path.name} 처리 중...")

        try:
            # CLIP으로 이미지 임베딩
            embedding = clip_embedder.embed_image(str(image_path))
            embeddings.append(embedding)

            # Document 생성 (상대 경로로 저장하여 이식성 확보)
            relative_path = f"{RAG_IMAGE_DIR_NAME}/{image_path.name}"
            doc = Document(
                page_content=image_path.stem,  # 파일명을 content로
                metadata={
                    "filename": image_path.name,
                    "filepath": relative_path,  # 상대 경로 저장
                    "celeb_id": image_path.stem,
                }
            )
            documents.append(doc)
            ids.append(image_path.stem)

            print(f"  - 임베딩 완료! (dim: {len(embedding)})")

        except Exception as e:
            print(f"  - Error: {e}")
            continue

    # LangChain Chroma에 저장
    print("\nChroma DB에 저장 중...")

    # Chroma 클라이언트 직접 사용하여 저장
    import chromadb
    from chromadb.config import Settings

    client = chromadb.PersistentClient(
        path=str(CHROMA_DB_DIR),
        settings=Settings(anonymized_telemetry=False)
    )

    # 기존 컬렉션 삭제 후 새로 생성
    try:
        client.delete_collection(name=COLLECTION_NAME)
        print(f"기존 컬렉션 '{COLLECTION_NAME}' 삭제됨")
    except Exception:
        pass

    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"description": "셀럽 패션 코디 이미지 임베딩"}
    )

    # 데이터 추가
    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=[doc.page_content for doc in documents],
        metadatas=[doc.metadata for doc in documents]
    )

    print("=" * 50)
    print(f"완료! {len(ids)}개의 코디가 벡터 DB에 저장되었습니다.")
    print(f"저장 위치: {CHROMA_DB_DIR}")
    print(f"컬렉션 이름: {COLLECTION_NAME}")


if __name__ == "__main__":
    main()
