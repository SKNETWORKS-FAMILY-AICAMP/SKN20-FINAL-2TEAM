# FTO Design Similarity Analysis System

AI 기반 특허 디자인 유사도 분석 시스템

---

## 🎯 시스템 개요

21,829개의 특허 스케치 이미지를 기반으로 사용자 입력(이미지 또는 텍스트)과 유사한 디자인을 검색하고, 멀티 LLM을 활용하여 형상 차이점을 분석하는 FTO(Freedom To Operate) 보조 시스템입니다.

### 주요 기능
1. **이미지/텍스트 기반 유사도 검색** - CLIP 임베딩 + Hybrid Retrieval
2. **멀티 LLM 비교** - 3개 모델(GPT-4o-mini, GPT-4o, O1)의 답변을 사용자가 선택
3. **법적 근거 제시** - 형상 차이/공통점을 객관적으로 서술

---

## 📁 프로젝트 구조

```
FTO_Flow/
│
├── 📂 data/                          # 데이터 디렉토리
│   ├── 📂 images_v2/                 # ⭐ 21,829개 스케치 이미지
│   ├── 📂 embeddings_v2/             # ⭐ 21,829개 CLIP 임베딩 (JSON)
│   ├── 📂 chroma_db_v2/              # ⭐ ChromaDB 벡터 데이터베이스
│   ├── 📂 api_xml/                   # 특허 API XML 데이터
│   ├── 📂 json/                      # JSON 메타데이터
│   └── 📂 rawdata/
│       └── 1981-2026.xlsx            # 원본 엑셀 데이터
│
├── 📂 backend/                       # 백엔드 Python 코드
│   ├── 📄 config_v2.py               # ⚙️ 실제 데이터 구조 반영 설정
│   ├── 📄 router_and_embedding_04_v2.py  # 🧭 사전 임베딩 활용 라우터
│   ├── 📄 hybrid_retriever_05_v2.py  # 🔍 ChromaDB 하이브리드 검색
│   ├── 📄 llm_pipeline_06_improved.py  # 🤖 멀티 LLM 파이프라인
│   └── 📄 main_api_v2.py             # 🌐 FastAPI 서버
│
├── 📂 frontend/                      # 프론트엔드 파일
│   ├── 📄 about.html                 # 메인 UI
│   ├── 📄 analysis.html              # 분석 페이지
│   ├── 📄 chat.html                  # 채팅 인터페이스
│   └── 📄 frontend_integration.js    # API 연동
│
├── 📂 scripts/                       # 유틸리티 스크립트
│   ├── 📄 test_chroma_connection.py  # ChromaDB 연결 테스트
│   └── 📄 analyze_embeddings.py      # 임베딩 분석
│
├── 📂 uploads/                       # 사용자 업로드 임시 저장
├── 📂 outputs/                       # 분석 결과 출력
├── 📂 logs/                          # 로그 파일
│
├── 📄 .env                           # 환경 변수 (OPENAI_API_KEY)
├── 📄 .gitignore                     # Git ignore
├── 📄 requirements.txt               # Python 의존성
└── 📄 README.md                      # 이 문서
```

---

## 🚀 Quick Start

### **필수 조건**
- Python 3.9+
- 21,829개 스케치 이미지 (`data/images_v2/`)
- 사전 계산된 임베딩 (`data/embeddings_v2/`)
- ChromaDB (`data/chroma_db_v2/`)

### **Step 1: 환경 설정**

```bash
# 프로젝트 클론
cd FTO_Flow

# 가상환경 생성
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt
```

### **Step 2: 환경 변수 설정**

```bash
# .env 파일 생성
cat > .env << EOF
OPENAI_API_KEY=sk-your-api-key-here
LOG_LEVEL=INFO
EOF
```

### **Step 3: ChromaDB 연결 확인**

```bash
cd backend
python -c "
from hybrid_retriever_05_v2 import ChromaDBClient
client = ChromaDBClient()
print(f'✅ ChromaDB connected! {client.collection.count():,} sketches loaded')
"

# 출력 예시:
# 🔗 Connecting to ChromaDB at data/chroma_db_v2
# ✅ Collection 'sketch_embeddings' loaded (21,829 items)
# ✅ ChromaDB connected! 21,829 sketches loaded
```

### **Step 4: 검색 테스트**

```python
# test_search.py
from pathlib import Path
from hybrid_retriever_05_v2 import hybrid_retrieve, ChromaDBClient

# ChromaDB 초기화
chroma = ChromaDBClient()

# 텍스트 쿼리
query = "원통형 머그컵 디자인"
results = hybrid_retrieve(query, chroma_client=chroma, final_topk=10)

print(f"Found {len(results)} similar sketches:")
for i, doc in enumerate(results, 1):
    print(f"[{i}] {doc.doc_id}")
    print(f"    Image: {doc.image_path}")
    print(f"    Score: {doc.rrf_score:.3f}")
```

### **Step 5: API 서버 실행**

```bash
cd backend
uvicorn main_api_v2:app --reload --host 0.0.0.0 --port 8000

# 브라우저에서 확인
# http://localhost:8000/docs (Swagger UI)
```

### **Step 6: 프론트엔드 실행**

```bash
cd frontend
python -m http.server 8080

# 브라우저 접속
# http://localhost:8080/about.html
```

---

## 📊 데이터 구조

### **실제 데이터**

| 디렉토리 | 개수 | 설명 |
|---------|------|------|
| `images_v2/` | 21,829개 | 스케치 이미지 (.jpg) |
| `embeddings_v2/` | 21,829개 | CLIP 임베딩 (.json) |
| `chroma_db_v2/` | 21,829개 | 벡터 데이터베이스 |

### **임베딩 JSON 구조**

```json
{
  "embedding": [0.123, -0.456, 0.789, ...]  // 512차원 벡터
}
```

### **ChromaDB 메타데이터 구조**

```json
{
  "image_path": "data/images_v2/sketch_0001.jpg",
  "design_no": "30-2023-0001",
  "applicant": "Samsung Electronics",
  "shape_description": "원통형 몸체, 상단 돌출 캡"
}
```

---

## 🔑 핵심 기능

### **1. 하이브리드 검색 (Hybrid Retrieval)**

```
User Input (Image/Text)
    ↓
CLIP Embedding
    ↓
Hybrid Retrieval
    ├── BM25 (Keyword-based) → Top 20
    └── Dense (Vector-based) → Top 20
    ↓
RRF (Reciprocal Rank Fusion) → Top 10
    ↓
(Optional) Reranker
    ↓
Similar Sketches
```

### **2. 멀티 LLM 분석**

```python
# 3개 LLM 모델 동시 호출
models = ["gpt-4o-mini", "gpt-4o", "o1"]

for model in models:
    response = llm.invoke(prompt)
    # 형상 차이/공통점 분석

# 사용자가 최종 모델 선택
selected_answer = user_selected_model_answer
```

### **3. 사전 계산 임베딩 활용**

```python
# 이미 계산된 임베딩 사용 (빠름)
embedding = load_from_json("data/embeddings_v2/sketch_0001.json")

# 새 이미지는 CLIP으로 실시간 계산
if not precomputed:
    embedding = clip_model.encode_image(new_image)
```

---

## 🛠️ 주요 컴포넌트

### **Backend 파일**

| 파일 | 역할 |
|------|------|
| `config_v2.py` | 실제 데이터 구조 반영 설정 |
| `router_and_embedding_04_v2.py` | 사전 임베딩 로드 + CLIP 실시간 임베딩 |
| `hybrid_retriever_05_v2.py` | ChromaDB 검색 + BM25 + RRF |
| `llm_pipeline_06_improved.py` | 멀티 LLM 호출 (Async) |
| `main_api_v2.py` | FastAPI 서버 |

### **API 엔드포인트**

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/health` | 서버 상태 확인 |
| POST | `/analyze/image` | 이미지 업로드 분석 |
| POST | `/analyze/text` | 텍스트 쿼리 분석 |
| GET | `/results/{analysis_id}` | 분석 결과 조회 |
| POST | `/llm/select` | LLM 모델 선택 |

---

## 📈 성능 지표

### **검색 성능**
- **데이터셋**: 21,829개 스케치
- **검색 속도**: < 100ms (ChromaDB)
- **Top-10 정확도**: ~85% (사용자 피드백 기준)

### **임베딩 성능**
- **모델**: OpenCLIP ViT-B-32
- **차원**: 512
- **사전 계산**: ✅ (실시간 계산 불필요)

---

## 🧪 테스트

### **ChromaDB 연결 테스트**

```bash
python scripts/test_chroma_connection.py
```

### **검색 테스트**

```python
from hybrid_retriever_05_v2 import hybrid_retrieve, ChromaDBClient

chroma = ChromaDBClient()

# 텍스트 검색
results = hybrid_retrieve("원통형 디자인", chroma_client=chroma)

# 이미지 검색
from pathlib import Path
results = hybrid_retrieve(Path("uploads/user_image.jpg"), chroma_client=chroma)
```

### **API 테스트**

```bash
# Health check
curl http://localhost:8000/health

# 텍스트 분석
curl -X POST http://localhost:8000/analyze/text \
  -H "Content-Type: application/json" \
  -d '{"description": "원통형 머그컵"}'

# 이미지 분석
curl -X POST http://localhost:8000/analyze/image \
  -F "file=@test_image.jpg"
```

---

## 🔧 설정 커스터마이징

### **config_v2.py 주요 설정**

```python
# 데이터 경로
DATA_CONFIG.images_dir = Path("data/images_v2")
DATA_CONFIG.embeddings_dir = Path("data/embeddings_v2")
DATA_CONFIG.chroma_db_path = Path("data/chroma_db_v2")

# 검색 설정
RETRIEVAL_CONFIG.topk_each = 20      # BM25/Dense 각각 Top-20
RETRIEVAL_CONFIG.final_topk = 10     # 최종 Top-10
RETRIEVAL_CONFIG.rrf_threshold = 0.8 # Reranker 활성화 임계값

# LLM 설정
LLM_CONFIG.models = ["gpt-4o-mini", "gpt-4o", "o1"]
LLM_CONFIG.temperature = 0.7
```

---

## 🐛 트러블슈팅

### **1. ChromaDB Collection Not Found**

```python
# Collection 이름 확인
from hybrid_retriever_05_v2 import ChromaDBClient
client = ChromaDBClient()

# config_v2.py에서 collection_name 수정
RETRIEVAL_CONFIG.collection_name = "실제_컬렉션_이름"
```

### **2. 임베딩 JSON 로드 실패**

```python
# JSON 구조 확인
import json
from pathlib import Path

sample = Path("data/embeddings_v2").glob("*.json").__next__()
with open(sample) as f:
    data = json.load(f)

print(f"Keys: {data.keys() if isinstance(data, dict) else 'list'}")
```

### **3. CUDA Out of Memory**

```python
# config_v2.py에서 batch_size 조정
MODEL_CONFIG.batch_size = 8  # 기본값 16
```

### **4. API CORS Error**

```python
# main_api_v2.py에 CORS 추가
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 📚 사용 예시

### **시나리오 1: 사용자 이미지 업로드**

```python
from pathlib import Path
from hybrid_retriever_05_v2 import hybrid_retrieve, ChromaDBClient
from llm_pipeline_06_improved import ask_all_models

# 1. 사용자 이미지
user_image = Path("uploads/user_design.jpg")

# 2. 유사 스케치 검색
chroma = ChromaDBClient()
similar = hybrid_retrieve(user_image, chroma_client=chroma, final_topk=10)

# 3. LLM 분석
input_desc = "사용자 업로드 디자인"
llm_answers = ask_all_models(input_desc, similar)

# 4. 결과 출력
for model, answer in llm_answers.items():
    print(f"\n[{model}]\n{answer}")
```

### **시나리오 2: 텍스트 쿼리**

```python
query = "원통형 몸체, 상단 캡, 하부 평면"

chroma = ChromaDBClient()
results = hybrid_retrieve(query, chroma_client=chroma, final_topk=10)

for i, doc in enumerate(results, 1):
    print(f"[{i}] {doc.image_path} (Score: {doc.rrf_score:.3f})")
```

### **시나리오 3: 메타데이터 활용**

```python
import pandas as pd

# 엑셀 데이터 로드
df = pd.read_excel("data/rawdata/1981-2026.xlsx")

# 특정 디자인 정보 추출
design_no = "30-2023-0001"
info = df[df['디자인번호'] == design_no]

print(info[['출원인', '출원일', '공개일']])
```

---

## 🎯 향후 개선 방향

### **Short-term**
- [ ] 메타데이터 자동 로드 (1981-2026.xlsx → ChromaDB)
- [ ] Vision-Language Model 통합 (자동 shape description)
- [ ] 캐싱 전략 (자주 검색되는 쿼리)

### **Mid-term**
- [ ] Fine-tuning CLIP (도메인 특화)
- [ ] Active Learning 도입
- [ ] A/B 테스트 프레임워크

### **Long-term**
- [ ] 멀티모달 융합 (이미지 + 텍스트 동시)
- [ ] 자체 Reranker 학습
- [ ] 실시간 스트리밍 답변

---

## 📝 라이선스

MIT License

---

## 👥 팀

- **Data Science Team** - 데이터 분석 및 모델 개발
- **ML Engineering Team** - 검색 시스템 구축
- **Legal Advisory Team** - FTO 분석 기준 수립

---

## 📞 문의

- **Email**: fto-support@company.com
- **Slack**: #fto-analysis
- **GitHub Issues**: [프로젝트 이슈 트래커]

---

## 🙏 Acknowledgments

- **OpenCLIP** - 이미지 임베딩
- **ChromaDB** - 벡터 데이터베이스
- **LangChain** - LLM 통합
- **FastAPI** - API 프레임워크

---

## 📖 추가 문서

- [API Documentation](docs/API_DOCUMENTATION.md)
- [Model Architecture](docs/MODEL_ARCHITECTURE.md)
- [Deployment Guide](docs/DEPLOYMENT_GUIDE.md)
- [Updated Project Guide](UPDATED_PROJECT_GUIDE.md)

---

**Last Updated**: 2024-02-14  
**Version**: 2.0.0 (실제 데이터 구조 반영)