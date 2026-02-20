# Design RAG 시스템 📐

> 특허청 디자인 데이터를 기반으로 유사 디자인을 검색하고 분석하는 RAG(Retrieval-Augmented Generation) 시스템

## 📁 폴더 구조

```
design/                            # 🎨 디자인 RAG 시스템
├── src/                           # 🧠 소스코드
│   ├── API_명세서.md              # API 명세서
│   ├── api.py                     # FastAPI 백엔드 서버
│   ├── design_chatbot.py          # 챗봇 실행 모듈
│   ├── design_chatbot.ipynb       # 챗봇 실행 모듈 (Jupyter 노트북 버전)
│   ├── prompts.py                 # 프롬프트 템플릿
│   ├── utils.py                   # 유틸리티 함수들
│  
│
├── data/                          # 📊 이미지 데이터 (구글 드라이브 다운로드)
│   ├── images/                    
│   │   ├── 3020230035272-api_xml-0_000.jpg
│   │   ├── ...
│   │  
├── chroma_db/                     # 🗄️ ChromaDB 벡터 데이터베이스 (구글 드라이브 다운로드)
│   ├── .DS_Store                  
│   ├── chroma.sqlite3             # ChromaDB 메인 데이터베이스
│   └── bba2cc98-8fd6-4bc3-a496-d78a6068a8f9/
│    
├── requirements.txt               
└── README.md                      
```

### 🚫 `.gitignore` 설정

```gitignore
data/
chroma_db/
.env
__pycache__/
*.pyc
temp_uploads/*
.DS_Store
```



## 🚀 실행 순서

### ⚡ Step 1: 데이터 다운로드 (최초 1회)
구글 드라이브에서 필요한 데이터(벡터DB & 이미지) 다운로드

꼭! 위 폴더 구조를 참고해, 다운로드한 폴더를 알맞은 위치에 배치해주세요.



1. **ChromaDB 벡터 데이터베이스** 다운로드(48.2MB)
- https://drive.google.com/drive/folders/1JkeGGx2MyGmmuUczrHQ0o-HDH74MWYtt?usp=drive_link 
- 위 링크에서 `chroma_db/` 폴더를 다운받아, 폴더 자체를 design 루트 디렉토리에 배치.


2. **이미지 데이터** 다운로드 (1.97 GB)
- https://drive.google.com/drive/folders/1JkeGGx2MyGmmuUczrHQ0o-HDH74MWYtt?usp=drive_link 
- 위 링크에서  `images/` 폴더를 다운받아, 폴더 자체를  `design/data/` 폴더에 배치. 
- 챗봇에서 이미지 표시할때 사용


### ⚙️ Step 2: 환경 설정
```bash
# 패키지 설치
pip install -r requirements.txt

# 환경변수 설정 (.env 파일 생성)
OPENAI_API_KEY=sk-...
KIPRISPLUS_API_KEY=...
TAVILY_API_KEY=tvly-...
```

### 🎯 Step 3: 서비스 실행

#### 🖥️ FastAPI 백엔드 서버 실행 
```bash
cd src
python api.py
# 또는
uvicorn api:app --reload --host 0.0.0.0 --port 8000

# 접속: http://localhost:8000
# API 문서: http://localhost:8000/docs
```

#### 💬 챗봇 실행 (테스트용)
```bash
cd src

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
# === LangChain 프레임워크 (실제 사용) ===
langchain==1.2.1
langchain-community==0.4.1
langchain-core==1.2.6
langchain-openai==1.1.6
langgraph==1.0.5
langgraph-checkpoint==3.0.1
langgraph-prebuilt==1.0.5

# === 모델 ===
torch>=2.1.0
numpy>=1.24.0
git+https://github.com/openai/CLIP.git

# === 데이터베이스 ===
chromadb>=0.4.0

# === 웹/API ===
fastapi>=0.104.0
uvicorn>=0.24.0
requests>=2.31.0

# === 이미지/파일 처리 ===
Pillow>=10.0.0
openpyxl>=3.1.0

# === 유틸리티 ===
python-dotenv>=1.0.0
```

### 설치
```bash
# 프로젝트 루트 디렉토리에서 실행
pip install -r requirements.txt
```

