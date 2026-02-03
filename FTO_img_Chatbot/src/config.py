from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Tuple, Optional
import numpy as np


# 차원별 모델 매핑
EMBEDDING_DIM_TO_MODEL = {
    512: ("ViT-B-32", "laion2b_s34b_b79k"),
    768: ("ViT-L-14", "laion2b_s32b_b82k"),
    1024: ("ViT-H-14", "laion2b_s32b_b79k"),
}


@dataclass
class Config:
    # Data files - 프로젝트 루트 기준 (resolve() 사용하지 않음 - 심볼릭 링크 문제 방지)
    metadata_jsonl: Path = field(default_factory=lambda: Path(__file__).parent.parent / "data/openclip_metadata.jsonl")
    # documents_jsonl도 openclip_metadata.jsonl 사용 (document 필드 포함)
    documents_jsonl: Path = field(default_factory=lambda: Path(__file__).parent.parent / "data/openclip_metadata.jsonl")
    embeddings_npz: Path = field(default_factory=lambda: Path(__file__).parent.parent / "data/openclip_embeddings.npz")
    
    # 이미지 폴더 경로 (로컬 이미지 표시용)
    image_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent / "data/img")

    # Output
    output_dir: Path = field(default_factory=lambda: Path("outputs"))

    # OpenCLIP - 자동 감지됨
    model_name: str = "ViT-L-14"
    pretrained: str = "laion2b_s32b_b82k"
    device: str = "mps"

    # Retrieval policy
    top_k: int = 30
    min_similarity: float = 0.25

    # LLM (Local - Ollama)
    llm_model: str = "qwen2.5:14b"
    ollama_base_url: str = "http://localhost:11434"

    # 자동 감지된 정보
    _embedding_dim: Optional[int] = field(default=None, repr=False)

    def __post_init__(self):
        """NPZ 파일에서 임베딩 차원을 자동 감지하고 모델 설정."""
        self._auto_detect_and_set_model()

    def _auto_detect_and_set_model(self):
        """NPZ 파일의 임베딩 차원을 읽어 적합한 모델로 자동 설정."""
        if not self.embeddings_npz.exists():
            print(f"⚠️ NPZ 파일 없음: {self.embeddings_npz}")
            return

        try:
            data = np.load(self.embeddings_npz, allow_pickle=True)
            
            # embeddings 키 호환성 처리 (embeddings 또는 image_embeddings)
            if "embeddings" in data:
                emb = data["embeddings"]
            elif "image_embeddings" in data:
                emb = data["image_embeddings"]
            else:
                raise KeyError(f"NPZ must contain key: 'embeddings' or 'image_embeddings'. Found keys: {list(data.keys())}")
            
            embedding_dim = emb.shape[1]
            self._embedding_dim = embedding_dim

            if embedding_dim in EMBEDDING_DIM_TO_MODEL:
                model_name, pretrained = EMBEDDING_DIM_TO_MODEL[embedding_dim]
                object.__setattr__(self, "model_name", model_name)
                object.__setattr__(self, "pretrained", pretrained)
                print(f"✅ 자동 감지: {embedding_dim}차원 → {model_name} ({pretrained})")
            else:
                print(f"⚠️ 지원하지 않는 임베딩 차원: {embedding_dim}")
                print(f"   지원 차원: {list(EMBEDDING_DIM_TO_MODEL.keys())}")

        except Exception as e:
            print(f"⚠️ NPZ 자동 감지 실패: {e}")

    @property
    def embedding_dim(self) -> Optional[int]:
        return self._embedding_dim