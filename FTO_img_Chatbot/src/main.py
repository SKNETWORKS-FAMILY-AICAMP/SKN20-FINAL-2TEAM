from __future__ import annotations
import argparse
import sys
from pathlib import Path

import pandas as pd

from config import Config
from io_utils import build_index_by_key, load_embeddings_npz
from embedder import OpenCLIPEmbedder
from similarity import retrieve_similar
from llm_explain import LLMExplainer
from report import build_markdown_report, markdown_to_pdf


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Image Similarity Analysis with OpenCLIP + Local LLM"
    )
    p.add_argument(
        "--image_path",
        type=str,
        required=True,
        help="User input image file path",
    )
    p.add_argument(
        "--image_id",
        type=str,
        default="user_input",
        help="User image id label (default: user_input)",
    )
    p.add_argument(
        "--out_name",
        type=str,
        default="similarity_report",
        help="Base filename for outputs (default: similarity_report)",
    )
    p.add_argument(
        "--pdf",
        action="store_true",
        help="Also export PDF report",
    )
    p.add_argument(
        "--top_k",
        type=int,
        default=None,
        help="Override top_k from config",
    )
    p.add_argument(
        "--min_similarity",
        type=float,
        default=None,
        help="Override min_similarity from config",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    cfg = Config()

    # CLI 오버라이드
    top_k = args.top_k if args.top_k is not None else cfg.top_k
    min_similarity = args.min_similarity if args.min_similarity is not None else cfg.min_similarity

    # 출력 디렉토리 생성
    cfg.output_dir.mkdir(parents=True, exist_ok=True)

    # 이미지 파일 확인
    image_path = Path(args.image_path)
    if not image_path.exists():
        print(f"❌ Error: Image file not found: {image_path}")
        sys.exit(1)

    print(f"📷 Input image: {image_path}")
    print(f"🔧 Config: top_k={top_k}, min_similarity={min_similarity}")

    # 1) Load indices
    print("📂 Loading metadata and documents...")
    metadata_idx = build_index_by_key(cfg.metadata_jsonl, key_field="id")
    documents_idx = build_index_by_key(cfg.documents_jsonl, key_field="id")
    print(f"   - Metadata entries: {len(metadata_idx)}")
    print(f"   - Document entries: {len(documents_idx)}")

    # 2) Load reference embeddings
    print("📂 Loading embeddings...")
    ref_ids, ref_emb = load_embeddings_npz(cfg.embeddings_npz)
    print(f"   - Reference images: {len(ref_ids)}")
    print(f"   - Embedding dim: {ref_emb.shape[1]}")

    # 3) Embed user image
    print("🔄 Embedding user image...")
    embedder = OpenCLIPEmbedder(cfg.model_name, cfg.pretrained, cfg.device)
    user_vec = embedder.embed_image_path(image_path)
    print(f"   - User embedding shape: {user_vec.shape}")

    # 4) Retrieve similar images
    print("🔍 Searching similar images...")
    items = retrieve_similar(
        user_vec=user_vec,
        ref_ids=ref_ids,
        ref_emb=ref_emb,
        metadata_idx=metadata_idx,
        documents_idx=documents_idx,
        top_k=top_k,
        min_similarity=min_similarity,
        assume_ref_normalized=True,
    )
    print(f"   - Found {len(items)} similar images (>= {min_similarity})")

    if not items:
        print("⚠️ No similar images found. Try lowering min_similarity.")
        sys.exit(0)

    # 5) Save similarity CSV
    sim_rows = [
        {
            "reference_image_id": it.reference_image_id,
            "cosine_similarity_score": round(it.cosine_similarity, 6),
        }
        for it in items
    ]
    sim_df = pd.DataFrame(sim_rows)
    sim_csv_path = cfg.output_dir / "user_similarity_results.csv"
    sim_df.to_csv(sim_csv_path, index=False, encoding="utf-8-sig")

    # 6) LLM explanation
    print("🤖 Generating LLM explanation...")
    explainer = LLMExplainer(model=cfg.llm_model, base_url=cfg.ollama_base_url)

    llm_input_items = [
        {
            "reference_image_id": it.reference_image_id,
            "cosine_similarity": round(it.cosine_similarity, 4),
            "metadata": it.metadata,
            "document": it.document,
        }
        for it in items
    ]
    explanation = explainer.explain(user_image_id=args.image_id, items=llm_input_items)

    # 에러 체크
    if "error" in explanation:
        print(f"⚠️ LLM Warning: {explanation['summary'].get('notes', 'Unknown error')}")

    # 7) Report export
    print("📝 Generating reports...")
    md = build_markdown_report(args.image_id, explanation, llm_input_items)

    md_path = cfg.output_dir / f"{args.out_name}.md"
    md_path.write_text(md, encoding="utf-8")

    if args.pdf:
        pdf_path = cfg.output_dir / f"{args.out_name}.pdf"
        markdown_to_pdf(md, pdf_path)

    # 8) Done
    print("")
    print("✅ Done!")
    print(f"   📊 Similarity CSV: {sim_csv_path}")
    print(f"   📄 Report (MD):    {md_path}")
    if args.pdf:
        print(f"   📄 Report (PDF):   {pdf_path}")


if __name__ == "__main__":
    main()