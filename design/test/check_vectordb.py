import chromadb
from chromadb import Client

def check_collections():
    """벡터 DB의 모든 컬렉션 이름을 확인하는 함수"""
    try:
        # ChromaDB 클라이언트 초기화 (기존 DB 경로와 동일하게 설정)
        chroma_client = chromadb.PersistentClient(path=r"C:\Users\playdata2\Desktop\SKN_AI_20\SKN20-FINAL-2TEAM\design\chroma_db")
        
        # 모든 컬렉션 목록 가져오기
        collections = chroma_client.list_collections()
        
        print("=" * 50)
        print("📁 현재 벡터 DB 컬렉션 목록")
        print("=" * 50)
        
        if not collections:
            print("⚠️  생성된 컬렉션이 없습니다.")
            return
        
        for i, collection in enumerate(collections, 1):
            print(f"{i}. 컬렉션 이름: {collection.name}")
            
            # 컬렉션의 기본 정보 출력
            try:
                count = collection.count()
                print(f"   📊 데이터 개수: {count}")
                
                # 메타데이터 정보 출력
                metadata = collection.metadata
                if metadata:
                    print(f"   📝 메타데이터: {metadata}")
                else:
                    print("   📝 메타데이터: 없음")
                    
            except Exception as e:
                print(f"   ❌ 컬렉션 정보 조회 실패: {e}")
            
            print("-" * 30)
            
    except Exception as e:
        print(f"❌ 벡터 DB 연결 실패: {e}")
        return

def get_collection_details(collection_name):
    """특정 컬렉션의 상세 정보를 확인하는 함수"""
    try:
        chroma_client = chromadb.PersistentClient(path=r"C:\Users\playdata2\Desktop\SKN_AI_20\SKN20-FINAL-2TEAM\design\chroma_db")
        
        # 특정 컬렉션 가져오기
        collection = chroma_client.get_collection(name=collection_name)
        
        print("=" * 50)
        print(f"🔍 '{collection_name}' 컬렉션 상세 정보")
        print("=" * 50)
        
        # 기본 정보
        print(f"컬렉션 이름: {collection.name}")
        print(f"데이터 개수: {collection.count()}")
        print(f"메타데이터: {collection.metadata}")
        
        # 일부 데이터 샘플 출력 (처음 3개)
        if collection.count() > 0:
            results = collection.get(limit=3, include=['metadatas', 'documents'])
            
            print("\n📋 데이터 샘플 (처음 3개):")
            for i, (id, metadata) in enumerate(zip(results['ids'], results['metadatas']), 1):
                print(f"\n{i}. ID: {id}")
                if metadata:
                    for key, value in metadata.items():
                        print(f"   {key}: {value}")
                        
    except Exception as e:
        print(f"❌ 컬렉션 '{collection_name}' 조회 실패: {e}")

if __name__ == "__main__":
    # 모든 컬렉션 목록 확인
    check_collections()
    
    #특정 컬렉션 상세 정보 확인 (design 컬렉션)
    print("\n" + "=" * 80 + "\n")
    get_collection_details("design")