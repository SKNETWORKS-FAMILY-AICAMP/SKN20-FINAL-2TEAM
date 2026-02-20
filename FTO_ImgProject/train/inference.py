"""
CLIP Image Retrieval - 학습된 모델로 유사 이미지 검색
------------------------------------------------------
사용법:
  python inference.py \
    --query_image ./test.jpg \
    --gallery_dir ./images_reject \
    --checkpoint ./checkpoints/best_model.pt \
    --top_k 5
"""

import os
import argparse
import logging
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image

import clip


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--query_image",  type=str, required=True,
                        help="검색할 query 이미지 경로")
    parser.add_argument("--gallery_dir",  type=str, required=True,
                        help="검색 대상 이미지 폴더")
    parser.add_argument("--checkpoint",   type=str, required=True,
                        help="학습된 모델 체크포인트 경로")
    parser.add_argument("--clip_model",   type=str, default="ViT-B/32")
    parser.add_argument("--top_k",        type=int, default=5)
    parser.add_argument("--batch_size",   type=int, default=32)
    return parser.parse_args()


def build_gallery_index(model, preprocess, gallery_dir: str,
                         batch_size: int, device):
    """갤러리 폴더의 모든 이미지 임베딩을 미리 추출해 인덱스 구축"""
    img_paths = sorted([
        str(p) for p in Path(gallery_dir).glob("*.jpg")
    ] + [
        str(p) for p in Path(gallery_dir).glob("*.png")
    ])

    if not img_paths:
        raise FileNotFoundError(f"갤러리 폴더에 이미지 없음: {gallery_dir}")

    all_feats = []
    model.eval()

    with torch.no_grad():
        for i in range(0, len(img_paths), batch_size):
            batch_paths = img_paths[i:i+batch_size]
            imgs = torch.stack([
                preprocess(Image.open(p).convert("RGB"))
                for p in batch_paths
            ]).to(device)
            feats = model.encode_image(imgs).float()
            feats = F.normalize(feats, dim=-1)
            all_feats.append(feats.cpu())

    gallery_feats = torch.cat(all_feats)  # [N, D]
    logging.info(f"갤러리 인덱스 구축 완료: {len(img_paths)}장")
    return img_paths, gallery_feats


def retrieve(query_path: str, img_paths, gallery_feats,
             model, preprocess, device, top_k: int):
    """query 이미지와 가장 유사한 top_k 이미지 반환"""
    model.eval()
    with torch.no_grad():
        query_img   = preprocess(Image.open(query_path).convert("RGB")).unsqueeze(0).to(device)
        query_feat  = model.encode_image(query_img).float()
        query_feat  = F.normalize(query_feat, dim=-1).cpu()

    sims = torch.matmul(query_feat, gallery_feats.T).squeeze(0)  # [N]
    top_indices = sims.topk(top_k).indices.tolist()

    results = [
        {"rank": i+1, "path": img_paths[idx], "score": sims[idx].item()}
        for i, idx in enumerate(top_indices)
    ]
    return results


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    args = get_args()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # 모델 로드
    model, preprocess = clip.load(args.clip_model, device=device)
    model = model.float()

    ckpt = torch.load(args.checkpoint, map_location=device)
    model.load_state_dict(ckpt["model_state"])
    logging.info(f"체크포인트 로드: epoch={ckpt['epoch']}, "
                 f"recalls={ckpt['recalls']}")

    # 갤러리 인덱스
    img_paths, gallery_feats = build_gallery_index(
        model, preprocess, args.gallery_dir, args.batch_size, device)

    # 검색
    results = retrieve(
        args.query_image, img_paths, gallery_feats,
        model, preprocess, device, args.top_k
    )

    print(f"\n🔍 Query: {args.query_image}")
    print(f"Top-{args.top_k} 유사 이미지:")
    for r in results:
        print(f"  #{r['rank']} | Score: {r['score']:.4f} | {os.path.basename(r['path'])}")


if __name__ == "__main__":
    main()
