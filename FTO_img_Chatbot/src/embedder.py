from __future__ import annotations
from pathlib import Path

import numpy as np
import torch
from PIL import Image
import open_clip


class OpenCLIPEmbedder:
    """OpenCLIP 모델로 이미지 임베딩 생성."""

    def __init__(self, model_name: str, pretrained: str, device: str = "mps"):
        self.model_name = model_name
        self.pretrained = pretrained

        # 디바이스 설정
        if device == "mps" and not torch.backends.mps.is_available():
            device = "cpu"
        elif device == "cuda" and not torch.cuda.is_available():
            device = "cpu"
        self._device = torch.device(device)

        # 모델 로드
        model, _, preprocess = open_clip.create_model_and_transforms(
            model_name, pretrained=pretrained
        )
        self._model = model.to(self._device).eval()
        self._preprocess = preprocess

    @torch.inference_mode()
    def embed_image_path(self, image_path: Path, normalize: bool = True) -> np.ndarray:
        """이미지 파일 경로로부터 임베딩 벡터 생성."""
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        img = Image.open(image_path).convert("RGB")
        x = self._preprocess(img).unsqueeze(0).to(self._device)

        feats = self._model.encode_image(x).float()

        if normalize:
            feats = feats / feats.norm(dim=-1, keepdim=True).clamp_min(1e-12)

        return feats.squeeze(0).detach().cpu().numpy().astype(np.float32)