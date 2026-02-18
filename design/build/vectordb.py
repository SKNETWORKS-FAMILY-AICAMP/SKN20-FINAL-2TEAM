import os
import json
import chromadb
from chromadb import Client

# ChromaDB 클라이언트 초기화
# 저장 경로 지정(현재 디렉토리의 chroma_db 폴더)
chroma_client = chromadb.PersistentClient(path="..\\chroma_db")


#컬렉션이 이미 존재하면 불러오고, 없으면 새로 생성한다.
image_collection = chroma_client.get_or_create_collection(
    name="design", # **컬렉션 이름 지정**
    metadata={"hnsw:space": "cosine"} # 거리 계산 방식 : 코사인
) 
print("벡터 DB 컬렉션 이름: ", image_collection.name)

# === embeddings 폴더 내 json 전체 로드 ===
EMBEDDING_DIR = "design\\data\\embeddings"

print("벡터 DB에 저장 중")
for filename in os.listdir(EMBEDDING_DIR):

    if not filename.endswith("_embedding.json"):
        continue

    filepath = os.path.join(EMBEDDING_DIR, filename)

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    #컬렉션에 도면 벡터 추가
    #도면 1장 = 벡터 1개
    #메타데이터는 자유롭게 추가 가능! (지금은 디자인id, 출원번호, LCCode, 상품명, 도면번호, 상태, 이미지경로만 넣음.)
    image_collection.add(
        ids=[data.get("id")], # 고유 ID
        embeddings=[data.get("embedding")], # CLIP image encoder 결과
        metadatas=[{
            "design_id": data.get("metadata", {}).get("design_id"), #디자인id
            "applicationNumber": data.get("metadata", {}).get("applicationNumber"), #출원번호
            "LCCode": data.get("metadata", {}).get("LCCode", ""), #LCCode
            "articleName": data.get("metadata", {}).get("articleName", ""), # 상품명
            "imageNumber": data.get("metadata", {}).get("imageNumber", ""), #도면번호
            "admstStat": data.get("metadata", {}).get("status", {}).get("admstStat", ""), #상태
            "imagePath": data.get("metadata", {}).get("imagePath", ""), #이미지경로
            "designSummary": data.get("metadata", {}).get("designSummary", "") #디자인 요약
        }]
    )

print("✅ 모든 embedding json을 벡터 DB에 저장 완료")


'''
# 벡터DB에서 검색해보자
# 3019990031932-09-01_embedding 파일 로드
with open("./embeddings/3019990031932-09-01-5_embedding.json", 'r', encoding='utf-8') as f:
    data_1 = json.load(f)
    
query_embedding = data_1.get('embedding')

results = image_collection.query(
    query_embeddings=[query_embedding],
    n_results=5, # 상위 5개 검색
    where={"admstStat": "소멸"}   # 선택 필터
)

print("\n", "results(검색 결과) keys:", "\n")
print(results.keys())

print("\n", "="*20, "\n")
print("검색 결과:")
print("IDs:", results["ids"])
print("Distances:", results["distances"])
print("Metadatas:", results["metadatas"])

print("\n", "="*20, "\n")

for i in range(len(results["ids"][0])):
    print(
        results["ids"][0][i],
        results["distances"][0][i],
        results["metadatas"][0][i]["imagePath"]
    )
'''