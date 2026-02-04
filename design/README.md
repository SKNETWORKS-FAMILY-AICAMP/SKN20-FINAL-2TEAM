# Design RAG 시스템 📐

> 특허청 디자인 데이터를 기반으로 유사 디자인을 검색하고 분석하는 RAG(Retrieval-Augmented Generation) 시스템

## 📁 폴더 구조

```
design/
├── api_design.py          # API 데이터 수집
├── xml_to_json.py         # XML → JSON 변환
├── embeddings.py          # 이미지 임베딩 생성
├── vectordb.py            # 벡터 DB 구축
├── rag.py                 # 기본 RAG 체인
├── rag_advanced.py        # 고급 RAG 체인 (VLM 분석 포함)
├── app.py                 # Streamlit 채팅 인터페이스
└── README.md              # 이 파일
```

---

## 🔧 각 모듈별 기능

### 1️⃣ `api_design.py`
**역할**: 특허청 API에서 디자인 데이터 수집

**주요 기능**:
- 엑셀 파일(`.xlsx`)에서 출원번호 추출
- 특허청 KIPRIS+ API를 통해 서지상세정보(XML) 조회
- XML 파일을 `data/xml/` 폴더에 저장
- API 응답 상태 및 응답시간 로깅

**입력**: 
- `data/출원번호/2025_2026.xlsx` (출원번호 목록)
- 환경변수: `KIPRISPLUS_API_KEY`

**출력**: 
- `data/xml/2025_2026/` 폴더의 XML 파일들

---

### 2️⃣ `xml_to_json.py`
**역할**: 특허청 XML 데이터를 구조화된 JSON으로 변환

**주요 기능**:
- XML 파일 파싱 (네임스페이스 제거)
- 서지정보 추출 (출원번호, 디자인번호, 상태 등)
- 도면 이미지 다운로드 및 저장
- 출원인, 디자이너 정보 추출
- 로카르노 분류 코드 파싱
- 이미지당 1개의 JSON 생성

**입력**: 
- `data/xml/2025_2026/` 폴더의 XML 파일들

**출력**: 
- `data/json/2025_2026/` 폴더의 JSON 파일들
- `data/images/` 폴더의 이미지 파일들

**JSON 구조**:
```json
{
  "id": "3020250000208-09-01-0",
  "metadata": {
    "design_id": "3020250000208",
    "applicationNumber": "3020250000208",
    "articleName": "의자",
    "number": "1",
    "status": {
      "admstStat": "1(등록)"
    },
    "imagePath": "data/images/3020250000208-09-01-1.jpg"
  }
}
```

---

### 3️⃣ `embeddings.py`
**역할**: 도면 이미지를 CLIP 모델로 임베딩 벡터화

**주요 기능**:
- CLIP 모델(ViT-B/32) 로드 (GPU 자동 감지)
- JSON 파일에서 이미지 경로 읽기
- 각 이미지를 512차원 벡터로 변환
- 임베딩 벡터 + 메타데이터를 JSON 형식으로 저장

**입력**: 
- `data/json/2025_2026/` 폴더의 JSON 파일들
- `data/images/` 폴더의 이미지 파일들

**출력**: 
- `data/embeddings/` 폴더의 `{도면ID}_embedding.json` 파일들

**출력 JSON 구조**:
```json
{
  "id": "3020250000208-09-01-0",
  "embedding": [0.123, 0.456, ...],  # 512차원 벡터
  "metadata": {
    "design_id": "3020250000208",
    "applicationNumber": "3020250000208",
    ...
  }
}
```

---

### 4️⃣ `vectordb.py`
**역할**: 임베딩 벡터를 ChromaDB에 저장 및 인덱싱

**주요 기능**:
- ChromaDB Persistent Client 초기화 (`chroma_db/` 폴더)
- "design" 컬렉션 생성/로드
- 모든 임베딩 JSON을 벡터 DB에 일괄 저장
- 코사인 거리 기반 유사도 검색 설정

**입력**: 
- `data/embeddings/` 폴더의 모든 임베딩 JSON 파일

**출력**: 
- `chroma_db/` 폴더의 벡터 DB 데이터

**메타데이터 저장**:
- `design_id`: 디자인 고유 ID
- `applicationNumber`: 출원번호
- `LCCode`: 로카르노 분류 코드
- `articleName`: 상품명
- `imageNumber`: 도면 번호
- `admstStat`: 등록 상태
- `imagePath`: 이미지 저장 경로

---

### 5️⃣ `rag.py`
**역할**: 기본 RAG 체인 구현 (이미지 기반 유사 디자인 검색)

**주요 기능**:
- 이미지 입력 → CLIP 임베딩 생성
- ChromaDB에서 K-NN으로 유사 도면 검색
- 검색 결과를 GPT-4o로 분석 및 설명
- RAG 체인 구성

**주요 함수**:
```python
get_image_embedding(image_input)
# → CLIP 임베딩 생성
# 입력: 이미지 파일 경로 또는 PIL.Image
# 출력: 512차원 벡터

search_similar_designs(embedding, top_k=5)
# → 유사 도면 검색
# 입력: 임베딩 벡터, 검색 개수
# 출력: 유사 도면 메타데이터 리스트

design_search_chain(user_query, image_input, top_k=5)
# → 사진 + 텍스트 입력 → 검색 → LLM 분석
# 입력: 텍스트 질문, 이미지, 검색 개수
# 출력: LLM이 생성한 분석 결과
```

---

### 6️⃣ `rag_advanced.py`
**역할**: 고급 RAG 체인 (VLM 분석 + 상세 비교)

**주요 기능**:
- **입력 이미지 VLM 분석**: GPT-4o로 사용자 이미지 상세 분석
- **벡터 검색**: CLIP으로 유사 디자인 N개 추출
- **필터링**: 자신의 도면 제외, 출원번호별 1개만 선택
- **각 유사 디자인 VLM 분석**: 검색된 도면 상세 분석
- **비교 분석**: LLM으로 입력 이미지와 유사 디자인 비교
- **상세 리포트 생성**: 종합적인 유사도 분석 보고서

**처리 흐름**:
```
[입력 이미지]
    ↓
[GPT-4o VLM 분석] → 구조화된 설명 (JSON)
    ↓
[CLIP 벡터 검색] → 유사 디자인 추출
    ↓
[필터링] → 출원번호별 1개, 자신 도면 제거
    ↓
[각 유사 디자인 VLM 분석]
    ↓
[비교 분석 LLM]
    ↓
[상세 리포트 생성]
```

---

### 7️⃣ `app.py`
**역할**: Streamlit 기반 대화형 웹 인터페이스

**주요 기능**:
- 🎨 직관적인 웹 UI (와이드 레이아웃)
- 📸 이미지 업로드 지원
- 🤖 실시간 유사 디자인 검색
- 💬 LLM 기반 자연어 응답
- 🔄 캐싱으로 성능 최적화

**사용법**:
```bash
streamlit run app.py
```

**주요 컴포넌트**:
- 벡터 DB 로드 (캐시됨)
- CLIP 모델 로드 (GPU/CPU 자동 선택)
- GPT-4o 연동
- 유사도 거리 순으로 정렬된 결과 표시

---

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
#   - data/images/ 폴더에 이미지 저장
```

### Step 3: 이미지 임베딩 생성
```bash
python embeddings.py
# 결과: data/embeddings/ 폴더에 임베딩 JSON 생성
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

---

## 📊 데이터 흐름

```
특허청 KIPRIS+ API
    ↓ (api_design.py)
XML 파일 저장
    ↓ (xml_to_json.py)
JSON 파일 + 이미지 저장
    ↓ (embeddings.py)
임베딩 JSON 생성 (512차원 벡터)
    ↓ (vectordb.py)
ChromaDB 벡터 DB 구축
    ↓ (rag.py / rag_advanced.py)
검색 및 분석
    ↓ (app.py)
Streamlit 웹 인터페이스로 제공
```

---

## 📌 주요 기술 스택

| 기술 | 용도 |
|------|------|
| **CLIP** | 이미지 임베딩 (ViT-B/32, 512차원) |
| **ChromaDB** | 벡터 DB (코사인 거리 기반) |
| **GPT-4o** | 텍스트 분석 및 생성 |
| **Streamlit** | 웹 UI |
| **LangChain** | LLM 체인 구성 |
| **Torch** | GPU 지원 |

---

## 🎯 사용 시나리오

### 시나리오 1: 디자인 유사도 검사
1. 새로운 디자인 이미지 업로드
2. 시스템이 자동으로 유사한 기존 디자인 검색
3. 의장권 출원 전 선행 기술 확인

### 시나리오 2: 디자인 트렌드 분석
1. 특정 카테고리의 디자인 특성 분석
2. 유사한 디자인들의 출원 현황 파악
3. 시장 트렌드 및 공백 영역 발굴

### 시나리오 3: 포트폴리오 관리
1. 기업의 기존 디자인 등록 현황 조회
2. 신규 디자인이 기존 디자인과의 관계 파악
3. 지적재산권 포트폴리오 최적화

---

## 🔗 관련 폴더

- **`data/xml/`**: 특허청 API 응답 XML
- **`data/json/`**: 구조화된 메타데이터 JSON
- **`data/images/`**: 다운로드된 도면 이미지
- **`data/embeddings/`**: CLIP 임베딩 벡터
- **`chroma_db/`**: ChromaDB 벡터 데이터베이스
- **`data/출원번호/`**: 입력 데이터 (출원번호 목록)

---

## 📝 라이선스

SKN AI 2.0 팀 프로젝트

---

## 💡 참고 사항

- **GPU 권장**: CLIP 모델 실행 시 GPU 사용 권장 (CPU는 느림)
- **API 제한**: KIPRIS+ API는 요청 수 제한이 있음 (rate limiting)
- **이미지 품질**: 고해상도 이미지일수록 임베딩 품질 향상
- **벡터 DB 크기**: 도면 개수가 많을수록 검색 시간 증가 (최적화 필요)

