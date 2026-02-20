"""
Ground Truth 기반 벡터DB 검색 성능 평가
- Precision@1: Top-1 결과가 relevant인 비율
- Recall@5: Top-5 안에 relevant_image가 포함된 비율
"""
import csv
import os
from collections import defaultdict
import chromadb

# ── 경로 설정 ──
GT_CSV = r"C:\Users\playdata2\Desktop\SKN_AI_20\SKN20-FINAL-2TEAM(default)\design\ground_truth\ground_truth_filtered.csv"
CHROMA_DB = r"C:\Users\playdata2\Desktop\SKN_AI_20\SKN20-FINAL-2TEAM(default)\design\chroma_db"
IMAGE_DIR = r"C:\Users\playdata2\Desktop\SKN_AI_20\SKN20-FINAL-2TEAM(default)\design\data\images"


def image_filename_to_db_id(filename):
    """이미지 파일명 -> ChromaDB ID 변환
    예: '3020250000208-09-01-0_000.jpg' -> '3020250000208-09-01-IMG-0'
    """
    stem = os.path.splitext(filename)[0]       # '3020250000208-09-01-0_000'
    prefix = stem.split("_")[0]                 # '3020250000208-09-01-0'
    design_id, img_num = prefix.rsplit("-", 1)  # '3020250000208-09-01', '0'
    return f"{design_id}-IMG-{img_num}"


def db_id_to_image_filename(db_id, collection):
    """ChromaDB ID -> 이미지 파일명 (imagePath 메타데이터 기반 매핑은 복잡하므로 역변환)
    예: '3020250000208-09-01-IMG-0' -> prefix '3020250000208-09-01-0'
    이미지 폴더에서 해당 prefix로 시작하는 파일을 찾음
    """
    # '3020250000208-09-01-IMG-0' -> design_id='3020250000208-09-01', img_num='0'
    parts = db_id.split("-IMG-")
    if len(parts) != 2:
        return None
    design_id, img_num = parts
    prefix = f"{design_id}-{img_num}_"
    # IMAGE_DIR에서 매칭 파일 찾기
    for fname in os.listdir(IMAGE_DIR):
        if fname.startswith(prefix):
            return fname
    return None


def main():
    # ── 1. Ground Truth 로드 ──
    with open(GT_CSV, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        gt_rows = list(reader)

    # query_image별 relevant_image 그룹핑
    query_relevants = defaultdict(set)
    query_types = {}
    for row in gt_rows:
        q = row["query_image"]
        r = row["relevant_image"]
        query_relevants[q].add(r)
        query_types[q] = row["similarity_type"]

    print(f"Ground Truth 로드: {len(gt_rows)}쌍, 고유 query: {len(query_relevants)}개\n")

    # ── 2. ChromaDB 연결 ──
    client = chromadb.PersistentClient(path=CHROMA_DB)
    collection = client.get_collection(name="design")
    print(f"ChromaDB 컬렉션 '{collection.name}' 로드: {collection.count()}개 벡터\n")

    # ── 3. 이미지 파일명 -> DB ID 매핑 (역방향도 준비) ──
    # DB의 모든 ID를 가져와서 역매핑 구축
    all_ids = collection.get(include=[])["ids"]
    dbid_to_filename = {}
    for db_id in all_ids:
        fname = db_id_to_image_filename(db_id, collection)
        if fname:
            dbid_to_filename[db_id] = fname

    print(f"DB ID -> 파일명 매핑: {len(dbid_to_filename)}개\n")

    # ── 4. 쿼리별 검색 & 평가 ──
    K = 5
    results_table = []
    precision1_hits = 0
    recall5_sum = 0.0
    total_queries = 0
    skipped = 0

    for query_img, relevant_set in query_relevants.items():
        query_db_id = image_filename_to_db_id(query_img)

        # 쿼리 임베딩 가져오기
        try:
            query_data = collection.get(ids=[query_db_id], include=["embeddings"])
        except Exception:
            skipped += 1
            continue

        if not query_data["embeddings"]:
            skipped += 1
            continue

        query_embedding = query_data["embeddings"][0]

        # Top-(K+1) 검색 (자기 자신 포함될 수 있으므로)
        search_results = collection.query(
            query_embeddings=[query_embedding],
            n_results=K + 1,
        )

        # 자기 자신 제외
        retrieved_ids = [
            rid for rid in search_results["ids"][0] if rid != query_db_id
        ][:K]
        retrieved_distances = []
        for i, rid in enumerate(search_results["ids"][0]):
            if rid != query_db_id and len(retrieved_distances) < K:
                retrieved_distances.append(search_results["distances"][0][i])

        # DB ID -> 파일명 변환
        retrieved_filenames = [dbid_to_filename.get(rid, rid) for rid in retrieved_ids]

        # Precision@1: Top-1이 relevant인지
        p1_hit = 1 if retrieved_filenames and retrieved_filenames[0] in relevant_set else 0
        precision1_hits += p1_hit

        # Recall@5: relevant 중 Top-5에 포함된 비율
        hits_in_top5 = sum(1 for fname in retrieved_filenames if fname in relevant_set)
        recall5 = hits_in_top5 / len(relevant_set)
        recall5_sum += recall5

        total_queries += 1

        results_table.append({
            "query": query_img,
            "type": query_types[query_img],
            "n_relevant": len(relevant_set),
            "p@1": p1_hit,
            "hits@5": hits_in_top5,
            "r@5": recall5,
            "top5": retrieved_filenames,
            "top5_dist": retrieved_distances,
        })

    # ── 5. 결과 출력 ──
    print("=" * 120)
    print(f"{'idx':<4} {'query_image':<45} {'type':<15} {'rel':>3} {'P@1':>4} {'hits':>4} {'R@5':>6}")
    print("-" * 120)

    # type별 집계
    type_stats = defaultdict(lambda: {"total": 0, "p1": 0, "r5": 0.0})

    for i, r in enumerate(results_table):
        print(
            f"{i:<4} {r['query']:<45} {r['type']:<15} {r['n_relevant']:>3} "
            f"{r['p@1']:>4} {r['hits@5']:>4} {r['r@5']:>6.2f}"
        )
        ts = type_stats[r["type"]]
        ts["total"] += 1
        ts["p1"] += r["p@1"]
        ts["r5"] += r["r@5"]

    print("=" * 120)

    # 전체 요약
    if total_queries > 0:
        avg_p1 = precision1_hits / total_queries
        avg_r5 = recall5_sum / total_queries
    else:
        avg_p1 = avg_r5 = 0.0

    print(f"\n{'구분':<20} {'쿼리수':>6} {'Precision@1':>12} {'Recall@5':>12}")
    print("-" * 55)
    for typ, s in type_stats.items():
        tp1 = s["p1"] / s["total"] if s["total"] else 0
        tr5 = s["r5"] / s["total"] if s["total"] else 0
        print(f"{typ:<20} {s['total']:>6} {tp1:>12.4f} {tr5:>12.4f}")
    print("-" * 55)
    print(f"{'전체':<20} {total_queries:>6} {avg_p1:>12.4f} {avg_r5:>12.4f}")

    if skipped:
        print(f"\n(DB에서 찾지 못해 건너뛴 쿼리: {skipped}개)")

    # ── 6. 상세 결과 CSV 저장 ──
    detail_csv = os.path.join(os.path.dirname(GT_CSV), "evaluation_results.csv")
    with open(detail_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["query_image", "type", "n_relevant", "P@1", "hits@5", "R@5",
                         "top1", "top1_dist", "top2", "top2_dist", "top3", "top3_dist",
                         "top4", "top4_dist", "top5", "top5_dist"])
        for r in results_table:
            row = [r["query"], r["type"], r["n_relevant"], r["p@1"], r["hits@5"], f"{r['r@5']:.4f}"]
            for j in range(5):
                if j < len(r["top5"]):
                    row.append(r["top5"][j])
                    row.append(f"{r['top5_dist'][j]:.6f}" if j < len(r["top5_dist"]) else "")
                else:
                    row.extend(["", ""])
            writer.writerow(row)

    print(f"\n상세 결과 CSV 저장: {os.path.abspath(detail_csv)}")


if __name__ == "__main__":
    main()
