# Design RAG 시스템 📐

> 특허청 디자인 데이터를 기반으로 유사 디자인을 검색하고 분석하는 RAG(Retrieval-Augmented Generation) 시스템

## 📁 폴더 구조

```
SKN20-FINAL-2TEAM/
├── design/                          # 🎨 디자인 RAG 시스템 (이 폴더)
│   │
│   ├── src/                        # 🧠 소스코드
│   │   ├── api.py                  # API 서빙
│   │   ├── design_chatbot.py       # 챗봇 실행 모듈
│   │   ├── design_chatbot.ipynb    # 챗봇 실행 모듈 (Jupyter 노트북 버전- 참고용)
│   │   ├── prompts.py              # 프롬프트 
│   │   └── utils.py                # 유틸리티 함수들 
│   │
│   ├── build/                      # 🔧 데이터 & 벡터DB 구축 (최초 1회 실행)
│   │   ├── api_design.py           # API 데이터 수집
│   │   ├── xml_to_json.py          # XML → JSON 변환
│   │   ├── embeddings.py           # 이미지 다운 & 임베딩 벡터 생성
│   │   └── vectordb.py             # 벡터DB 구축
│   │
│   ├── data/                       # 📊 데이터 저장소 (.gitignore 추가)
│   │   ├── xml/                    # 특허청 API 응답 
│   │   ├── json/                   # 필요한 필드만 추출한 JSON
│   │   ├── images/                 # 도면 이미지
│   │   ├── embeddings/             # 벡터DB 구축용 임베딩 파일
│   │   └── 출원번호/               # 출원번호 목록 Excel
│   │
│   └── chroma_db/                  # 🗄️ ChromaDB 벡터 데이터베이스 (.gitignore 추가)
│     
│
├── requirements.txt               
└── README.md                       

```

### 🚫 `.gitignore` 설정

```gitignore
design/data/
design/chroma_db/
.env
```



## 🚀 실행 순서

### 💡 최초 설정 (1회만 실행)
데이터를 처음부터 구축하는 경우 아래 순서대로 실행:

### Step 1: API에서 데이터 수집
```bash
cd design/build
python api_design.py
# 결과: design/data/xml/ 폴더에 XML 파일 생성
```

### Step 2: XML을 JSON으로 변환
```bash
python xml_to_json.py
# 결과: design/data/json/ 폴더에 JSON 파일 생성
```

### Step 3: 이미지 임베딩 생성
```bash
python embeddings.py
# 결과: 
#    - design/data/embeddings/ 폴더에 임베딩 JSON 생성
#    - design/data/images/ 폴더에 이미지 저장
```

### Step 4: 벡터 DB 구축
```bash
python vectordb.py
# 결과: design/chroma_db/ 폴더에 벡터DB 생성
```

---

### 🎯 일반 사용 (매번 실행)
데이터 구축이 완료된 후:

### 챗봇 실행
```bash
cd design/src

# Jupyter 노트북으로 실행
jupyter notebook design_chatbot.ipynb

# 또는 Python 스크립트로 실행
python design_chatbot.py
```

---

## ⚙️ 환경 설정

### 필수 환경변수 (`.env` 파일)
```
OPENAI_API_KEY=sk-...
KIPRISPLUS_API_KEY=...
TAVILY_API_KEY=tvly-...
```

### 필수 패키지

**Python 3.9+ 필요**

```bash
# === LangChain 프레임워크 ===
langchain==1.2.1
langchain-chroma==1.1.0
langchain-classic==1.0.1
langchain-community==0.4.1
langchain-core==1.2.6
langchain-huggingface==1.2.0
langchain-openai==1.1.6
langchain-text-splitters==1.1.0
langgraph==1.0.5
langgraph-checkpoint==3.0.1
langgraph-prebuilt==1.0.5
langgraph-sdk==0.3.1

# === 모델 ===
openai>=1.0.0
torch>=2.1.0
git+https://github.com/openai/CLIP.git  # CLIP 모델
transformers>=4.30.0
numpy>=1.24.0

# === 데이터베이스 & 검색 ===
chromadb>=0.4.0
tavily-python>=0.3.0

# === 웹 & API ===
fastapi>=0.104.0
uvicorn>=0.24.0

# === 파일 처리 ===
Pillow>=10.0.0
openpyxl>=3.1.0
requests>=2.31.0

# === 기타 ===
python-dotenv>=1.0.0
pathlib
```

### 설치
```bash
# 프로젝트 루트 디렉토리에서 실행
pip install -r requirements.txt
```

