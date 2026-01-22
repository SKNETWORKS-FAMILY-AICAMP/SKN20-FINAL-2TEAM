'''
img_data_list.json 파일을 vector DB에 저장

1. JSON 로드
2. Chroma 컬렉션 생성
3. embedding + metadata + id 저장

'''
import chromadb
import json


# 1. JSON 로드
with open("img_data_list.json", "r") as f:
    img_data_list = json.load(f)

# 2. Chroma Persistent 클라이언트 생성 (디스크에 저장)
client = chromadb.PersistentClient(path="./chroma_db")

collection = client.create_collection(
    name="fashion_images", #컬렉션 이름 지정
)

# 3. embedding + metadata + id 저장
embeddings = [item["embedding"] for item in img_data_list]
metadatas  = [item["metadata"] for item in img_data_list]
ids        = [item["metadata"]["id"] for item in img_data_list]

collection.add(
    embeddings=embeddings, #이미지 임베딩 벡터
    metadatas=metadatas, #이미지 메타데이터
    ids=ids #각 이미지 id
)

print(f"총 {len(img_data_list)}개가 VectorDB에 저장되었습니다.")


# 저장된 컬렉션 확인
print(client.list_collections())

# 저장 경로 확인
# print("VectorDB 저장 경로:", client.get_persist_directory())

# 내부 문서 1개 확인
print("컬렉션 내 문서 1개 예시:")
print(collection.get(ids=[ids[0]], include=['embeddings', 'metadatas']))
