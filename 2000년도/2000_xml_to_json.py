# xml_to_json.py
# XML(특허청 디자인 서지/이미지) → JSON(너가 지정한 스키마) 변환기

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

LC_CODE = "09-01"  # 르카르노 분류코드: 무조건 고정


# -------------------------
# Helpers
# -------------------------
_DATE_RE = re.compile(r"^\s*(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})\s*$")


def normalize_date(s: Optional[str]) -> Optional[str]:
    """'YYYY.MM.DD' / 'YYYY-MM-DD' / 'YYYY/MM/DD' -> 'YYYY-MM-DD'"""
    if not s:
        return None
    m = _DATE_RE.match(s)
    if not m:
        return s.strip()
    y, mo, d = m.group(1), int(m.group(2)), int(m.group(3))
    return f"{y}-{mo:02d}-{d:02d}"


def text_of(node: ET.Element, path: str) -> Optional[str]:
    """Find text by XPath-like query under node."""
    found = node.find(path)
    if found is None or found.text is None:
        return None
    v = found.text.strip()
    return v if v else None


def must(v: Optional[str], name: str) -> str:
    if not v:
        raise ValueError(f"필수 필드 누락: {name}")
    return v


# -------------------------
# Core conversion
# -------------------------
@dataclass(frozen=True)
class ConvertOptions:
    lc_code: str = LC_CODE


def convert_one_xml(xml_path: Path, *, opt: ConvertOptions = ConvertOptions()) -> list[dict]:
    """
    XML 1개 -> JSON 레코드 N개 반환
    (도면 1장(imagePath 1개)당 JSON 1개)
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()

    application_number = text_of(root, ".//applicationNumber")
    application_number = must(application_number, "applicationNumber")

    design_id = f"{application_number}-{opt.lc_code}"

    base_doc = {
        "design_id": design_id,
        "applicationNumber": application_number,
        "registrationNumber": text_of(root, ".//registrationNumber"),
        "publicationNumber": text_of(root, ".//publicationNumber"),
        "status": {
            "regFg": text_of(root, ".//regFg"),
            "admstStat": text_of(root, ".//admstStat"),
            "lastDispositionDate": normalize_date(text_of(root, ".//lastDispositionDate")),
        },
        "meta": {
            "articleName": text_of(root, ".//articleName"),
            "LCCode": opt.lc_code,  # 고정
            "designNumber": text_of(root, ".//designNumber"),
            "applicantName": text_of(root, ".//applicantName"),
            "agentName": text_of(root, ".//agentname"),
        },
        "creative": {
            "designSummary": text_of(root, ".//creativeSummaryInfo/designSummary") or text_of(root, ".//designSummary"),
            "designDescription": text_of(root, ".//creativeSummaryInfo/designDescription") or text_of(root, ".//designDescription"),
        },
    }

    # 이미지: <designImageInfo> 아래에 <imagePath>가 여러 개 존재하는 구조를 대응
    out: list[dict] = []
    image_paths = root.findall(".//designImageInfo//imagePath")
    if not image_paths:
        # 혹시 다른 구조일 때 대비: 전체에서 imagePath 탐색
        image_paths = root.findall(".//imagePath")

    for idx, img_node in enumerate(image_paths, 1):  # // Changed
        raw = text_of(img_node, "./number")

        # // Changed: 유효 도면번호는 1~99만 인정 (0, 300 같은 값 방지)
        n = int(raw) if raw and raw.isdigit() else None
        if n is None or not (1 <= n <= 99):
            n = idx  # 비정상이면 순번으로 재부여

        image_doc = json.loads(json.dumps(base_doc, ensure_ascii=False))  # // Changed: deep copy 안전
        image_doc["image"] = {
            "image_id": f"{application_number}-{n:02d}",  # 출원번호-도면번호(2자리)
            "imageName": text_of(img_node, "./imageName"),
            "imagePath": text_of(img_node, "./largePath"), #or text_of(img_node, "./smallPath"),
            "number": str(n),  # "1" 형태로 통일
        }
        out.append(image_doc)

    return out


# def convert_path(input_path: Path, output_dir: Path, *, opt: ConvertOptions = ConvertOptions()) -> list[Path]:
#     """
#     input_path가 파일이면 1개 변환,
#     디렉토리면 내부 *.xml 전부 변환해서 output_dir에 json 저장
#     """
#     output_dir.mkdir(parents=True, exist_ok=True)

#     xml_files = [input_path] if input_path.is_file() else sorted(input_path.glob("*.xml"))
#     written: list[Path] = []

#     for xp in xml_files:
#         docs = convert_one_xml(xp, opt=opt)
#         out_path = output_dir / f"{xp.stem}.json"
#         with out_path.open("w", encoding="utf-8") as f:
#             json.dump(docs, f, ensure_ascii=False, indent=2)
#         written.append(out_path)

#     return written


def convert_path(input_path: Path, output_dir: Path, *, opt: ConvertOptions = ConvertOptions()) -> list[Path]:
    """
    // Changed
    - XML 1개 -> 이미지 1장당 JSON 파일 1개 생성
    - 폴더면 내부 *.xml 전부 처리
    - 파일명은 image_id.json (예: 3020140001234-01.json)
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    xml_files = [input_path] if input_path.is_file() else sorted(input_path.glob("*.xml"))
    written: list[Path] = []

    for xp in xml_files:
        docs = convert_one_xml(xp, opt=opt)  # 이미지 개수만큼 dict 리스트

        for doc in docs:
            image_id = doc["image"]["image_id"]
            out_path = output_dir / f"{image_id}.json"
            with out_path.open("w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False, indent=2)
            written.append(out_path)

    return written



# -------------------------
# CLI
# -------------------------
def main() -> None:
    import argparse

    p = argparse.ArgumentParser(description="KIPRIS 디자인 XML -> JSON 변환기 (LCCode=09-01 고정)")

    DEFAULT_INPUT = Path("./2000_xml")  # // Changed
    DEFAULT_OUTPUT = Path("./2000_json")       # // Changed

    p.add_argument(
        "--input",
        "-i",
        default=str(DEFAULT_INPUT),             # // Changed
        help=f"XML 파일 경로 또는 XML 폴더 경로 (default: {DEFAULT_INPUT})",  # // Changed
    )
    p.add_argument(
        "--output",
        "-o",
        default=str(DEFAULT_OUTPUT),            # // Changed
        help=f"출력 폴더 (default: {DEFAULT_OUTPUT})",  # // Changed
    )
    args = p.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    output_dir = Path(args.output).expanduser().resolve()

    if not input_path.exists():  # // Changed
        raise SystemExit(f"❌ --input 경로가 존재하지 않습니다: {input_path}")  # // Changed

    written = convert_path(input_path, output_dir)
    print(f"✅ {len(written)}개 JSON 생성 완료")
    for w in written[:5]:
        print(f" - {w}")
    if len(written) > 5:
        print(f" - ... (+{len(written) - 5} files)")

if __name__ == "__main__":
    main()
