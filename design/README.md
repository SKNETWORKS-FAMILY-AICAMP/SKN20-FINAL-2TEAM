# Design RAG 시스템 📐

> 특허청 디자인 데이터를 기반으로 유사 디자인을 검색하고 분석하는 RAG(Retrieval-Augmented Generation) 시스템

## 📁 폴더 구조

```
SKN20-FINAL-2TEAM/
├── design/                          # 🎨 디자인 RAG 시스템 (이 폴더)
│   ├── api_design.py               # API 데이터 수집
│   ├── xml_to_json.py              # XML → JSON 변환
│   ├── embeddings.py               # 이미지 임베딩 생성
│   ├── vectordb.py                 # 벡터 DB 구축
│   ├── rag.py                      # 기본 RAG 체인
│   ├── rag_advanced.py             # 고급 RAG 체인 (VLM 분석 포함)
│   ├── app.py                      # Streamlit 채팅 인터페이스
│   └── README.md                   
│
├── data/                           # 📊 데이터 저장소 (.gitignore 추가)
│   ├── xml/                        # 특허청 API 응답 
│   ├── json/                       # 필요한 필드만 추출한 JSON
│   ├── images/                     # 도면 이미지
│   ├── embeddings/                 # 벡터 DB 구축용
│   ├── 출원번호/                   # 출원번호 목록 Excel
│   └── rag_테스트데이터셋/         # 테스트용 데이터셋
│
├── chroma_db/                      # 🗄️ ChromaDB 벡터 데이터베이스 (.gitignore 추가)
│   └── [벡터 DB 파일들]
│
└── [기타 폴더들...]
```

### 🚫 `.gitignore` 설정

```gitignore
data/
chroma_db/
.env
```



## 🚀 실행 순서

데이터를 처음부터 구축하는 경우 아래 순서대로 실행:

### Step 1: API에서 데이터 수집
```bash
python api_design.py
# 결과: data/xml/2025_2026/ 폴더에 XML 파일 생성
```

### Step 2: XML을 JSON으로 변환
```bash
python xml_to_json.py
# 결과: 
#   - data/json/2025_2026/ 폴더에 JSON 파일 생성
```

### Step 3: 이미지 임베딩 생성
```bash
python embeddings.py
# 결과: 
#    - data/embeddings/ 폴더에 임베딩 JSON 생성
#    - data/images/ 폴더에 이미지 저장
```

### Step 4: 벡터 DB 구축
```bash
python vectordb.py
# 결과: chroma_db/ 폴더에 벡터 DB 생성
```

### Step 5: Streamlit 앱 실행
```bash
streamlit run app.py
# → 브라우저에서 http://localhost:8501 접속
```

---

## ⚙️ 환경 설정

### 필수 환경변수 (`.env` 파일)
```
OPENAI_API_KEY=sk-...
KIPRISPLUS_API_KEY=...
```

### 필수 패키지
```
chromadb
langchain-openai
langchain-core
pillow
torch
clip
openpyxl
requests
streamlit
python-dotenv
```

### 설치
```bash
pip install -r requirements.txt
```

