from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors


def build_markdown_report(
    user_image_id: str,
    explanation_json: Dict[str, Any],
    items: List[Dict[str, Any]],
) -> str:
    """마크다운 형식 리포트 생성."""
    lines: List[str] = []

    lines.append("# Image Similarity Analysis Report")
    lines.append("")
    lines.append("## 1. User Image Overview")
    lines.append(f"- **Image ID**: {user_image_id}")
    lines.append("- **Embedding Model**: OpenCLIP (ViT-B-32)")
    lines.append("- **Similarity Metric**: Cosine Similarity")
    lines.append("")

    # Summary
    summary = explanation_json.get("summary", {})
    lines.append("## 2. Summary")
    lines.append(f"- **Number of Similar Images**: {summary.get('num_similar', len(items))}")
    if summary.get("notes"):
        lines.append(f"- **Notes**: {summary.get('notes')}")
    lines.append("")

    # Ranking table
    lines.append("## 3. Similar Image Ranking")
    lines.append("")
    lines.append("| Rank | Image ID | Similarity | Strength |")
    lines.append("|-----:|----------|----------:|----------|")

    ranking = explanation_json.get("ranking", [])
    for r in ranking:
        lines.append(
            f"| {r.get('rank', '-')} | {r.get('reference_image_id', '-')} | "
            f"{r.get('cosine_similarity', 0):.4f} | {r.get('strength', '-')} |"
        )
    lines.append("")

    # Detailed analysis
    lines.append("## 4. Detailed Similarity Analysis")
    lines.append("")

    for r in ranking:
        rid = r.get("reference_image_id", "Unknown")
        lines.append(f"### {rid}")
        lines.append(f"- **Similarity Score**: {r.get('cosine_similarity', 0):.4f}")
        lines.append(f"- **Strength**: {r.get('strength', '-')}")
        lines.append("")
        lines.append("**Why Similar:**")
        for reason in r.get("why_similar", []) or []:
            lines.append(f"- {reason}")
        lines.append("")

        ev = r.get("evidence", {}) or {}
        meta_fields = ev.get("metadata_fields_used", []) or []
        doc_fields = ev.get("document_fields_used", []) or []
        lines.append(f"**Evidence (metadata)**: {', '.join(meta_fields) if meta_fields else 'N/A'}")
        lines.append(f"**Evidence (document)**: {', '.join(doc_fields) if doc_fields else 'N/A'}")

        limitations = r.get("limitations", []) or []
        if limitations:
            lines.append(f"**Limitations**: {', '.join(limitations)}")
        lines.append("")

    # Methodology
    lines.append("## 5. Data Sources & Methodology")
    lines.append("- **Metadata**: openclip_metadata.jsonl")
    lines.append("- **Embeddings**: openclip_embeddings.npz")
    lines.append("- **Documents**: documents.jsonl")
    lines.append("- **Similarity**: Cosine similarity over OpenCLIP embeddings")
    lines.append("- **Explanation**: Local LLM (Ollama)")
    lines.append("")

    # Raw data
    lines.append("## 6. Raw Similarity Data")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(items, ensure_ascii=False, indent=2))
    lines.append("```")

    return "\n".join(lines)


def markdown_to_pdf(md_text: str, pdf_path: Path) -> None:
    """마크다운 텍스트를 PDF로 변환 (간단 버전)."""
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Code", fontName="Courier", fontSize=8, leading=10))

    story = []

    for line in md_text.splitlines():
        line = line.rstrip()

        if line.startswith("# "):
            story.append(Paragraph(line[2:], styles["Heading1"]))
        elif line.startswith("## "):
            story.append(Paragraph(line[3:], styles["Heading2"]))
        elif line.startswith("### "):
            story.append(Paragraph(line[4:], styles["Heading3"]))
        elif line.startswith("```"):
            continue  # 코드블록 마커 스킵
        elif line.startswith("- "):
            story.append(Paragraph(f"• {line[2:]}", styles["Normal"]))
        elif line.startswith("|"):
            continue  # 테이블은 간단 버전에서 스킵
        elif line == "":
            story.append(Spacer(1, 6))
        else:
            # 볼드 처리
            line = line.replace("**", "<b>", 1).replace("**", "</b>", 1)
            story.append(Paragraph(line, styles["Normal"]))

    doc.build(story)