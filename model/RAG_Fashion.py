'''
이미지 기반 RAG

플로우:
1. 사용자 질문 + 이미지 입력
2. 이미지 → ResNet 임베딩 생성
3. 벡터DB에서 유사한 이미지 검색
4. 검색 결과 + 질문 → LLM에 전달
5. LLM이 답변 생성
'''

import chromadb
import torch
import torchvision.transforms as transforms
from torchvision.models import resnet50
from PIL import Image
import numpy as np
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage


class ImageRAG:
    def __init__(self):
        """벡터DB 초기화 및 컬렉션 로드"""
        # Chroma 클라이언트 로드
        self.client = chromadb.PersistentClient(path="./chroma_db")
        
        try:
            self.collection = self.client.get_collection(name="fashion_images")
            print(f" 벡터DB 로드 완료! ({self.collection.count()}개 이미지)")
        except Exception as e:
            print(f" 벡터DB 로드 실패: {e}")
            exit()
        
        # ResNet 로드 (쿼리 이미지 임베딩용)
        self.model = resnet50(pretrained=True)
        self.model = torch.nn.Sequential(*list(self.model.children())[:-1]) # 마지막 분류층 제거
        self.model.eval()
        
        # 이미지 전처리 pipeline
        self.preprocess = transforms.Compose([
            transforms.Resize(256),
            transforms.CenterCrop(224),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406],
                                std=[0.229, 0.224, 0.225])
        ])
    
    
    def get_image_embedding(self, image_path):
        """
        입력 이미지를 임베딩 벡터로 변환 by ResNet
        
        Args:
            image_path (str): 입력 이미지 파일 경로
        
        Returns:
            list: 임베딩 벡터 (길이: 2048)
        """
        
        image = Image.open(image_path).convert('RGB')
        input_tensor = self.preprocess(image).unsqueeze(0)
        
        with torch.no_grad():
            embedding = self.model(input_tensor).flatten()
        
        return embedding.cpu().numpy().tolist()
    
    
    def search_similar_images(self, image_path, top_k=5):
        """
        입력 이미지와 유사한 이미지 검색 at VectorDB
        
        Args:
            image_path (str): 쿼리 이미지 경로
            top_k (int): 반환할 유사 이미지 개수
        
        Returns:
            dict: {
                'ids': [이미지 id들],
                'distances': [유사도 거리],
                'metadatas': [메타데이터들],
                'embeddings': [임베딩 벡터들]
            }
        """
        # 쿼리 이미지 임베딩 생성
        query_embedding = self.get_image_embedding(image_path)
        
        
        # Chroma에서 유사도 검색
        results = self.collection.query(
            embeddings=[query_embedding],
            n_results=top_k
        )
        
        return results
    
    
    def display_results(self, results):
        """검색 결과 출력
        
        Args:
            results (dict): search_similar_images의 반환값
        """
        if results is None:
            print("검색 결과 없음")
            return
        
        print(f"\n✓ 상위 {len(results['ids'][0])}개 유사 이미지:\n")
        
        for i, (id_, distance, metadata) in enumerate(
            zip(results['ids'][0], 
                results['distances'][0], 
                results['metadatas'][0])
        ):
            print(f"[{i+1}] ID: {id_}")
            print(f"    시대: {metadata['era']}")
            print(f"    스타일: {metadata['style']}")
            print(f"    성별: {metadata['gender']}")
            print(f"    URL: {metadata['url']}")
            print(f"    유사도 거리: {distance:.4f}")
            print()
    
    
    def answer_question(self, question, image_path, top_k=5):
        """
        질문 + 이미지 → 유사 이미지 검색 → LLM 답변
        
        Args:
            question: 사용자 질문
            image_path: 입력 이미지 경로
            top_k: 검색할 유사 이미지 개수
        
        Returns:
            str: LLM의 답변
        """
        # 1. 벡터DB에서 유사 이미지 검색
        results = self.search_similar_images(image_path, top_k=top_k)
        
        # 2. 검색 결과를 텍스트로 정리
        search_results_text = self._format_search_results(results)
        
        # 3. LLM에 질문 + 검색 결과 전달
        response = self._generate_answer(question, search_results_text)
        
        return response, results
    
    
    def _format_search_results(self, results):
        """검색 결과를 LLM이 이해할 수 있는 텍스트로 변환
        
        Args:
            results (dict): 검색 결과
        
        Returns:
            str: 포맷된 텍스트
        """
        text = "검색된 유사한 이미지들:\n"
        
        for i, (id_, metadata) in enumerate(
            zip(results['ids'][0], results['metadatas'][0])
        ):
            text += f"\n[{i+1}] 이미지 ID: {id_}\n"
            text += f"   - 시대: {metadata['era']}\n"
            text += f"   - 스타일: {metadata['style']}\n"
            text += f"   - 성별: {metadata['gender']}\n"
        
        return text
    
    
    def _generate_answer(self, question, search_results_text):
        """LLM으로 답변 생성
        
        Args:
            question (str): 사용자 질문
            search_results_text (str): 검색 결과 텍스트
        
        Returns:
            str: LLM 답변
        """
        from langchain_openai import ChatOpenAI
        
        llm = ChatOpenAI(model="gpt-4", temperature=0.2)
        
        system_prompt = """사용자의 질문과 유사한 이미지를 검색한 후, 
                         유용한 패션 조언을 제공해주세요."""
        
        user_prompt = f"""질문: {question}

                        검색된 참고 이미지 정보:
                        {search_results_text}

                        위 정보를 바탕으로 질문에 답변해주세요."""
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]
        
        response = llm(messages)
        return response.content


# ===== 사용 예시 =====
if __name__ == "__main__":
    # RAG 초기화
    rag = ImageRAG()
    
    # 입력: 질문 + 이미지
    question = "이 옷과 비슷한 스타일을 추천해줘."
    test_image = r'C:\Users\playdata2\Desktop\SKN_AI_20\SKN20-FINAL-2TEAM\model\data\Sample\01.원천데이터\1.training\woman\2019\T_00297_19_normcore_W.jpg'
    
    # LLM 답변 생성
    answer, results = rag.answer_question(question, test_image, top_k=5)
    
    # 결과 출력
    print("=" * 60)
    print(f"질문: {question}\n")
    print("검색된 유사 이미지:")
    for i, (id_, metadata) in enumerate(zip(results['ids'][0], results['metadatas'][0])):
        print(f"  [{i+1}] {metadata['era']} - {metadata['style']} ({metadata['gender']})")
    print("\n" + "=" * 60)
    print("LLM 답변:")
    print("=" * 60)
    print(answer)
