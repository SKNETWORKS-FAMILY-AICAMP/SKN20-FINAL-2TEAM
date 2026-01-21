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

# 2. Chroma 컬렉션 생성
client = chromadb.Client()

collection = client.create_collection(
    name="fashion_images" #이 컬렉션이 VectorDB 테이블 역할
)

# 3. embedding + metadata + id 저장
embeddings = [item["embedding"] for item in img_data_list]
metadatas  = [item["metadata"] for item in img_data_list]
ids        = [item["metadata"]["id"] for item in img_data_list]

collection.add(
    embeddings=embeddings, #이미지 임베딩 벡터
    metadatas=metadatas, #이미지 메타데이터
    ids=ids #각 이미지 id (필수)
)

print(f"총 {len(img_data_list)}개가 VectorDB에 저장되었습니다.")



