import chromadb
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from PIL import Image
import torch
import clip
from dotenv import load_dotenv
import streamlit as st
import requests
from io import BytesIO

load_dotenv()

# 페이지 설정
st.set_page_config(page_title="🎨 디자인 챗봇", layout="wide")
st.title("🎨 디자인 유사도 검색 챗봇")

# ===== 벡터DB 로드 =====
@st.cache_resource
def load_models():
    """모델 로드 (한 번만 실행)"""
    chroma_client = chromadb.PersistentClient(path="./chroma_db")
    image_collection = chroma_client.get_collection(name="design_img")
    
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, preprocess = clip.load("ViT-B/32", device=device)
    
    return image_collection, model, preprocess, device

image_collection, model, preprocess, device = load_models()

# LLM 초기화
llm = ChatOpenAI(model="gpt-4o", temperature=0.)
output_parser = StrOutputParser()

# 프롬프트 템플릿
prompt_template = ChatPromptTemplate.from_messages([
    (
        "system",
        """
당신은 사용자가 보낸 디자인 사진을 보고, 현재 등록된 디자인 중 비슷한 디자인 후보군을
추천해주는 친절한 챗봇입니다. 
다음 문맥을 참고해 질문에 답변하세요.
답변에는 id, 출원번호, 유사도 거리, 상품명, 상태를 포함하여 친근하고 자연스럽게 답변하세요.
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

# ===== 이미지 임베딩 함수 =====
def get_image_embedding(image_input):
    """입력한 사진을 CLIP으로 임베딩"""
    try:
        query_image = Image.open(image_input)
        inputs = preprocess(query_image).unsqueeze(0).to(device)
        with torch.no_grad():
            image_embedding = model.encode_image(inputs)
            embedding = image_embedding.cpu().numpy()
            query_embedding = embedding[0].tolist()
        return query_embedding
    except Exception as e:
        return None

# ===== 벡터DB 검색 함수 =====
def search_similar_designs(query_embedding, n_results=30):
    """벡터DB에서 유사한 도면 검색"""
    results = image_collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results
    )
    
    context_text = ""
    results_list = []
    
    for i in range(len(results["ids"][0])):
        design_id = results["ids"][0][i]
        distance = results["distances"][0][i]
        metadata = results["metadatas"][0][i]
        
        design_info = {
            'index': i + 1,
            'id': design_id,
            'distance': distance,
            'applicationNumber': metadata.get('applicationNumber', 'N/A'),
            'articleName': metadata.get('articleName', 'N/A'),
            'imageNumber': metadata.get('imageNumber', 'N/A'),
            'admstStat': metadata.get('admstStat', 'N/A'),
            'imagePath': metadata.get('imagePath', 'N/A')
        }
        results_list.append(design_info)
        
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
    
    return context_text, results_list

# ===== 이미지 표시 함수 =====
def display_image_from_url(image_url):
    """URL에서 이미지를 다운로드하여 표시"""
    try:
        response = requests.get(image_url, timeout=10)
        if response.status_code == 200:
            img = Image.open(BytesIO(response.content))
            return img
    except Exception:
        pass
    return None

# ===== 전체 체인 =====
def design_search_chain(image_input, user_question):
    """사진 + 텍스트 입력 -> 유사 도면 검색 -> LLM 답변"""
    
    query_embedding = get_image_embedding(image_input)
    if query_embedding is None:
        return "죄송하지만 이미지 처리에 실패했습니다. 다시 시도해주세요.", []
    
    context, results_list = search_similar_designs(query_embedding, n_results=30)
    
    chain = prompt_template | llm | output_parser
    answer = chain.invoke({
        "context": context,
        "question": user_question
    })
    
    return answer, results_list

# ===== 세션 상태 초기화 =====
if "messages" not in st.session_state:
    st.session_state.messages = []
if "current_image" not in st.session_state:
    st.session_state.current_image = None
if "current_results" not in st.session_state:
    st.session_state.current_results = []

# ===== 사이드바에 이미지 업로드 =====
with st.sidebar:
    st.subheader("📤 이미지 업로드")
    uploaded_file = st.file_uploader("이미지를 선택하세요 (JPG, PNG)", type=["jpg", "jpeg", "png"])
    
    if uploaded_file:
        st.session_state.current_image = uploaded_file
        st.image(uploaded_file, caption="현재 이미지", use_column_width=True)
        
        if st.button("🗑️ 이미지 초기화", use_container_width=True):
            st.session_state.current_image = None
            st.session_state.messages = []
            st.rerun()

# ===== 메인 채팅 영역 =====
# 대화 히스토리 표시
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        
        # 검색 결과가 있으면 테이블 표시
        if message.get("results"):
            st.markdown("#### 📊 검색 결과")
            
            # 테이블 헤더
            header_cols = st.columns([0.6, 1.2, 1.5, 1.5, 1, 0.8])
            with header_cols[0]:
                st.markdown("**순위**")
            with header_cols[1]:
                st.markdown("**출원번호**")
            with header_cols[2]:
                st.markdown("**도면사진**")
            with header_cols[3]:
                st.markdown("**상품명**")
            with header_cols[4]:
                st.markdown("**상태**")
            with header_cols[5]:
                st.markdown("**유사도**")
            
            st.divider()
            
            # 테이블 행
            for design in message["results"][:10]:
                row_cols = st.columns([0.6, 1.2, 1.5, 1.5, 1, 0.8])
                
                with row_cols[0]:
                    st.markdown(f"**{design['index']}**")
                
                with row_cols[1]:
                    st.markdown(design['applicationNumber'])
                
                with row_cols[2]:
                    if design['imagePath'] != 'N/A':
                        img = display_image_from_url(design['imagePath'])
                        if img:
                            st.image(img, width=80)
                    else:
                        st.caption("이미지 없음")
                
                with row_cols[3]:
                    st.markdown(design['articleName'])
                
                with row_cols[4]:
                    st.markdown(design['admstStat'])
                
                with row_cols[5]:
                    st.markdown(f"**{design['distance']:.4f}**")

# ===== 채팅 입력 =====
if st.session_state.current_image is None:
    st.info("👈 왼쪽 사이드바에서 이미지를 업로드해주세요!")
else:
    if user_input := st.chat_input("디자인에 대해 물어보세요..."):
        # 사용자 메시지 저장
        st.session_state.messages.append({
            "role": "user",
            "content": user_input
        })
        
        # 사용자 메시지 표시
        with st.chat_message("user"):
            st.markdown(user_input)
        
        # 챗봇 응답 생성
        with st.chat_message("assistant"):
            with st.spinner("🔄 검색 중..."):
                answer, results_list = design_search_chain(
                    st.session_state.current_image,
                    user_input
                )
            
            st.markdown(answer)
            
            # 검색 결과 테이블 표시
            if results_list:
                st.markdown("#### 📊 검색 결과")
                
                # 테이블 헤더
                header_cols = st.columns([0.6, 1.2, 1.5, 1.5, 1, 0.8])
                with header_cols[0]:
                    st.markdown("**순위**")
                with header_cols[1]:
                    st.markdown("**출원번호**")
                with header_cols[2]:
                    st.markdown("**도면사진**")
                with header_cols[3]:
                    st.markdown("**상품명**")
                with header_cols[4]:
                    st.markdown("**상태**")
                with header_cols[5]:
                    st.markdown("**유사도**")
                
                st.divider()
                
                # 테이블 행
                for design in results_list[:10]:  # 상위 10개만 표시
                    row_cols = st.columns([0.6, 1.2, 1.5, 1.5, 1, 0.8])
                    
                    with row_cols[0]:
                        st.markdown(f"**{design['index']}**")
                    
                    with row_cols[1]:
                        st.markdown(design['applicationNumber'])
                    
                    with row_cols[2]:
                        if design['imagePath'] != 'N/A':
                            img = display_image_from_url(design['imagePath'])
                            if img:
                                st.image(img, width=80)
                        else:
                            st.caption("이미지 없음")
                    
                    with row_cols[3]:
                        st.markdown(design['articleName'])
                    
                    with row_cols[4]:
                        st.markdown(design['admstStat'])
                    
                    with row_cols[5]:
                        st.markdown(f"**{design['distance']:.4f}**")
            
            # 챗봇 메시지 저장
            st.session_state.messages.append({
                "role": "assistant",
                "content": answer,
                "results": results_list
            })
