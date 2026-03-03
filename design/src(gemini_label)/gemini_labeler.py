"""
Gemini 형태 특징 추출기 (Task 1)
- images_v2에서 이미지를 읽어 Gemini 1.5 Flash로 형태 특징 추출
- 결과를 design/data/labels/{image_id}.json에 저장

실행 방법:
  # 특징 추출 (기본 100장)
  python gemini_labeler.py extract --api-key YOUR_KEY

  # 환경변수 사용
  GEMINI_API_KEY=YOUR_KEY python gemini_labeler.py extract

  # 라벨 + 기존 JSON 병합 (json_merged/ 에 저장)
  python gemini_labeler.py merge
"""

import argparse
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image

# ── 경로 설정 ────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent  # design/
DATA_DIR = BASE_DIR / "data"

# ── .env 로드: design/.env → 루트 .env 순서 (override=False: 먼저 로드된 값 우선) ──
load_dotenv(BASE_DIR / ".env", override=False)           # design/.env
load_dotenv(BASE_DIR.parent / ".env", override=False)    # SKN20-FINAL-2TEAM/.env
IMAGES_DIR = DATA_DIR / "images_v2"
JSON_DIR = DATA_DIR / "json"
LABELS_DIR = DATA_DIR / "labels"
FAILED_LOG = LABELS_DIR / "failed_list.txt"

# ── Gemini 프롬프트 ────────────────────────────────────────────────────────
GEMINI_PROMPT = """\
아래 화장품 용기 디자인 특허 이미지를 특허 심사관 관점에서 분석해줘.
각 항목을 아래 선택지 중에서만 골라 JSON 형식으로 반환해. 다른 텍스트 없이.

[용기유형] 하나 선택:
병형 | 항아리형 | 튜브형 | 스틱형 | 콤팩트형 | 파우치형 | 기타

[실루엣.단면] 하나 선택:
원형단면 | 타원형단면 | 정사각단면 | 직사각단면 | 다각형단면 | 비정형단면

[실루엣.비율] 하나 선택:
세로형 | 정방형 | 가로형

[실루엣.윤곽] 하나 선택:
직선형 | 완만한곡선형 | 사다리꼴형 | 역사다리꼴형 | 모래시계형 | 볼형 | 달걀형

[연결부형태] 하나 선택:
없음 | 직선연결 | 완만한경사 | 급경사 | 단차형 | 둥근어깨 | 각진어깨

[세부조형] 해당하는 것 최대 3개 선택:
세로리브 | 가로리브 | 나선형리브 | 세로홈 | 격자패턴 | 엠보싱패턴 |
허리곡선 | 하단굽 | 각진모서리 | 둥근모서리 | 손잡이 | 날개형돌출 | 그립텍스처 | 투명창 | 없음

[디스펜서] 하나 선택:
없음 | 일반펌프 | 에어리스펌프 | 스프레이 | 롤온 | 드로퍼 | 트위스트업 | 기타

[뚜껑.형태] 하나 선택:
없음 | 평면캡 | 돔형캡 | 스크류캡 | 힌지캡 | 슬라이드캡 | 이중캡 | 기타

[뚜껑.결합] 하나 선택:
없음 | 끼움식 | 나사식 | 자석식 | 힌지식

{
  "용기유형": "",
  "실루엣": {
    "단면": "",
    "비율": "",
    "윤곽": ""
  },
  "연결부형태": "",
  "세부조형": [],
  "디스펜서": "",
  "뚜껑": {
    "형태": "",
    "결합": ""
  }
}"""


def build_summary(label: dict) -> str:
    """고정 필드 조합으로 주요특징요약 자동 생성."""
    parts = []
    if label.get("용기유형"):
        parts.append(label["용기유형"])
    s = label.get("실루엣", {})
    silhouette = " ".join(filter(None, [s.get("단면"), s.get("비율"), s.get("윤곽")]))
    if silhouette:
        parts.append(silhouette)
    if label.get("디스펜서") and label["디스펜서"] != "없음":
        parts.append(label["디스펜서"])
    lid = label.get("뚜껑", {}).get("형태", "")
    if lid and lid != "없음":
        parts.append(lid)
    detail = [d for d in label.get("세부조형", []) if d != "없음"]
    if detail:
        parts.append("+".join(detail))
    return " / ".join(parts)


def parse_image_id(filename: str) -> str | None:
    """
    이미지 파일명에서 image_id 추출.
    예) 3020040015192-api_xml-0_000.JPG → 3020040015192-0
    """
    stem = Path(filename).stem  # 3020040015192-api_xml-0_000
    if "-api_xml-" not in stem:
        return None
    app_num, rest = stem.split("-api_xml-", 1)  # '3020040015192', '0_000'
    number = rest.split("_")[0]  # '0'
    return f"{app_num}-{number}"


def call_gemini(model, img_path: Path) -> dict | None:
    """Gemini API 호출 → JSON dict 반환. 실패 시 None."""
    import google.generativeai as genai  # 지연 import (설치 여부 확인 후)

    img = Image.open(img_path).convert("RGB")
    try:
        response = model.generate_content([GEMINI_PROMPT, img])
        raw = response.text.strip()

        # 코드블록 감싸진 경우 제거 (```json ... ```)
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

        return json.loads(raw)
    except Exception as e:
        print(f"  [오류] Gemini 응답 파싱 실패: {e}")
        return None


def cmd_extract(args):
    """이미지 → Gemini 형태 특징 추출 → labels/ 저장"""
    load_dotenv()
    api_key = args.api_key or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY가 없습니다. --api-key 옵션 또는 환경변수를 설정하세요.")

    try:
        import google.generativeai as genai
    except ImportError:
        raise SystemExit(
            "google-generativeai 패키지가 없습니다.\n"
            "pip install google-generativeai  를 실행하세요."
        )

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")

    LABELS_DIR.mkdir(parents=True, exist_ok=True)

    # 이미지 목록 (정렬 후 limit 적용)
    all_images = sorted(IMAGES_DIR.glob("*.JPG")) + sorted(IMAGES_DIR.glob("*.jpg"))
    images = all_images[: args.limit]
    total = len(images)
    print(f"총 {total}장 처리 시작 (limit={args.limit})")

    failed = []
    success = 0

    for idx, img_path in enumerate(images, 1):
        image_id = parse_image_id(img_path.name)
        if image_id is None:
            print(f"[{idx}/{total}] 파일명 파싱 실패: {img_path.name} → 스킵")
            failed.append(img_path.name)
            continue

        label_path = LABELS_DIR / f"{image_id}.json"

        # 이미 추출된 경우 스킵
        if label_path.exists() and not args.force:
            print(f"[{idx}/{total}] {image_id} — 이미 존재, 스킵")
            success += 1
            continue

        print(f"[{idx}/{total}] {image_id} 처리 중...", end=" ", flush=True)
        result = call_gemini(model, img_path)

        if result is None:
            print("실패")
            failed.append(img_path.name)
        else:
            result["_image_id"] = image_id  # 출처 추적용
            label_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print("완료")
            success += 1

        # Rate limit 방지
        time.sleep(args.delay)

    # 실패 목록 기록
    if failed:
        with open(FAILED_LOG, "a", encoding="utf-8") as f:
            f.write("\n".join(failed) + "\n")
        print(f"\n실패: {len(failed)}장 → {FAILED_LOG}")

    print(f"\n완료: {success}/{total}장 성공")


def cmd_merge(args):
    """
    labels/{image_id}.json + json/{image_id}.json 병합
    → json_merged/{image_id}.json 에 gemini_features 필드 추가하여 저장
    """
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    label_files = list(LABELS_DIR.glob("*.json"))
    label_files = [f for f in label_files if f.name != "failed_list.txt"]

    merged = 0
    skipped = 0

    for label_path in label_files:
        image_id = label_path.stem  # e.g. 3020040015192-0
        json_path = JSON_DIR / f"{image_id}.json"

        if not json_path.exists():
            print(f"[스킵] JSON 없음: {image_id}")
            skipped += 1
            continue

        base_data = json.loads(json_path.read_text(encoding="utf-8"))
        label_data = json.loads(label_path.read_text(encoding="utf-8"))

        # _image_id 메타 필드는 제외하고 병합
        label_data.pop("_image_id", None)
        base_data["gemini_features"] = label_data

        out_path = output_dir / f"{image_id}.json"
        out_path.write_text(json.dumps(base_data, ensure_ascii=False, indent=2), encoding="utf-8")
        merged += 1

    print(f"병합 완료: {merged}개 → {output_dir}")
    if skipped:
        print(f"스킵 (JSON 없음): {skipped}개")


# ── CLI ────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Gemini 형태 특징 추출기")
    sub = parser.add_subparsers(dest="command", required=True)

    # extract 서브커맨드
    ep = sub.add_parser("extract", help="이미지에서 Gemini 형태 특징 추출")
    ep.add_argument("--api-key", default=None, help="Gemini API 키 (없으면 GEMINI_API_KEY 환경변수)")
    ep.add_argument("--limit", type=int, default=100, help="처리할 이미지 수 (기본 100)")
    ep.add_argument("--delay", type=float, default=1.0, help="요청 간 딜레이 초 (기본 1.0)")
    ep.add_argument("--force", action="store_true", help="이미 추출된 파일도 덮어쓰기")

    # merge 서브커맨드
    mp = sub.add_parser("merge", help="labels/ 와 json/ 병합")
    mp.add_argument(
        "--output-dir",
        default=str(DATA_DIR / "json_merged"),
        help="병합 결과 저장 폴더 (기본: design/data/json_merged)",
    )

    args = parser.parse_args()

    if args.command == "extract":
        cmd_extract(args)
    elif args.command == "merge":
        cmd_merge(args)


if __name__ == "__main__":
    main()
