# openclip_vector_similarity.py
# ------------------------------------------------------------
# 목적:
# - 09-01/2000년도/2000_json 폴더의 JSON들을 읽어서
#   1) 이미지 다운로드 (image.imagePath -> img/)
#   2) 텍스트(document) 구성
#   3) OpenCLIP ViT-L/14로 image/text embedding (같은 공간)
#   4) L2 normalize 후 cosine similarity 계산
#   5) metadata + embedding + similarity 결과 저장
#
# 실행 예)
#   python openclip_vector_similarity.py
#   python openclip_vector_similarity.py --input_dir "09-01/2000년도/2000_json" --output_dir "09-01/2000년도"
#   python openclip_vector_similarity.py --batch_size 64
# ------------------------------------------------------------

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import requests
from PIL import Image
from tqdm import tqdm

import torch
import open_clip


# -------------------------
# Config
# -------------------------
DEFAULT_MODEL_NAME = "ViT-L-14"
DEFAULT_PRETRAINED = "laion2b_s32b_b82k"
DEFAULT_BATCH_SIZE = 32


# -------------------------
# Data structures
# -------------------------
@dataclass(frozen=True)
class Record:
    doc_id: str                # design_id 혹은 applicationNumber 기반 ID
    image_id: str
    image_url: str
    image_local_path: str
    document: str              # text document (same-space text embedding)
    metadata: Dict[str, Any]   # chroma metadatas 등에 그대로 넣을 dict


# -------------------------
# Utils
# -------------------------
def pick_device(explicit: Optional[str] = None) -> str:
    if explicit:
        return explicit
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def l2_normalize(x: torch.Tensor, eps: float = 1e-12) -> torch.Tensor:
    return x / (x.norm(dim=-1, keepdim=True) + eps)


def batch_cosine_sim(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Batch cosine similarity (a, b are already L2-normalized)"""
    return np.sum(a * b, axis=-1)


def safe_get(d: Dict[str, Any], path: List[str], default=None):
    cur = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def build_document(j: Dict[str, Any]) -> str:
    """
    "document" = Chroma documents처럼 텍스트 본문.
    (이미지↔텍스트 같은 공간이 목적이므로, CLIP 텍스트 인코더로 임베딩할 텍스트를 여기에 구성)
    """
    article = safe_get(j, ["meta", "articleName"], "") or ""
    lc = safe_get(j, ["meta", "LCCode"], "") or ""
    applicant = safe_get(j, ["meta", "applicantName"], "") or ""
    summary = safe_get(j, ["creative", "designSummary"], "") or ""
    desc = safe_get(j, ["creative", "designDescription"], "") or ""

    parts = [
        f"제품명: {article}",
        f"Locarno: {lc}",
        f"출원인: {applicant}",
        f"요점: {summary}",
        f"설명: {desc}",
    ]
    return "\n".join([p for p in parts if p.strip()])


def download_image(url: str, save_path: Path, timeout: int = 30) -> bool:
    save_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        save_path.write_bytes(r.content)
        return True
    except requests.exceptions.RequestException as e:
        print(f"[WARN] 이미지 다운로드 실패: {url} -> {e}")
        return False


def open_image_rgb(path: Path) -> Image.Image:
    img = Image.open(path)
    if img.mode != "RGB":
        img = img.convert("RGB")
    return img


def chunked(lst: List, n: int):
    """리스트를 n개씩 나누는 제너레이터"""
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


# -------------------------
# OpenCLIP Encoder (Batch 지원)
# -------------------------
class OpenCLIPSameSpaceEncoder:
    def __init__(self, model_name: str, pretrained: str, device: Optional[str] = None):
        self.device = pick_device(device)
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            model_name, pretrained=pretrained
        )
        self.tokenizer = open_clip.get_tokenizer(model_name)

        self.model.to(self.device)
        self.model.eval()

    @torch.inference_mode()
    def encode_images_batch(self, pil_images: List[Image.Image]) -> np.ndarray:
        """배치 이미지 인코딩"""
        tensors = torch.stack([self.preprocess(img) for img in pil_images]).to(self.device)
        emb = self.model.encode_image(tensors)
        emb = l2_normalize(emb).detach().float().cpu().numpy()
        return emb.astype(np.float32)

    @torch.inference_mode()
    def encode_texts_batch(self, texts: List[str]) -> np.ndarray:
        """배치 텍스트 인코딩"""
        tokens = self.tokenizer(texts).to(self.device)
        emb = self.model.encode_text(tokens)
        emb = l2_normalize(emb).detach().float().cpu().numpy()
        return emb.astype(np.float32)

    # 단일 처리용 (하위 호환)
    def encode_image(self, pil_img: Image.Image) -> np.ndarray:
        return self.encode_images_batch([pil_img])[0]

    def encode_text(self, text: str) -> np.ndarray:
        return self.encode_texts_batch([text])[0]


# -------------------------
# Main pipeline
# -------------------------
def load_records(input_dir: Path, output_dir: Path, download: bool = True) -> List[Record]:
    img_dir = output_dir / "img"
    records: List[Record] = []

    json_files = sorted(input_dir.glob("*.json"))
    
    for jp in tqdm(json_files, desc="Loading JSONs"):
        j = json.loads(jp.read_text(encoding="utf-8"))

        design_id = safe_get(j, ["design_id"], "") or jp.stem
        app_no = safe_get(j, ["applicationNumber"], "") or ""
        image_id = safe_get(j, ["image", "image_id"], "") or jp.stem
        image_name = safe_get(j, ["image", "imageName"], "image.jpg") or "image.jpg"
        image_url = safe_get(j, ["image", "imagePath"], "") or ""

        doc_id = f"{design_id}::{image_id}"

        ext = Path(image_name).suffix if Path(image_name).suffix else ".jpg"
        local_name = doc_id.replace("::", "__").replace("/", "_") + ext
        local_path = img_dir / local_name

        if download and image_url:
            _ = download_image(image_url, local_path)

        document = build_document(j)

        metadata = {
            "design_id": design_id,
            "applicationNumber": app_no,
            "registrationNumber": safe_get(j, ["registrationNumber"], None),
            "articleName": safe_get(j, ["meta", "articleName"], None),
            "LCCode": safe_get(j, ["meta", "LCCode"], None),
            "image_id": image_id,
            "image_url": image_url,
            "image_local_path": str(local_path),
            "source_json": str(jp),
            "modality": "image+text",
        }

        records.append(
            Record(
                doc_id=doc_id,
                image_id=image_id,
                image_url=image_url,
                image_local_path=str(local_path),
                document=document,
                metadata=metadata,
            )
        )

    return records


def run_embedding(
    records: List[Record],
    model_name: str,
    pretrained: str,
    device: Optional[str],
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, List[Record]]:
    """
    배치 단위로 이미지/텍스트 임베딩 수행
    Returns: (img_vecs, txt_vecs, sims, valid_records)
    """
    enc = OpenCLIPSameSpaceEncoder(model_name=model_name, pretrained=pretrained, device=device)

    # 유효한 레코드만 필터링 (이미지 파일 존재하는 것만)
    valid_records: List[Record] = []
    for r in records:
        p = Path(r.image_local_path)
        if p.exists():
            valid_records.append(r)
        else:
            print(f"[WARN] 이미지 파일 없음, 스킵: {r.image_local_path}")

    if not valid_records:
        raise RuntimeError("임베딩할 이미지가 없습니다. (다운로드 실패 or input_dir 비었음)")

    print(f"총 {len(valid_records)}개 레코드 임베딩 시작 (batch_size={batch_size})")

    all_img_vecs: List[np.ndarray] = []
    all_txt_vecs: List[np.ndarray] = []

    # 배치 단위로 처리
    batches = list(chunked(valid_records, batch_size))
    
    for batch_records in tqdm(batches, desc="Embedding batches"):
        # 이미지 로드
        images = [open_image_rgb(Path(r.image_local_path)) for r in batch_records]
        texts = [r.document for r in batch_records]

        # 배치 임베딩
        img_vecs = enc.encode_images_batch(images)
        txt_vecs = enc.encode_texts_batch(texts)

        all_img_vecs.append(img_vecs)
        all_txt_vecs.append(txt_vecs)

    # 전체 결합
    img_vecs_all = np.concatenate(all_img_vecs, axis=0)
    txt_vecs_all = np.concatenate(all_txt_vecs, axis=0)

    # Cosine similarity 계산 (이미 L2 normalized)
    sims = batch_cosine_sim(img_vecs_all, txt_vecs_all)

    return img_vecs_all, txt_vecs_all, sims, valid_records


def save_outputs(
    output_dir: Path,
    records: List[Record],
    img_vecs: np.ndarray,
    txt_vecs: np.ndarray,
    sims: np.ndarray,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    assert len(records) == img_vecs.shape[0] == txt_vecs.shape[0] == sims.shape[0]

    # 1) metadata + document jsonl
    meta_path = output_dir / "openclip_metadata.jsonl"
    with meta_path.open("w", encoding="utf-8") as f:
        for r, s in zip(records, sims):
            row = {
                "id": r.doc_id,
                "document": r.document,
                "metadata": r.metadata,
                "image_text_cosine": float(s),
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # 2) embedding npz
    np.savez_compressed(
        output_dir / "openclip_embeddings.npz",
        ids=np.array([r.doc_id for r in records]),
        image_embeddings=img_vecs,
        text_embeddings=txt_vecs,
        image_text_cosine=sims,
    )


def maybe_build_chroma(
    output_dir: Path,
    collection_name: str,
    records: List[Record],
    txt_vecs: np.ndarray,
    img_vecs: np.ndarray,
) -> None:
    """
    ChromaDB에 텍스트/이미지 레코드 저장 (upsert 사용)
    """
    import chromadb

    persist_dir = output_dir / "chroma_openclip"
    client = chromadb.PersistentClient(path=str(persist_dir))
    col = client.get_or_create_collection(name=collection_name)

    assert len(records) == txt_vecs.shape[0] == img_vecs.shape[0]

    # 텍스트 레코드 (upsert로 중복 방지)
    col.upsert(
        ids=[f"{r.doc_id}::text" for r in records],
        documents=[r.document for r in records],
        metadatas=[{**r.metadata, "modality": "text"} for r in records],
        embeddings=txt_vecs.tolist(),
    )

    # 이미지 레코드
    col.upsert(
        ids=[f"{r.doc_id}::image" for r in records],
        documents=["" for _ in records],
        metadatas=[{**r.metadata, "modality": "image"} for r in records],
        embeddings=img_vecs.tolist(),
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--input_dir", type=str, default="./2000_json")
    p.add_argument("--output_dir", type=str, default=".")
    p.add_argument("--model_name", type=str, default=DEFAULT_MODEL_NAME)
    p.add_argument("--pretrained", type=str, default=DEFAULT_PRETRAINED)
    p.add_argument("--device", type=str, default=None)
    p.add_argument("--batch_size", type=int, default=DEFAULT_BATCH_SIZE, help="배치 크기 (기본값: 32)")
    p.add_argument("--no_download", action="store_true")
    p.add_argument("--build_chroma", action="store_true")
    p.add_argument("--collection", type=str, default="openclip_same_space")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    print(f"📂 Input: {input_dir}")
    print(f"📂 Output: {output_dir}")
    print(f"🔧 Model: {args.model_name} / {args.pretrained}")
    print(f"🔧 Batch size: {args.batch_size}")
    print(f"🔧 Device: {pick_device(args.device)}")

    records = load_records(input_dir=input_dir, output_dir=output_dir, download=not args.no_download)
    if not records:
        raise RuntimeError(f"JSON 파일을 찾지 못했습니다: {input_dir}")

    print(f"📄 로드된 레코드: {len(records)}개")

    img_vecs, txt_vecs, sims, valid_records = run_embedding(
        records=records,
        model_name=args.model_name,
        pretrained=args.pretrained,
        device=args.device,
        batch_size=args.batch_size,
    )

    save_outputs(
        output_dir=output_dir,
        records=valid_records,
        img_vecs=img_vecs,
        txt_vecs=txt_vecs,
        sims=sims,
    )

    if args.build_chroma:
        maybe_build_chroma(
            output_dir=output_dir,
            collection_name=args.collection,
            records=valid_records,
            txt_vecs=txt_vecs,
            img_vecs=img_vecs,
        )

    print("\n✅ 완료")
    print(f"- 임베딩된 레코드: {len(valid_records)}개")
    print(f"- output: {output_dir}")
    print(f"- metadata: {output_dir / 'openclip_metadata.jsonl'}")
    print(f"- embeddings: {output_dir / 'openclip_embeddings.npz'}")
    if args.build_chroma:
        print(f"- chroma persist: {output_dir / 'chroma_openclip'}")


if __name__ == "__main__":
    main()