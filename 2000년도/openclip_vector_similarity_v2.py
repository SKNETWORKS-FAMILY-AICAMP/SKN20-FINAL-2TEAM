#!/usr/bin/env python3
"""
openclip_vector_similarity_v2.py
랜덤으로 이미지 2장을 선택하여 OpenCLIP 벡터 유사도(cosine similarity)를 계산합니다.

사용법:
    python openclip_vector_similarity_v2.py
    python openclip_vector_similarity_v2.py --num_pairs 10
    python openclip_vector_similarity_v2.py --threshold 0.7
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import List, Tuple

import numpy as np
import pandas as pd
import torch
from PIL import Image
from tqdm import tqdm

try:
    import open_clip
except ImportError:
    raise ImportError("open_clip이 설치되지 않았습니다. `pip install open-clip-torch` 실행")


# -------------------------
# 설정
# -------------------------
DEFAULT_MODEL_NAME = "ViT-L-14"
DEFAULT_PRETRAINED = "laion2b_s32b_b82k"
DEFAULT_THRESHOLD = 0.7  # 이 값 이상이면 label=1 (유사), 미만이면 label=0


# -------------------------
# OpenCLIP 인코더
# -------------------------
class OpenCLIPEncoder:
    """OpenCLIP을 사용한 이미지 임베딩 생성"""
    
    def __init__(self, model_name: str = DEFAULT_MODEL_NAME, 
                    pretrained: str = DEFAULT_PRETRAINED,
                    device: str | None = None):
        self.device = self._pick_device(device)
        print(f"Using device: {self.device}")
        
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            model_name, pretrained=pretrained
        )
        self.model.to(self.device)
        self.model.eval()
        
        print(f"Loaded OpenCLIP model: {model_name} ({pretrained})")
    
    @staticmethod
    def _pick_device(explicit: str | None = None) -> str:
        if explicit:
            return explicit
        if torch.cuda.is_available():
            return "cuda"
        if torch.backends.mps.is_available():
            return "mps"
        return "cpu"
    
    @staticmethod
    def _l2_normalize(x: torch.Tensor, eps: float = 1e-12) -> torch.Tensor:
        return x / (x.norm(dim=-1, keepdim=True) + eps)
    
    @torch.inference_mode()
    def encode_image(self, pil_img: Image.Image) -> np.ndarray:
        """단일 이미지를 임베딩 벡터로 변환 (L2 정규화됨)"""
        img_tensor = self.preprocess(pil_img).unsqueeze(0).to(self.device)
        emb = self.model.encode_image(img_tensor)
        emb = self._l2_normalize(emb)
        return emb.detach().float().cpu().numpy()[0].astype(np.float32)


# -------------------------
# 유사도 계산
# -------------------------
def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """L2 정규화된 벡터 간 코사인 유사도 (내적)"""
    return float(np.dot(vec1, vec2))


def classify_similarity(similarity: float, threshold: float) -> int:
    """
    유사도를 기반으로 침해 위험 레이블 분류
    
    Args:
        similarity: 코사인 유사도 값 (0~1)
        threshold: 임계값
    
    Returns:
        1: 유사함 (침해 위험 높음)
        0: 유사하지 않음 (침해 위험 낮음)
    """
    return 1 if similarity >= threshold else 0


# -------------------------
# 이미지 로드
# -------------------------
def load_metadata(metadata_csv: Path) -> pd.DataFrame:
    """metadata.csv 파일 로드"""
    if not metadata_csv.exists():
        raise FileNotFoundError(f"Metadata 파일을 찾을 수 없습니다: {metadata_csv}")
    
    df = pd.read_csv(metadata_csv)
    print(f"Loaded {len(df)} records from {metadata_csv}")
    return df


def get_valid_image_paths(metadata_df: pd.DataFrame, base_dir: Path) -> List[Tuple[str, Path]]:
    """
    실제로 존재하는 이미지 파일 경로 목록 반환
    
    Returns:
        List of (image_id, full_path)
    """
    valid_paths = []
    
    for _, row in metadata_df.iterrows():
        img_id = row['image_id']
        img_path = base_dir / row['image_local_path']
        
        if img_path.exists():
            valid_paths.append((img_id, img_path))
        else:
            print(f"[WARN] 이미지 파일 없음: {img_path}")
    
    print(f"Found {len(valid_paths)} valid images")
    return valid_paths


def load_image_rgb(path: Path) -> Image.Image:
    """이미지를 RGB 모드로 로드"""
    img = Image.open(path)
    if img.mode != "RGB":
        img = img.convert("RGB")
    return img


# -------------------------
# 랜덤 페어 생성 및 유사도 계산
# -------------------------
def generate_random_pairs(
    image_paths: List[Tuple[str, Path]],
    num_pairs: int,
    encoder: OpenCLIPEncoder,
    threshold: float
) -> List[dict]:
    """
    랜덤으로 이미지 쌍을 선택하여 유사도 계산
    
    Args:
        image_paths: (image_id, path) 리스트
        num_pairs: 생성할 쌍의 개수
        encoder: OpenCLIP 인코더
        threshold: 유사도 임계값
    
    Returns:
        결과 딕셔너리 리스트
    """
    results = []
    
    for i in tqdm(range(num_pairs), desc="Computing similarities"):
        # 랜덤으로 2개 선택 (중복 없이)
        if len(image_paths) < 2:
            raise ValueError("이미지가 2개 미만입니다.")
        
        img1_id, img1_path = random.choice(image_paths)
        img2_id, img2_path = random.choice(image_paths)
        
        # 같은 이미지 선택 방지
        while img1_id == img2_id:
            img2_id, img2_path = random.choice(image_paths)
        
        # 이미지 로드 및 임베딩
        try:
            img1 = load_image_rgb(img1_path)
            img2 = load_image_rgb(img2_path)
            
            vec1 = encoder.encode_image(img1)
            vec2 = encoder.encode_image(img2)
            
            # 유사도 계산
            sim = cosine_similarity(vec1, vec2)
            label = classify_similarity(sim, threshold)
            
            results.append({
                'pair_id': i + 1,
                'image1_id': img1_id,
                'image1_path': str(img1_path),
                'image2_id': img2_id,
                'image2_path': str(img2_path),
                'cosine_similarity': sim,
                'label': label,
                'label_desc': '유사(침해위험 높음)' if label == 1 else '비유사(침해위험 낮음)'
            })
            
        except Exception as e:
            print(f"[ERROR] 쌍 {i+1} 처리 실패: {e}")
            continue
    
    return results


# -------------------------
# 결과 저장
# -------------------------
def save_results(results: List[dict], output_path: Path) -> None:
    """결과를 CSV로 저장"""
    if not results:
        print("[WARN] 저장할 결과가 없습니다.")
        return
    
    df = pd.DataFrame(results)
    df.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"\n결과 저장: {output_path}")
    
    # 통계 출력
    print("\n" + "=" * 60)
    print("결과 통계")
    print("=" * 60)
    print(f"총 쌍 개수: {len(df)}")
    print(f"유사 (label=1): {(df['label'] == 1).sum()} ({(df['label'] == 1).sum() / len(df) * 100:.1f}%)")
    print(f"비유사 (label=0): {(df['label'] == 0).sum()} ({(df['label'] == 0).sum() / len(df) * 100:.1f}%)")
    print(f"평균 유사도: {df['cosine_similarity'].mean():.4f}")
    print(f"최소 유사도: {df['cosine_similarity'].min():.4f}")
    print(f"최대 유사도: {df['cosine_similarity'].max():.4f}")
    print("=" * 60)


def print_sample_results(results: List[dict], n: int = 5) -> None:
    """샘플 결과 출력"""
    print(f"\n샘플 결과 (처음 {min(n, len(results))}개):")
    print("-" * 80)
    
    for r in results[:n]:
        print(f"Pair {r['pair_id']}:")
        print(f"  Image 1: {r['image1_id']}")
        print(f"  Image 2: {r['image2_id']}")
        print(f"  Similarity: {r['cosine_similarity']:.4f}")
        print(f"  Label: {r['label']} ({r['label_desc']})")
        print("-" * 80)


# -------------------------
# Main
# -------------------------
def main():
    parser = argparse.ArgumentParser(
        description="랜덤 이미지 쌍의 OpenCLIP 유사도 계산"
    )
    parser.add_argument(
        "--metadata",
        type=str,
        default="split_output/metadata.csv",
        help="Metadata CSV 파일 경로"
    )
    parser.add_argument(
        "--base_dir",
        type=str,
        default=".",
        help="이미지 경로 기준 디렉토리"
    )
    parser.add_argument(
        "--num_pairs",
        type=int,
        default=2000,
        help="생성할 랜덤 쌍의 개수"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help="유사도 임계값 (이상: label=1, 미만: label=0)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="similarity_results.csv",
        help="결과 저장 CSV 파일명"
    )
    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL_NAME,
        help="OpenCLIP 모델명"
    )
    parser.add_argument(
        "--pretrained",
        type=str,
        default=DEFAULT_PRETRAINED,
        help="Pretrained 가중치명"
    )
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        help="디바이스 (cuda, mps, cpu)"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="랜덤 시드"
    )
    
    args = parser.parse_args()
    
    # 랜덤 시드 설정
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    
    # 경로 설정
    metadata_path = Path(args.metadata)
    base_dir = Path(args.base_dir)
    output_path = Path(args.output)
    
    print("=" * 60)
    print("OpenCLIP Vector Similarity Comparison v2")
    print("=" * 60)
    print(f"Metadata: {metadata_path}")
    print(f"Base dir: {base_dir}")
    print(f"Number of pairs: {args.num_pairs}")
    print(f"Threshold: {args.threshold}")
    print(f"Output: {output_path}")
    print(f"Random seed: {args.seed}")
    print("=" * 60)
    
    # 1. Metadata 로드
    metadata_df = load_metadata(metadata_path)
    
    # 2. 유효한 이미지 경로 가져오기
    image_paths = get_valid_image_paths(metadata_df, base_dir)
    
    if len(image_paths) < 2:
        raise ValueError("유효한 이미지가 2개 미만입니다.")
    
    # 3. OpenCLIP 인코더 초기화
    encoder = OpenCLIPEncoder(
        model_name=args.model,
        pretrained=args.pretrained,
        device=args.device
    )
    
    # 4. 랜덤 쌍 생성 및 유사도 계산
    results = generate_random_pairs(
        image_paths=image_paths,
        num_pairs=args.num_pairs,
        encoder=encoder,
        threshold=args.threshold
    )
    
    # 5. 결과 저장
    save_results(results, output_path)
    
    # 6. 샘플 출력
    print_sample_results(results, n=10)
    
    print("\n✅ 완료!")


if __name__ == "__main__":
    main()
