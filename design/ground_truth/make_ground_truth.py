"""
Ground Truth CSV 생성 스크립트
- Task 1: 같은 출원번호 내 다른 도면 (도면0=query, relevant 1개) 
- Task 2: 같은 출원인 & 같은 등록일자, 다른 출원번호 (도면0=query, relevant 2개) 
- CSV 파일 각각 별도 저장
"""
import json
import os
import csv
import random
from collections import defaultdict

# 경로 설정
BASE_DIR = r"C:\Users\playdata2\Desktop\SKN_AI_20\SKN20-FINAL-2TEAM(vb1)\design\data"
JSON_DIR = r"C:\Users\playdata2\Desktop\SKN_AI_20\SKN20-FINAL-2TEAM(vb1)\design\data\json(21,909개)"
IMAGE_DIR = r"C:\Users\playdata2\Desktop\SKN_AI_20\SKN20-FINAL-2TEAM(vb1)\design\data\images(21,895개)"
OUTPUT_DIR = os.path.join(BASE_DIR, os.pardir, "ground_truth")
os.makedirs(OUTPUT_DIR, exist_ok=True)
OUTPUT_TASK1 = os.path.join(OUTPUT_DIR, "ground_truth_task1.csv")
OUTPUT_TASK2 = os.path.join(OUTPUT_DIR, "ground_truth_task2.csv")

# ── 쌍 개수 설정 ──
MAX_TASK1_QUERIES = 15  # Task 1 query 수
MAX_TASK2_QUERIES = 0  # Task 2 query 수

# 이미지 파일 목록을 set으로 로드 (빠른 존재 확인)
image_files = set(os.listdir(IMAGE_DIR))

# JSON 파일 파싱
app_drawings = defaultdict(list)  # appNum -> [{drawingNum, imageFile, exists}]
app_meta = {}  # appNum -> {applicantName, lastDispositionDate, LCCode}

for fname in sorted(os.listdir(JSON_DIR)):
    if not fname.endswith(".json"):
        continue
    fpath = os.path.join(JSON_DIR, fname)
    with open(fpath, encoding="utf-8") as f:
        data = json.load(f)

    app_num = data["applicationNumber"]
    drawing_num = data["image"]["number"]
    lc_code = data["meta"]["LCCode"]
    applicant = data["meta"]["applicantName"].strip()
    last_date = data["status"]["lastDispositionDate"]
    image_name = data["image"]["imageName"]

    # 이미지 파일명: {출원번호}-{LCCode}-{도면번호}_{인덱스}.jpg
    idx = os.path.splitext(image_name)[0]
    image_file = f"{app_num}-{lc_code}-{drawing_num}_{idx}.jpg"

    app_drawings[app_num].append({
        "drawingNum": drawing_num,
        "imageFile": image_file,
        "exists": image_file in image_files,
    })

    if app_num not in app_meta:
        app_meta[app_num] = {
            "applicantName": applicant,
            "lastDispositionDate": last_date,
            "LCCode": lc_code,
        }

# ── Task 1: 같은 출원번호 다른 도면 (query당 relevant 1개) ──
# 도면0=query, 도면1 또는 도면2 중 하나를 relevant로 선택
task1_candidates = []
for app_num, drawings in app_drawings.items():
    by_num = {d["drawingNum"]: d for d in drawings}
    query_d = by_num.get("0")
    if not query_d or not query_d["exists"]:
        continue
    # 도면1 우선, 없으면 도면2
    rel_d = by_num.get("1") or by_num.get("2")
    if rel_d and rel_d["exists"]:
        task1_candidates.append({
            "query_image": query_d["imageFile"],
            "relevant_image": rel_d["imageFile"],
            "similarity_type": "easy_positive",
            "note": "같은 출원번호 다른 도면",
        })

random.seed(18)
if len(task1_candidates) > MAX_TASK1_QUERIES:
    task1_rows = random.sample(task1_candidates, MAX_TASK1_QUERIES)
else:
    task1_rows = task1_candidates

# ── Task 2: 같은 출원인 & 같은 등록일자, 다른 출원번호 (query당 relevant 2개) ──
# 그룹 내 특허 3개 이상 → query 1개 + relevant 2개
# group_apps = defaultdict(list)
# for app_num, meta in app_meta.items():
#     by_num = {d["drawingNum"]: d for d in app_drawings[app_num]}
#     rep = by_num.get("0")
#     if rep and rep["exists"]:
#         key = (meta["applicantName"], meta["lastDispositionDate"])
#         group_apps[key].append({
#             "appNum": app_num,
#             "imageFile": rep["imageFile"],
#         })

# # 각 그룹에서 query 1개 + relevant 2개 조합 생성
# task2_candidates = []
# for (applicant, date), apps in group_apps.items():
#     if len(apps) < 3:  # 같은 출원인 특허가 3개 이상인 그룹만
#         continue
#     for i, query_app in enumerate(apps):
#         others = apps[:i] + apps[i+1:]
#         if len(others) < 2:
#             continue
#         # relevant 2개 선택
#         rel_pair = others[:2]
#         task2_candidates.append({
#             "query_image": query_app["imageFile"],
#             "relevant_images": [r["imageFile"] for r in rel_pair],
#             "applicant": applicant,
#             "date": date,
#         })

# random.seed(18)
# if len(task2_candidates) > MAX_TASK2_QUERIES:
#     task2_candidates = random.sample(task2_candidates, MAX_TASK2_QUERIES)

# task2_rows = []
# for item in task2_candidates:
#     for rel_img in item["relevant_images"]:
#         task2_rows.append({
#             "query_image": item["query_image"],
#             "relevant_image": rel_img,
#             "similarity_type": "hard_positive",
#             "note": f"같은 출원인({item['applicant']}) 같은 등록일({item['date']}) 다른 출원번호",
#         })

# ── CSV 저장 ──
fieldnames = ["query_image", "relevant_image", "similarity_type", "note"]

with open(OUTPUT_TASK1, "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(task1_rows)

# with open(OUTPUT_TASK2, "w", newline="", encoding="utf-8-sig") as f:
#     writer = csv.DictWriter(f, fieldnames=fieldnames)
#     writer.writeheader()
#     writer.writerows(task2_rows)

print(f"Task 1: {len(task1_rows)} queries (각 relevant 1개) → {OUTPUT_TASK1}")
# print(f"Task 2: {len(task2_candidates)} queries (각 relevant 2개, 총 {len(task2_rows)}행) → {OUTPUT_TASK2}")
