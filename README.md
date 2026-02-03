# FTO 이미지 챗봇 프로젝트

FTO 이미지 챗봇 프로젝트의 데이터 전처리 과정을 설명합니다. KIPRIS OpenAPI에서 수집한 원본 XML 데이터를 JSON으로 변환하고, OpenCLIP 임베딩 벡터로 가공하여 유사도 검색 시스템을 구축합니다.

## 📋 목차

1. [전처리 흐름도](#전처리-흐름도)
2. [파일별 역할 설명](#파일별-역할-설명)
3. [원본 데이터 구조](#원본-데이터-구조)
4. [단계별 상세 설명](#단계별-상세-설명)
5. [생성되는 파일 목록](#생성되는-파일-목록)
6. [실행 방법](#실행-방법)
7. [데이터 형식 예시](#데이터-형식-예시)
8. [문제 해결](#문제-해결)

---

## 전처리 흐름도

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          데이터 전처리 파이프라인                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────┐       │
│  │                    [0단계] 원본 데이터 수집                           │       │
│  │  ┌────────────────────────┐    ┌───────────────────────┐         │       │
│  │  │  2000_raw_data/        │    │  2000_xml/            │         │       │
│  │  │  └─ 2000.xlsx (464 건)  │   │  └── *.xml (464 건)    │         │       │
│  │  │  (출원번호 목록)          │    │  (KIPRIS OpenAPI)      │        │       │
│  │  └─────── ──┬─────────────┘    └─────────┬─────────────┘         │       │
│  │             │                            │                       │       │
│  │             └──────────┬─────────────────┘                       │       │
│  │                        ▼                                         │       │
│  │            ┌─────────────────────┐                               │       │
│  │            │  XML → JSON 파싱     │                               │       │
│  │            │  (이미지별 분리)       │                               │       │
│  │            └─────────┬───────────┘                               │       │
│  │                      ▼                                           │       │
│  │            ┌─────────────────────┐                               │       │
│  │            │  2000_json/*.json   │  ← 이미지1개 당 JSON 파일 1개     │       │
│  │            │  (3,324 건)          │                              │       │
│  │            └─────────────────────┘                               │      │
│  └──────────────────────────────────────────────────────────────────┘      │
│                       │                                                    │
│                       ▼                                                    │
│  ┌──────────────────────────────────────────────────────────────────┐      │
│  │              [1단계] openclip_vector_similarity_v1.py             │      | │  |                                                                  |      |
│  │  ┌─────────────────────────────────────────────────────────────┐ │      │
│  │  │  1. JSON 파일 로드 및 파싱                                      │ │      │
│  │  │  2. 이미지 URL → 로컬 다운로드 (data/img/)                       │ │      │
│  │  │  3. document 문서 생성 (제품명, 분류, 출원인, 요점, 설명)            │ │      │
│  │  │  4. OpenCLIP 이미지 임베딩 (ViT-L-14, 768차원)                   │ │      │
│  │  │  5. OpenCLIP 텍스트 임베딩 (동일 임베딩 공간)                       │ │      │
│  │  │  6. L2 정규화 후 코사인 유사도 계산                                │ │      │
│  │  └─────────────────────────────────────────────────────────────┘ │       │
│  └─────────┬────────────────────────────┬─────────────────────────────┘   │
│            │                            │                                 │
│            ▼                            ▼                                 │
│  ┌──────────────────────────┐  ┌──────────────────────────┐              │
│  │ openclip_metadata.jsonl  │  │ openclip_embeddings.npz  │              │
│  ├──────────────────────────┤  ├──────────────────────────┤              │
│  │ • id(출원번호+르카르노분류코드) │  │ • ids (N,)               │              │
│  │ • document               │  │ • image_embeddings       │              │
│  │ • metadata               │  │   (N, 768)               │              │
│  │ • image_text_cosine      │  │ • text_embeddings        │              │
│  │                          │  │   (N, 768)               │              │
│  │                          │  │ • image_text_cosine      │              │
│  │                          │  │   (N,)                   │              │
│  └──────────┬───────────────┘  └──────────────────────────┘              │
│             ▼                                                             │
│  ┌──────────────────────────────────────────────────────────────────┐       │
│  │                   [2단계] Split_jsonl.py                          │       │
│  │  ┌─────────────────────────────────────────────────────────────┐ │       │
│  │  │  1. JSONL 라인별 파싱                                          │ │       
│  │  │  2. document/metadata 분리                                   │ │       │
│  │  │  3. metadata 평탄화 (중첩 dict → 1-depth)                     │ │       │
│  │  │  4. ID 추출 또는 자동 생성                                      │ │       │
│  │  └─────────────────────────────────────────────────────────────┘ │       │
│  └────────┬─────────────────────────┬───────────────────────────────┘       │
│           │                         │                                       │
│           ▼                         ▼                                       │
│  ┌─────────────────────┐   ┌─────────────────────┐                          │
│  │  documents.jsonl    │   │  metadata.parquet   │                          │
│  │  • id               │   │  (컬럼 기반 저장)      │                          │
│  │  • document         │   │                     │                          │
│  └─────────────────────┘   └─────────────────────┘                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 파일별 역할 설명

프로젝트의 각 파일이 담당하는 역할을 설명합니다.

### 📁 루트 디렉토리 (`/`)

| 파일명 | 역할 | 설명 |
|--------|------|------|
| `2000_xml_to_json.py` | **XML→JSON 변환기** | KIPRIS OpenAPI에서 수집한 XML 파일을 파싱하여 이미지별로 분리된 JSON 파일로 변환합니다. 1개 XML에서 이미지 개수만큼 JSON 파일을 생성합니다. |
| `2000img_extraction.py` | **이미지 추출기** | XML 파일에서 이미지 URL 정보를 추출하고, 이미지를 로컬에 다운로드하여 CSV로 정리합니다. |
| `데이터전처리.md` | **문서화** | 데이터 전처리 파이프라인의 전체 흐름과 사용법을 설명하는 문서입니다. |
| `종합흐름.md` | **문서화** | 프로젝트 전체 아키텍처와 흐름을 설명하는 종합 문서입니다. |

### 📁 데이터 폴더 (`/data`)

| 파일명 | 역할 | 설명 |
|--------|------|------|
| `fetch_kipris_xml.py` | **API 데이터 수집** | KIPRIS OpenAPI를 호출하여 특정 출원번호의 XML 데이터를 가져와 저장합니다. API 키와 출원번호를 입력받아 XML 파일을 생성합니다. |
| `openclip_vector_similarity_v1.py` | **임베딩 생성기** | JSON 파일들을 읽어 이미지를 다운로드하고, OpenCLIP 모델(ViT-L-14)로 이미지/텍스트 임베딩을 생성합니다. L2 정규화 후 코사인 유사도를 계산하여 저장합니다. |
| `Split_jsonl.py` | **JSONL 분리기** | `openclip_metadata.jsonl`을 파싱하여 `documents.jsonl`과 `metadata.parquet`으로 분리합니다. 메타데이터를 평탄화하고 ID를 추출/생성합니다. |
| `openclip_metadata.jsonl` | **메타데이터 저장소** | 임베딩 생성 시 함께 저장된 메타데이터 파일입니다. ID, document, metadata, 이미지-텍스트 코사인 유사도를 포함합니다. |
| `openclip_embeddings.npz` | **임베딩 벡터 저장소** | NumPy 압축 형식으로 저장된 임베딩 벡터입니다. IDs(N,), 이미지 임베딩(N, 768), 텍스트 임베딩(N, 768)을 포함합니다. |
| `documents.jsonl` | **문서 저장소** | 검색용으로 분리된 document 파일입니다. ID와 document 텍스트만 포함합니다. |

### 📁 소스 코드 폴더 (`/src`)

| 파일명 | 역할 | 설명 |
|--------|------|------|
| `app.py` | **웹 애플리케이션** | Streamlit 기반 웹 UI입니다. 사용자가 이미지를 업로드하면 유사 이미지를 검색하고, LLM으로 분석 결과를 설명합니다. 챗봇 인터페이스를 제공합니다. |
| `main.py` | **CLI 진입점** | 명령줄 인터페이스(CLI)로 유사도 분석을 실행합니다. 이미지 경로를 입력받아 유사 이미지를 검색하고 마크다운/PDF 리포트를 생성합니다. |
| `config.py` | **설정 관리** | 프로젝트 설정을 관리합니다. 데이터 파일 경로, OpenCLIP 모델 설정, 검색 파라미터(top_k, min_similarity), LLM 설정 등을 정의합니다. 임베딩 차원에 따라 모델을 자동 감지합니다. |
| `embedder.py` | **임베딩 생성기** | OpenCLIP 모델을 로드하고 이미지를 임베딩 벡터로 변환합니다. MPS/CUDA/CPU 디바이스를 자동 감지하고, L2 정규화된 벡터를 반환합니다. |
| `io_utils.py` | **입출력 유틸리티** | JSONL 파일 읽기, 키 기반 인덱스 생성, NPZ 임베딩 파일 로드 등 데이터 입출력 관련 함수를 제공합니다. |
| `similarity.py` | **유사도 계산** | 코사인 유사도를 계산하고 상위 K개의 유사 이미지를 검색합니다. L2 정규화, 점수 정렬, 최소 유사도 필터링을 수행합니다. |
| `llm_explain.py` | **LLM 분석기** | Ollama 기반 로컬 LLM(qwen2.5:14b)을 호출하여 유사도 결과를 분석하고 사람이 이해하기 쉬운 설명을 생성합니다. JSON 형식의 구조화된 분석 결과를 반환합니다. |
| `report.py` | **리포트 생성기** | 유사도 분석 결과를 마크다운 형식의 리포트로 변환합니다. PDF 변환 기능도 제공합니다. 요약, 순위표, 상세 분석 섹션을 포함합니다. |

### 📁 데이터 하위 폴더

| 폴더명 | 역할 | 설명 |
|--------|------|------|
| `2000_raw_data/` | **원본 데이터** | KIPRIS 홈페이지에서 수동 다운로드한 Excel 파일(출원번호 목록)이 저장됩니다. |
| `2000_xml/` | **XML 데이터** | KIPRIS OpenAPI에서 수집한 원본 XML 파일들이 저장됩니다. (출원번호당 1개) |
| `2000_json/` | **JSON 데이터** | XML에서 변환된 JSON 파일들이 저장됩니다. (이미지당 1개) |
| `img/` | **이미지 저장소** | 다운로드된 이미지 파일들이 저장됩니다. |
| `test_output/` | **테스트 출력** | 테스트 실행 시 생성되는 출력 파일들이 저장됩니다. |

### 🔄 파일 간 의존 관계

```
┌────────────────────────────────────────────────────────────────────────────┐
│                           파일 의존 관계도                                    │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│   [데이터 수집 단계]                                                          │
│   fetch_kipris_xml.py → 2000_xml/*.xml                                     │
│                              │                                             │
│                              ▼                                             │
│   [전처리 단계]                                                               │
│   2000_xml_to_json.py → 2000_json/*.json                                   │
│   2000img_extraction.py → img/*.jpg (이미지 다운로드)                          │
│                              │                                             │
│                              ▼                                             │
│   [임베딩 단계]                                                               │
│   openclip_vector_similarity_v1.py                                         │
│       → openclip_metadata.jsonl                                            │
│       → openclip_embeddings.npz                                            │
│                              │                                             │
│                              ▼                                             │
│   [분리 단계]                                                                 │
│   Split_jsonl.py → documents.jsonl                                         │
│                              │                                             │
│                              ▼                                             │
│   [서비스 단계]                                                               │
│   ┌─────────────────────────────────────────────────────────────┐          │
│   │  app.py (웹 UI)  또는  main.py (CLI)                          │          │
│   │      │                                                       │          │
│   │      ├── config.py (설정 로드)                                 │          │
│   │      ├── io_utils.py (데이터 로드)                             │          │
│   │      ├── embedder.py (이미지 임베딩)                            │          │
│   │      ├── similarity.py (유사도 검색)                           │          │
│   │      ├── llm_explain.py (LLM 분석)                           │          │
│   │      └── report.py (리포트 생성)                               │          │
│   └─────────────────────────────────────────────────────────────┘          │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 원본 데이터 구조

### 0단계: 원본 데이터 수집 (KIPRIS OpenAPI)

#### 데이터 수집 프로세스

```
┌──────────────────────────────────────────────────────────────────┐
│                    0단계: 데이터 수집 파이프라인                        │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1️⃣ KIPRIS 홈페이지 Excel 파일 다운로드 (수동)                          │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  2000_raw_data/2000.xlsx                                   │  │
│  │  ┌──────────────┬──────────────┬──────────────┐            │  │
│  │  │ 출원번호       │ 등록일        │ 물품명          │           │  │
│  │  ├──────────────┼──────────────┼──────────────┤            │  │
│  │  │ 3020000000039│ 2000.05.15   │ 포장용 병      │            │  │
│  │  │ 3020000000414│ 2000.06.20   │ 시계          │            │  │
│  │  │ ...          │ ...          │ ...          │            │  │
│  │  └──────────────┴──────────────┴──────────────┘            │  │
|  |   ... 464 건                                               |  |
│  └────────────────────────────────────────────────────────────┘  │
│                           │                                      │
│                           ▼                                      │
│  2️⃣ KIPRIS OpenAPI 호출 (출원번호별)                                 │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  for 출원번호 in 2000.xlsx:                                  │  │
│  │      response = requests.get(                              │  │
│  │          "http://plus.kipris.or.kr/openapi/...",           │  │
│  │          params={"applicationNumber": 출원번호}              │  │
│  │      )                                                     │  │
│  │      save to 2000_xml/{출원번호}.xml                         │  │
│  └────────────────────────────────────────────────────────────┘  │
│                           │                                      │
│                           ▼                                      │
│  3️⃣ XML 파일 저장                                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  2000_xml/                                                 │  │
│  │  ├── 3020000000039.xml  (출원번호당 1개 XML)                  │  │
│  │  ├── 3020000000414.xml                                     │  │
│  │  └── ... (464 건 파일)                                       │  │
│  └────────────────────────────────────────────────────────────┘  │
│                           │                                      │
│                           ▼                                      │
│  4️⃣ XML → JSON 변환 (2000_xml_to_json.py)                          │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  1개 XML 파일 → 이미지 개수만큼 JSON 파일 분리                     │  │
│  │                                                            │  │
│  │  예: 3020000000039.xml (이미지 7개)                           │  │
│  │      ↓                                                     │  │
│  │      ├── 3020000000039-01.json                             │  │
│  │      ├── 3020000000039-02.json                             │  │
│  │      ├── ...                                               │  │
│  │      └── 3020000000039-07.json                             │  │
│  └────────────────────────────────────────────────────────────┘  │
│                           │                                      │
│                           ▼                                      │
│  5️⃣ JSON 파일 생성 완료                                              │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  2000_json/                                                │  │
│  │  ├── 3020000000039-01.json  (이미지당 1개 JSON)               │  │
│  │  ├── 3020000000039-02.json                                 │  │
│  │  └── ... (3,324 건)                                         │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

#### 데이터 소스

| 파일/폴더 | 설명 | 형식 | 생성 방법 |
|-----------|------|------|----------|
| `2000_raw_data/2000.xlsx` | 2000년도 디자인 출원번호 목록 | Excel | **수동 다운로드** |
| `2000_xml/*.xml` | KIPRIS OpenAPI 응답 데이터 (464건) | XML | **KIPRIS OpenAPI 호출** |
| `2000_json/*.json` | 이미지별 분리된 JSON (3,324건) | JSON | **`2000_xml_to_json.py`** |

#### 0-1단계: Excel → XML (KIPRIS OpenAPI)

**목적**: Excel에 정리된 출원번호 목록을 기반으로 KIPRIS OpenAPI에서 상세 정보 수집

**주의**: 이 단계는 **수동 또는 별도 스크립트**로 수행되며, 본 문서에는 자동화 스크립트가 포함되어 있지 않습니다.

**수동 수행 방법**:
1. `2000.xlsx` 파일에서 출원번호 목록 확인
2. KIPRIS Plus 사이트에서 출원번호별 OpenAPI 호출
3. 응답 XML을 `2000_xml/` 폴더에 저장

**KIPRIS OpenAPI 예시**:
```bash
# 출원번호: 3020000000039
curl "http://plus.kipris.or.kr/openapi/service?applicationNumber=3020000000039" \
  -o 2000_xml/3020000000039.xml
```

#### 0-2단계: XML → JSON 변환

**실행 파일**: `2000_xml_to_json.py`

**핵심 로직**:
- **1개 XML 파일** → **이미지 개수만큼 JSON 파일** 생성
- 각 이미지마다 독립적인 JSON 파일로 분리
- 파일명: `{출원번호}-{이미지번호}.json` (예: `3020000000039-01.json`)

**실행 방법**:
```bash
python 2000_xml_to_json.py \
  --input ./data/2000_xml \
  --output ./data/2000_json
```

**변환 예시**:
```
3020000000039.xml (1개 파일, 7개 이미지 포함)
    ↓ 2000_xml_to_json.py
    ├── 3020000000039-01.json
    ├── 3020000000039-02.json
    ├── 3020000000039-03.json
    ├── 3020000000039-04.json
    ├── 3020000000039-05.json
    ├── 3020000000039-06.json
    └── 3020000000039-07.json
```

### JSON 파일 스키마 (`2000_json/*.json`)

XML에서 파싱된 JSON 파일 구조입니다.
JSON 파일로 변환할때 해당 column만 추출하였습니다.

```json
{
  "design_id": "3020000000039-09-01",
  "applicationNumber": "3020000000039",
  "registrationNumber": "3002602570000",
  "publicationNumber": null,
  "status": {
    "regFg": "Y",
    "admstStat": "소멸",
    "lastDispositionDate": "2000-02-25"
  },
  "meta": {
    "articleName": "포장용 병",
    "LCCode": "09-01",
    "designNumber": "M01",
    "applicantName": "문영만",
    "agentName": null
  },
  "creative": {
    "designSummary": "<P N=\"1\">포장용 병의 형상과 모양의 결합을 의장 창작 내용의 요점으로 함.</P>",
    "designDescription": "<P N=\"1\">1. 재질은 점토임. </P>"
  },
  "image": {
    "image_id": "3020000000039-01",
    "imageName": "000.JPG",
    "imagePath": "http://plus.kipris.or.kr/openapi/fileToss.jsp?arg=...",
    "number": "1"
  }
}
```

### 필드 설명

| 필드 | 설명 | 예시 | 원본 XML 경로 |
|------|------|------|---------------|
| `design_id` | 디자인 고유 식별자 | `3020000000039-09-01` | 생성됨 |
| `applicationNumber` | 출원번호 | `3020000000039` | `biblioSummaryInfo/applicationNumber` |
| `registrationNumber` | 등록번호 | `3002602570000` | `biblioSummaryInfo/registrationNumber` |
| `status.admstStat` | 행정 상태 | `소멸`, `등록` | `biblioSummaryInfo/admstStat` |
| `meta.articleName` | 제품명 (물품명) | `포장용 병` | `biblioSummaryInfo/articleName` |
| `meta.LCCode` | 로카르노 분류 코드 | `09-01` | `classificationCodeInfo` |
| `meta.applicantName` | 출원인 | `문영만` | `applicantInfo/applicantName` |
| `creative.designSummary` | 디자인 요점 | HTML 태그 포함 | `creativeSummaryInfo/designSummary` |
| `creative.designDescription` | 디자인 설명 | HTML 태그 포함 | `creativeDescriptionInfo/designDescription` |
| `image.imagePath` | 이미지 다운로드 URL | KIPRIS URL | `imagePath/largePath` |

---

## 단계별 상세 설명

### 1단계: OpenCLIP 임베딩 생성

**실행 파일**: `data/openclip_vector_similarity_v1.py`

#### 처리 과정

```
┌─────────────────────────────────────────────────────────────────────┐
│                        OpenCLIP 임베딩 파이프라인                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1️⃣ JSON 로드 및 레코드 생성                                             │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  • glob("*.json")으로 모든 JSON 파일 수집                        │    │
│  │  • design_id, applicationNumber, image_id 추출                │    │
│  │  • doc_id = "{design_id}::{image_id}" 형식으로 고유 ID 생성      │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                               │                                     │
│                               ▼                                     │
│  2️⃣ 이미지 다운로드                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  • image.imagePath URL에서 이미지 다운로드                        │    │
│  │  • 저장 경로: data/img/{doc_id}.jpg                            │    │
│  │  • 실패 시 경고 출력 후 해당 레코드 스킵                             │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                               │                                     │
│                               ▼                                     │
│  3️⃣ 텍스트 문서 생성 (build_document 함수)                               │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  document = """                                             │    │
│  │  제품명: {meta.articleName}                                   │    │
│  │  Locarno: {meta.LCCode}                                     │    │
│  │  출원인: {meta.applicantName}                                 │    │
│  │  요점: {creative.designSummary}                               │    │
│  │  디자인설명: {creative.designDescription}                       │    │
│  │  """                                                         │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                               │                                     │
│                               ▼                                     │
│  4️⃣ OpenCLIP 임베딩 (배치 처리)                                         │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  모델: ViT-L-14 (laion2b_s32b_b82k)                           │    │
│  │                                                              │    │
│  │  [이미지 임베딩]                                                 │    │
│  │  • PIL.Image → preprocess → model.encode_image()             │    │
│  │  • L2 정규화 → (N, 768) float32                                │    │
│  │                                                              │    │
│  │  [텍스트 임베딩]                                                │    │
│  │  • text → tokenizer → model.encode_text()                    │    │
│  │  • L2 정규화 → (N, 768) float32                               │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                               │                                     │
│                               ▼                                     │
│  5️⃣ 코사인 유사도 계산                                                   │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  • L2 정규화된 벡터는 내적 = 코사인 유사도                           │    │
│  │  • sim[i] = sum(img_vec[i] * txt_vec[i])                     │    │
│  │  • 범위: -1 ~ 1 (높을수록 이미지-텍스트 일치도 높음)                  │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

#### 핵심 클래스: `OpenCLIPSameSpaceEncoder`

```python
class OpenCLIPSameSpaceEncoder:
    """이미지와 텍스트를 동일한 임베딩 공간에 매핑"""
    
    def __init__(self, model_name: str, pretrained: str, device: str):
        # OpenCLIP 모델 및 전처리기 로드
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            model_name, pretrained=pretrained
        )
        self.tokenizer = open_clip.get_tokenizer(model_name)
    
    def encode_images_batch(self, images: List[PIL.Image]) -> np.ndarray:
        """배치 이미지 임베딩 (L2 정규화 포함)"""
        ...
    
    def encode_texts_batch(self, texts: List[str]) -> np.ndarray:
        """배치 텍스트 임베딩 (L2 정규화 포함)"""
        ...
```

#### 입력
- `2000_json/` 디렉토리의 JSON 파일들
  - 각 JSON 파일에는 디자인 정보와 이미지 URL이 포함

#### 출력

**1. `openclip_metadata.jsonl`**
- 각 레코드의 메타데이터를 JSON Lines 형식으로 저장
- 포함 필드:
  | 필드 | 타입 | 설명 |
  |------|------|------|
  | `id` | string | 문서 고유 ID (`{design_id}::{image_id}` 형식) |
  | `document` | string | 생성된 텍스트 문서 |
  | `metadata` | object | 원본 메타데이터 (출원번호, 등록번호, 이미지 경로 등) |
  | `image_text_cosine` | float | 이미지-텍스트 간 코사인 유사도 (-1 ~ 1) |

**2. `openclip_embeddings.npz`**
- NumPy 압축 형식으로 임베딩 벡터 저장
- 포함 배열:
  | 배열명 | Shape | dtype | 설명 |
  |--------|-------|-------|------|
  | `ids` | (N,) | str | 문서 ID 배열 |
  | `image_embeddings` | (N, 768) | float32 | L2 정규화된 이미지 임베딩 |
  | `text_embeddings` | (N, 768) | float32 | L2 정규화된 텍스트 임베딩 |
  | `image_text_cosine` | (N,) | float32 | 코사인 유사도 배열 |

#### 사용 모델

| 항목 | 값 | 설명 |
|------|-----|------|
| **모델명** | `ViT-L-14` | Vision Transformer Large, 14x14 패치 |
| **Pretrained** | `laion2b_s32b_b82k` | LAION-2B 데이터셋 학습 가중치 |
| **임베딩 차원** | 768 | 이미지/텍스트 동일 공간 |
| **정규화** | L2 Normalize | 코사인 유사도 계산 최적화 |

---

### 2단계: 데이터 분리 (문서/메타데이터)

**실행 파일**: `data/Split_jsonl.py`

#### 처리 과정

```
┌─────────────────────────────────────────────────────────────────────┐
│                       데이터 분리 파이프라인                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1️⃣ JSONL 라인별 파싱                                                  │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  • 각 라인을 JSON으로 파싱                                       │    │
│  │  • 파싱 실패 시 경고 로깅 후 스킵                                  │    │
│  │  • 빈 라인 무시                                                │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                               │                                     │
│                               ▼                                     │
│  2️⃣ JSONL ID 추출 또는 자동 생성                                         │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  우선순위: id → image_id → doc_id → design_id                 │    │
│  │  metadata 내부에서도 동일 순위로 검색                              │    │
│  │  없으면: "auto_{line_num}_{uuid8자리}" 자동 생성                 │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                               │                                     │
│                               ▼                                     │
│  3️⃣ document/metadata 분리 (split_one_record 함수)                     │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │  doc_row = {                                                 │    │
│  │      "id": rid,                                              │    │
│  │      "document": 원본의 document 필드                           │    │
│  │  }                                                           │    │
│  │                                                              │    │
│  │  meta_row = {                                                │    │
│  │      "id": rid,                                              │    │
│  │      **flatten_metadata(원본의 metadata)                       │    │
│  │  }                                                           │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                               │                                     │
│                               ▼                                     │
│  4️⃣ metadata 평탄화 (_flatten_metadata 함수)                         │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  중첩된 dict를 1-depth로 변환                                   │    │
│  │  예: {"a": {"b": 1}} → {"a.b": 1}                             │    │
│  │  Pandas/Parquet 저장에 최적화                                  │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

#### 핵심 함수

```python
def _flatten_metadata(meta: Dict, prefix: str = "") -> Dict:
    """metadata를 1-depth 컬럼으로 평탄화 (Pandas 친화)"""
    out = {}
    for k, v in meta.items():
        kk = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(_flatten_metadata(v, kk))
        else:
            out[kk] = v
    return out

def split_one_record(rec: Dict, line_num: int) -> Tuple:
    """단일 레코드를 document, metadata로 분리"""
    rid, id_generated = _pick_id(rec, line_num)
    
    doc_row = {"id": rid, "document": rec.get("document")}
    meta_row = {"id": rid, **_flatten_metadata(rec.get("metadata", {}))}
    
    return doc_row, meta_row, id_generated
```

#### 입력
- `openclip_metadata.jsonl` (1단계에서 생성된 파일)

#### 출력

**1. `documents.jsonl`**
- 디자인 문서 정보만 추출
- 포함 필드:
  | 필드 | 타입 | 설명 |
  |------|------|------|
  | `id` | string | 문서 고유 ID |
  | `document` | string | 텍스트 문서 내용 |

**2. `metadata.parquet`**
- 메타데이터를 Parquet 형식으로 저장
- Apache Arrow 컬럼 기반 포맷으로 빠른 분석 쿼리 지원
- 평탄화된 컬럼 구조 (예: `metadata.design_id` → `design_id`)

**3. `metadata.csv`** (선택적)
- 메타데이터를 CSV 형식으로 저장
- UTF-8-sig 인코딩 (Excel 한글 호환)

#### 진행 상황 추적 (ProgressTracker)

```
=== Processing Summary ===
Total lines processed : 1,234 (처리된 총 JSONL 라인 수)
  - Documents         : 1,234 (document 필드가 있는 레코드 수)
  - Metadata          : 1,234 (metadata 필드가 있는 레코드 수)
  - Embeddings        : 0 (embedding 필드가 있는 레코드 수)
--------------------------------------------------
Auto-generated IDs    : 0
Parse errors (skipped): 0 (JSON 파싱 실패로 스킵된 라인 수)
Invalid embeddings    : 0 (임베딩 변환 실패 레코드 수)
===================================================
```

---


### 디렉토리 구조

```
data/
├── 2000_raw_data/                # [0-1단계] 원본 데이터
│   └── 2000.xlsx                 # 출원번호 목록 (수동 작성)
│
├── 2000_xml/                     # [0-2단계] KIPRIS OpenAPI 응답
│   ├── 3020000000039.xml         # 출원번호당 1개 XML
│   ├── 3020000000414.xml
│   └── ... (464 파일)
│
├── 2000_json/                    # [0-3단계] XML → JSON 변환
│   ├── 3020000000039-01.json     # 출원번호-이미지번호.json
│   ├── 3020000000039-02.json
│   ├── 3020000000039-03.json
│   └── ... (3,324 파일)
│
├── img/                          # [1단계] 다운로드된 이미지
│   ├── 3020000000039-09-01__3020000000039-01.jpg
│   └── ...
│
├── openclip_metadata.jsonl       # [1단계] 메타데이터 + 문서
├── openclip_embeddings.npz       # [1단계] 임베딩 벡터
│
├── documents.jsonl               # [2단계] 분리된 문서
├── metadata.parquet              # [2단계] 분리된 메타데이터
│
├── 2000_xml_to_json.py           # [0-3단계] XML→JSON 변환 스크립트
├── openclip_vector_similarity_v1.py  # [1단계] 임베딩 생성 스크립트
└── Split_jsonl.py                    # [2단계] 데이터 분리 스크립트
```

### 데이터 변환 흐름 요약

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  2000.xlsx      │     │  *.xml          │     │  *.json         │
│  (출원번호 목록)    │ ──▶ │  (464 파일)    │ ──▶  │  (3,324 파일)     │
│                 │     │  출원번호당 1개    │     │  이미지당 1개      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
    수동 작성              KIPRIS API 호출         2000_xml_to_json.py
```

---

## 실행 방법

### 환경 설정

```bash
# 가상환경 생성 및 활성화
python -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# 의존성 설치
pip install open_clip_torch torch torchvision numpy pandas pyarrow Pillow requests tqdm
```

---

### 0-3단계: XML → JSON 변환

**실행 파일**: `2000_xml_to_json.py`

이 단계는 KIPRIS OpenAPI로부터 받은 XML 파일을 이미지별 JSON 파일로 분리합니다.

```bash
# 기본 실행
python 2000_xml_to_json.py

# 또는 경로 지정
python 2000_xml_to_json.py \
  --input ./data/2000_xml \
  --output ./data/2000_json
```

#### CLI 옵션

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--input`, `-i` | `./2000_xml` | XML 파일 경로 또는 XML 폴더 경로 |
| `--output`, `-o` | `./2000_json` | 출력 JSON 폴더 |

#### 예상 출력

```
✅ 3,324개 JSON 생성 완료
 - ./2000_json/3020000000039-01.json
 - ./2000_json/3020000000039-02.json
 - ./2000_json/3020000000039-03.json
 - ./2000_json/3020000000414-01.json
 - ./2000_json/3020000000414-02.json
 ...
```

#### 변환 로직 설명

`2000_xml_to_json.py`의 핵심 함수:

```python
def convert_one_xml(xml_path: Path) -> list[dict]:
    """
    XML 1개 → JSON 레코드 N개 반환
    (이미지 1장당 JSON 1개)
    """
    # 1. XML 파싱
    tree = ET.parse(xml_path)
    root = tree.getroot()
    
    # 2. 공통 정보 추출
    application_number = text_of(root, ".//applicationNumber")
    article_name = text_of(root, ".//articleName")
    
    # 3. 이미지별 분리
    image_paths = root.findall(".//imagePath")
    
    # 4. 각 이미지마다 독립 JSON 생성
    for idx, img_node in enumerate(image_paths, 1):
        image_doc = {
            "design_id": f"{application_number}-09-01",
            "applicationNumber": application_number,
            "meta": {"articleName": article_name, ...},
            "image": {
                "image_id": f"{application_number}-{idx:02d}",
                "imagePath": text_of(img_node, "./largePath"),
                ...
            }
        }
        # 저장: {application_number}-{idx:02d}.json
```

---

### 1단계: OpenCLIP 임베딩 생성

```bash
cd data

# 기본 실행 (GPU/MPS 자동 감지)
python openclip_vector_similarity_v1.py \
  --input_dir ./2000_json \
  --output_dir .

# 상세 옵션 지정
python openclip_vector_similarity_v1.py \
  --input_dir ./2000_json \
  --output_dir . \
  --model_name ViT-L-14 \
  --pretrained laion2b_s32b_b82k \
  --batch_size 32 \
  --device cuda
```

#### CLI 옵션

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--input_dir` | `./2000_json` | JSON 파일이 있는 디렉토리 |
| `--output_dir` | `.` | 결과 파일 저장 디렉토리 |
| `--model_name` | `ViT-L-14` | OpenCLIP 모델명 |
| `--pretrained` | `laion2b_s32b_b82k` | Pretrained 가중치 |
| `--batch_size` | `32` | 배치 크기 (VRAM에 따라 조정) |
| `--device` | 자동 감지 | `mps`, `cuda`, `cpu` |
| `--no_download` | False | 이미지 다운로드 스킵 |
| `--build_chroma` | False | ChromaDB 빌드 여부 |
| `--collection` | `openclip_same_space` | ChromaDB 컬렉션명 |

#### 예상 출력

```
📂 Input: ./2000_json
📂 Output: .
🔧 Model: ViT-L-14 / laion2b_s32b_b82k
🔧 Batch size: 32
🔧 Device: mps
Loading JSONs: 100%|██████████| 3324/3324 [00:13<00:00, 246.80it/s]
📄 로드된 레코드: 3324개
총 3324개 레코드 임베딩 시작 (batch_size=32)
Embedding batches: 100%|██████████| 104/104 [06:00<00:00,  3.47s/it]

✅ 완료
- 임베딩된 레코드: 3324개
- output: .
- metadata: ./openclip_metadata.jsonl
- embeddings: ./openclip_embeddings.npz
```

---

### 2단계: 데이터 분리

```bash
# 기본 실행
python Split_jsonl.py \
  --in_jsonl ./openclip_metadata.jsonl \
  --out_dir .

# CSV 출력 포함
python Split_jsonl.py \
  --in_jsonl ./openclip_metadata.jsonl \
  --out_dir . \
  --save_csv \
  --log_interval 1000 \
  --verbose
```

#### CLI 옵션

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `--in_jsonl` | (필수) | 입력 JSONL 파일 경로 |
| `--out_dir` | (필수) | 출력 디렉토리 |
| `--save_csv` | False | metadata를 CSV로도 저장 |
| `--log_interval` | `10000` | 진행 상황 로깅 간격 |
| `--verbose` | False | DEBUG 레벨 로깅 |

#### 예상 출력

```
2026-02-03 10:00:00 [INFO] Starting processing: ./openclip_metadata.jsonl
2026-02-03 10:00:00 [INFO] Output directory: .
2026-02-03 10:00:01 [INFO] Progress: 3,324 lines processed | docs: 3,324, meta: 3,324, emb: 0
2026-02-03 10:00:02 [INFO] Saved metadata to: ./metadata.parquet
2026-02-03 10:00:02 [INFO] Saved metadata CSV to: ./metadata.csv

==================================================
Processing Summary
==================================================
Total lines processed : 3,324
  - Documents         : 3,324
  - Metadata          : 3,324
  - Embeddings        : 0
--------------------------------------------------
Auto-generated IDs    : 0
Parse errors (skipped): 0
Invalid embeddings    : 0
==================================================
```

---

## 데이터 형식 예시

### 원본 XML (`2000_xml/*.xml`) - KIPRIS OpenAPI 응답

```xml
<?xml version="1.0" encoding="UTF-8"?>
<response>
  <header>
    <successYN>Y</successYN>
    <resultCode>00</resultCode>
    <resultMsg>NORMAL SERVICE.</resultMsg>
  </header>
  <body>
    <item>
      <applicantInfoArray>
        <applicantInfo>
          <applicantName>문영만</applicantName>
          <applicantCountry>대한민국</applicantCountry>
        </applicantInfo>
      </applicantInfoArray>
      
      <biblioSummaryInfoArray>
        <biblioInfoArray>
          <biblioSummaryInfo>
            <applicationNumber>3020000000039</applicationNumber>
            <applicationDate>2000.01.04</applicationDate>
            <registrationNumber>3002602570000</registrationNumber>
            <articleName>포장용 병</articleName>
            <admstStat>소멸</admstStat>
          </biblioSummaryInfo>
        </biblioInfoArray>
        
        <designImageInfoArray>
          <designImageInfo>
            <imagePath>
              <imageName>000.JPG</imageName>
              <largePath>http://plus.kipris.or.kr/openapi/fileToss.jsp?arg=...</largePath>
              <number>1</number>
            </imagePath>
          </designImageInfo>
        </designImageInfoArray>
      </biblioSummaryInfoArray>
      
      <creativeSummaryInfoArray>
        <creativeSummaryInfo>
          <designSummary>&lt;P N="1"&gt;포장용 병의 형상과 모양의 결합...&lt;/P&gt;</designSummary>
        </creativeSummaryInfo>
      </creativeSummaryInfoArray>
    </item>
  </body>
</response>
```

### 파싱된 JSON (`2000_json/*.json`)

```json
{
  "design_id": "3020000000039-09-01",
  "applicationNumber": "3020000000039",
  "registrationNumber": "3002602570000",
  "publicationNumber": null,
  "status": {
    "regFg": "Y",
    "admstStat": "소멸",
    "lastDispositionDate": "2000-02-25"
  },
  "meta": {
    "articleName": "포장용 병",
    "LCCode": "09-01",
    "designNumber": "M01",
    "applicantName": "문영만",
    "agentName": null
  },
  "creative": {
    "designSummary": "<P N=\"1\">포장용 병의 형상과 모양의 결합을 의장 창작 내용의 요점으로 함.</P>",
    "designDescription": "<P N=\"1\">1. 재질은 점토임. </P>"
  },
  "image": {
    "image_id": "3020000000039-01",
    "imageName": "000.JPG",
    "imagePath": "http://plus.kipris.or.kr/openapi/fileToss.jsp?arg=..."
  }
}
```

### openclip_metadata.jsonl

```json
{
  "id": "3020000000039-09-01::3020000000039-01",
  "document": "제품명: 포장용 병\nLocarno: 09-01\n출원인: 문영만\n요점: 포장용 병의 형상과 모양의 결합을 의장 창작 내용의 요점으로 함.\n설명: 1. 재질은 점토임.",
  "metadata": {
    "design_id": "3020000000039-09-01",
    "applicationNumber": "3020000000039",
    "registrationNumber": "3002602570000",
    "articleName": "포장용 병",
    "LCCode": "09-01",
    "image_id": "3020000000039-01",
    "image_url": "http://plus.kipris.or.kr/openapi/...",
    "image_local_path": "img/3020000000039-09-01__3020000000039-01.jpg",
    "source_json": "2000_json/3020000000039-01.json",
    "modality": "image+text"
  },
  "image_text_cosine": 0.2847
}
```

### openclip_embeddings.npz

```python
import numpy as np

# NPZ 파일 로드
data = np.load("openclip_embeddings.npz")
print(data.files)
# ['ids', 'image_embeddings', 'text_embeddings', 'image_text_cosine']

# 각 배열 확인
ids = data['ids']                    # shape: (N,), dtype: <U...
image_emb = data['image_embeddings'] # shape: (N, 768), dtype: float32
text_emb = data['text_embeddings']   # shape: (N, 768), dtype: float32
cosine_sim = data['image_text_cosine'] # shape: (N,), dtype: float32

print(f"레코드 수: {len(ids)}")
print(f"이미지 임베딩: {image_emb.shape}")
print(f"텍스트 임베딩: {text_emb.shape}")
print(f"유사도 범위: {cosine_sim.min():.4f} ~ {cosine_sim.max():.4f}")

# 특정 ID의 임베딩 조회
target_id = "3020000000039-09-01::3020000000039-01"
idx = np.where(ids == target_id)[0][0]
print(f"임베딩 벡터 (처음 5개): {image_emb[idx][:5]}")
```

### documents.jsonl

```json
{
  "id": "3020000000039-09-01::3020000000039-01",
  "document": "제품명: 포장용 병\nLocarno: 09-01\n출원인: 문영만\n요점: 포장용 병의 형상과 모양의 결합을 의장 창작 내용의 요점으로 함.\n설명: 1. 재질은 점토임."
}
```

### metadata.parquet (스키마)

```python
import pandas as pd

df = pd.read_parquet("metadata.parquet")
print(df.columns.tolist())
# ['id', 'design_id', 'applicationNumber', 'registrationNumber', 
#  'articleName', 'LCCode', 'image_id', 'image_url', 
#  'image_local_path', 'source_json', 'modality']

print(df.head())
```

---

## 문제 해결

### CUDA/MPS 메모리 부족

```bash
# 증상: RuntimeError: CUDA out of memory / MPS backend out of memory

# 해결 1: 배치 크기 줄이기
python openclip_vector_similarity_v1.py --batch_size 16

# 해결 2: CPU 모드로 실행 (느리지만 안정적)
python openclip_vector_similarity_v1.py --device cpu
```

### 이미지 다운로드 실패

```bash
# 증상: [WARN] 이미지 다운로드 실패: http://... -> Connection timed out

# 해결 1: 네트워크 연결 확인 후 재실행
python openclip_vector_similarity_v1.py

# 해결 2: 이미 다운로드한 이미지가 있으면 스킵
python openclip_vector_similarity_v1.py --no_download

# 해결 3: 타임아웃 시간 늘리기 (코드 수정 필요)
# download_image() 함수의 timeout 파라미터 조정
```

### JSON 파일 로드 오류

```bash
# 증상: JSON parse error - Expecting ',' delimiter

# 해결 1: JSON 파일 유효성 검사
python -m json.tool 2000_json/problem_file.json

# 해결 2: 인코딩 확인 (UTF-8 필수)
file -I 2000_json/problem_file.json
```

### 임베딩 벡터 불일치

```bash
# 증상: NPZ 파일의 ids와 embeddings shape가 일치하지 않음

# 해결: 임베딩을 처음부터 다시 생성
rm openclip_embeddings.npz openclip_metadata.jsonl
python openclip_vector_similarity_v1.py
```

### Parquet 저장 오류

```bash
# 증상: pyarrow.lib.ArrowInvalid: ('cannot mix list and non-list')

# 원인: metadata의 중첩 구조가 불규칙함
# 해결: _flatten_metadata 함수가 모든 중첩을 평탄화하므로 자동 해결됨
# 만약 여전히 오류 발생 시 verbose 모드로 문제 라인 확인
python Split_jsonl.py --in_jsonl input.jsonl --out_dir . --verbose
```

---

## 요구사항

### Python 패키지

```txt
# 필수 패키지
open_clip_torch>=2.20.0
torch>=2.0.0
torchvision>=0.15.0
numpy>=1.24.0
pandas>=2.0.0
pyarrow>=12.0.0
Pillow>=9.0.0
requests>=2.28.0
tqdm>=4.65.0

# 선택적 (ChromaDB 빌드 시)
chromadb>=0.4.0
```

### 시스템 요구사항

| 항목 | 최소 사양 | 권장 사양 |
|------|----------|----------|
| **Python** | 3.8+ | 3.10+ |
| **RAM** | 8GB | 16GB+ |
| **GPU VRAM** | 4GB | 8GB+ |
| **디스크** | 5GB | 20GB+ |
| **OS** | Linux, macOS, Windows | macOS (MPS), Linux (CUDA) |

### 디바이스 지원

| 디바이스 | 지원 여부 | 속도 (상대적) | 설정 |
|----------|----------|--------------|------|
| NVIDIA CUDA | ✅ | ⚡⚡⚡ 가장 빠름 | `--device cuda` |
| Apple MPS | ✅ | ⚡⚡ 빠름 | `--device mps` (자동 감지) |
| CPU | ✅ | ⚡ 느림 | `--device cpu` |

---

## 참고 문서

- [OpenCLIP GitHub](https://github.com/mlfoundations/open_clip)
- [LAION-2B 데이터셋](https://laion.ai/blog/laion-5b/)
- [프로젝트 메인 README](./README.md)
- [종합 흐름 문서](./종합흐름.md)
