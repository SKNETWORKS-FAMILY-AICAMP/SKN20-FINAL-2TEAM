import chromadb
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from PIL import Image
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser
import torch
import clip
from dotenv import load_dotenv
load_dotenv()
'''
RAG (Retrieval-Augmented Generation) 체인 구현

- 이미지 임베딩: CLIP 모델 사용
- 벡터 DB: ChromaDB
- LLM: GPT-4o

함수 목록
get_image_embedding: 이미지 입력 -> CLIP 임베딩 반환
search_similar_designs: 벡터DB에서 유사 도면 검색
design_search_chain: 사진 + 텍스트 입력 -> 유사 도면 검색 -> LLM

'''

#벡터DB 로드
# ChromaDB 클라이언트 초기화
chroma_client = chromadb.PersistentClient(path="./chroma_db")

#생성할때와 동일한 이름으로 컬렉션 불러오기
image_collection = chroma_client.get_collection(
    name="design_img"
)

collections = chroma_client.list_collections()
print(f"벡터DB collections: {collections}")


# CLIP 모델 로드 (ViT-B/32)
print("CLIP 모델 로딩 중...")
device = "cuda" if torch.cuda.is_available() else "cpu"
model, preprocess = clip.load("ViT-B/32", device=device)
print(f"모델 로드 완료 (Device: {device})")


# ===== 이미지 임베딩 함수 =====
def get_image_embedding(image_input):
    """입력한 사진을  CLIP으로 임베딩
    
    Args: 
        image_input (str or bytes): 이미지 파일 경로 또는 바이너리 데이터

    Returns:
        embedding: 이미지 임베딩 벡터(512d)

    """
    try:
        query_image = Image.open(image_input)
        # CLIP으로 임베딩
        inputs = preprocess(query_image).unsqueeze(0).to(device)
        with torch.no_grad():
            image_embedding = model.encode_image(inputs)
            embedding = image_embedding.cpu().numpy()
            query_embedding = embedding[0].tolist()

        return query_embedding
    
    except Exception as e:
        print(f"❌ 이미지 임베딩 실패: {e}")
        return None

# ===== 벡터DB 검색 함수 =====
def search_similar_designs(query_embedding, n_results=30):
    """벡터DB에서 유사한 도면 검색.
    
    Args:
        query_embedding (list): 이미지 임베딩 벡터
        n_results (int): 검색할 유사 도면 개수
    
    Returns:
        str: 유사 도면 정보를 포맷팅한 문자열
    """
    results = image_collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results
    )
    
    # 메타데이터를 포맷팅 -> llm에 전달할 컨텍스트 생성
    context_text = ""
    for i in range(len(results["ids"][0])):
        design_id = results["ids"][0][i]
        distance = results["distances"][0][i]
        metadata = results["metadatas"][0][i]
        
        
        context_text += f"""
            디자인 {i+1}:
            - ID: {design_id}
            - 유사도 거리: {distance:.4f}
            - 출원번호: {metadata.get('applicationNumber', 'N/A')}
            - 상품명: {metadata.get('articleName', 'N/A')}
            - 도면번호: {metadata.get('imageNumber', 'N/A')}
            - 상태: {metadata.get('admstStat', 'N/A')}
            - 이미지 경로: {metadata.get('imagePath', 'N/A')}
    """
    
    return context_text

# ===== LLM 체인 =====
llm = ChatOpenAI(model="gpt-4o", temperature=0.)
output_parser = StrOutputParser()

# === 프롬포트 ===
prompt_template =ChatPromptTemplate.from_messages([
    (
        "system",
        """
당신은 사용자가 보낸 디자인 사진을 보고, 현재 등록된 디자인 중 비슷한 디자인 후보군을
추천해주는 역할입니다. 
다음 문맥을 참고해 질문에 답변하세요.
답변에는 id, 유사도 거리, 상품명, 도면번호, 상태, 이미지 경로를 포함하여 답변하세요. 

"""
    ),
    (
        "user",
        """
다음 정보를 참고해 질문에 답변하세요.
정보(context): {context}

사용자 질문: {question}


"""
    )
])

# 전체 체인
def design_search_chain(image_input, user_question):
    """사진 + 텍스트 입력 -> 유사 도면 검색 -> LLM 답변
    
    """
    
    # 1️⃣ 사진 임베딩
    print("1️⃣ 사진 임베딩 중...")
    query_embedding = get_image_embedding(image_input)
    if query_embedding is None:
        return "❌ 이미지 처리에 실패했습니다."
    
    # 2️⃣ 벡터DB에서 상위 30개 검색
    print("2️⃣ 벡터DB에서 유사 도면 검색 중...")
    context = search_similar_designs(query_embedding, n_results=30)
    
    # 3️⃣ LLM 답변 생성
    print("3️⃣ LLM 답변 생성 중...")
    chain = prompt_template | llm | output_parser
    
    answer = chain.invoke({
        "context": context,
        "question": user_question
    })
    
    return answer

'''
# 테스트
image_path = r"C:\Users\playdata2\Desktop\디자인\VectorDB\downloaded_images\3019870006829-09-01_001.JPG"
question = "이 도면과 유사한 디자인을 찾아줘."
result = design_search_chain(image_path, question)
print(result)
'''