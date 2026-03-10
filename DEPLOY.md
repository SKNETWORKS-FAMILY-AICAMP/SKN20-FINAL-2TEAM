# FTOGuard 배포 아키텍처 & 히스토리

> 최종 업데이트: 2026-03-10
> 프로젝트 전체 인프라 구조, 설계 결정, 트러블슈팅 기록
> 팀원용 재배포 가이드는 DEPLOY_HOWTO.md 참고

---

## 1. 전체 아키텍처

```
EC2 r6i.large (16GB RAM) - Docker Compose
+------------------------------------------------------+
|                                                      |
|  fto-backend (:8080)   chromadb-patent   chromadb-   |
|  FastAPI+RAG+Design    :8000(내부)       design      |
|  +Frontend             volume:/data     :8000(내부)  |
|                                         volume:/data |
+----------+-------------------------------------------+
           |
     +-----v------+     +------------------+
     |  AWS RDS   |     | RunPod Serverless |
     |  MySQL 8.4 |     | Qwen2.5-14B(특허)|
     +------------+     | Qwen2.5-VL-7B    |
                        | (디자인)          |
                        +------------------+
```

---

## 2. Docker 컨테이너 구성

| 컨테이너 | 이미지 | 포트 | 역할 |
|----------|--------|------|------|
| fto-backend | 자체 빌드 (Dockerfile) | 8080 (외부) | FastAPI + RAG + Design + Frontend |
| chromadb-patent | chromadb/chroma:latest | 8000 (내부) | 특허 벡터DB (297,061 chunks, KURE 1024차원) |
| chromadb-design | chromadb/chroma:latest | 8000 (내부) | 디자인 벡터DB (21,801 items, CLIP 512차원) |

### backend 컨테이너 내부 구조

```
backend 컨테이너 (:8080)
+-- FastAPI (backend/)           -> API 서버
+-- RAG 코드 (rag/)              -> 특허 검색
+-- 디자인 챗봇 (design/src/)    -> 디자인 분석
+-- 프론트엔드 (FRONTEND/)       -> 정적파일 서빙
|
+-- [메모리 상주]
    +-- KURE-v1 임베딩 모델 (~3GB)
    +-- CLIP ViT-B/32 (~340MB, 첫 요청 시 다운로드)
    +-- BM25 인덱스 (~500MB)
        +-- postings.pkl (145MB)
        +-- idf.pkl (17MB)
        +-- doc_len.pkl (1.9MB)
        +-- doc_map.pkl (8.5MB)
        +-- meta.json
```

### 왜 Docker인가?

| 상황 | EC2 직접 설치 | Docker |
|------|-------------|--------|
| 설치 | pip install + 버전 충돌 | docker compose up 한 줄 |
| 인덱스 깨지면 | SSH -> 디버깅 -> 재설치 | docker compose restart |
| 서버 옮길 때 | 처음부터 세팅 | 폴더 복사 + docker compose up |
| 버전 관리 | pip 버전 꼬임 | 이미지 태그 고정 |

### 왜 ChromaDB 2개 분리?

```
chromadb-patent  (컨테이너 1)  ->  특허 벡터 (3.1GB)
chromadb-design  (컨테이너 2)  ->  디자인 벡터 (75MB)
```

하나 죽어도 나머지 정상. 데이터 교체 시 해당 컨테이너만 재시작. 로그 분리로 디버깅 용이.

---

## 3. 검색 흐름

### 특허 검색 (사용자가 "히알루론산 미백 화장품" 검색 시)

```
[1] 키워드 추출 (backend 내부)
    "히알루론산 미백 화장품" -> ["히알루론산", "미백", "화장품"]

[2] 사전필터링 (RDS claim_keywords)
    78,716 특허 -> ~1,000개 후보 chunk_id로 축소

[3-A] BM25 검색 (backend 내부, 네트워크 안 탐)
    pkl 파일에서 직접 계산 -> chunk별 BM25 점수

[3-B] Dense 검색 (backend -> ChromaDB, HTTP)
    KURE로 쿼리 임베딩 -> ChromaDB에 cosine 검색

[4] RRF 합산 -> 최종 순위

[5] Patent Collapse -> 특허당 1건 합침 -> 최종 결과
```

### 디자인 분석 (LangGraph 2단계)

```
[1단계] 이미지 -> CLIP 임베딩 -> ChromaDB 유사 검색 -> 10개 반환 (interrupt)
[2단계] 사용자 선택 -> VLM 상세 비교 (RunPod) -> FTO 리포트 생성
```

### BM25를 왜 별도 컨테이너로 안 분리?

| | BM25 (앱 내장) | Elasticsearch |
|---|---|---|
| 데이터 규모 | 78K 문서, 173MB | 수백만~수천만 |
| 검색 속도 | 메모리 직접 접근 (즉시) | 네트워크 왕복 |
| RAM | ~500MB | ES만 2~4GB |

78K 규모에서 Elasticsearch는 오버엔지니어링.

---

## 4. 메모리 사용량

```
KURE-v1 임베딩 모델:     ~3 GB
CLIP ViT-B/32:           ~340 MB
BM25 인덱스:             ~500 MB
LangGraph + 챗봇:        ~300 MB
FastAPI + RAG + OS:      ~900 MB
ChromaDB x2:             ~300 MB
-----------------------------------------
정상: ~5.4 GB / 피크: ~7-8 GB
```

| 인스턴스 | RAM | 판단 |
|----------|-----|------|
| t3.medium (4GB) | 4 GB | 부족 |
| t3.large (8GB) | 8 GB | 가능하지만 여유 없음 |
| r6i.large (16GB) | 16 GB | 안전 (현재 사용) |

KURE를 RunPod에 올리면? 검색마다 1~3초 느려지고 cold start 리스크. r6i.large 쓸 수 있으면 EC2에서 돌리는 게 낫다.

---

## 5. RunPod Serverless

### 특허 FTO (LoRA 동적 로딩)

| 항목 | 값 |
|------|-----|
| Base 모델 | Qwen/Qwen2.5-14B-Instruct |
| LoRA | itsbini/qwen2.5-14b-fto |
| GPU | A100 80GB |
| max_model_len | 4096 |
| max_tokens | 2048 |
| 정확도 | 94.3% |

### 디자인 VLM

| 항목 | 값 |
|------|-----|
| 모델 | Qwen/Qwen2.5-VL-7B-Instruct |
| GPU | RTX 4090 24GB 이상 |
| max_model_len | 8192 |
| Timeout | 300초 (서버리스 Cold Start 고려) |

### Cold Start

| Active Workers | 응답 시간 | 비용 |
|----------------|----------|------|
| 0 | 30초~2분 | 쓴 만큼 |
| 1 | 즉시 (~3초) | ~$0.5/hr |

---

## 6. 데이터 (git 미포함, 수동 업로드)

```
data/
+-- chroma-patent/     특허 벡터DB (~1.9GB, KURE 1024차원, 297,061 chunks)
+-- chroma-design/     디자인 벡터DB (~75MB, CLIP 512차원, 21,801 items)
+-- bm25_index/        BM25 인덱스 (~173MB, pkl 4개 + meta.json)
```

KURE 임베딩 모델로 78,716건 특허를 벡터화한 결과물. Docker가 자동 생성 안 함.

---

## 7. RDS 현황

| 테이블 | 건수 |
|--------|------|
| patents | 78,716 |
| claim_components | 263,396 |
| users | 11 |
| chats / messages / analyses | 소량 |

---

## 8. 주요 파일

| 파일 | 역할 |
|------|------|
| Dockerfile | 통합 이미지 (backend+rag+design+frontend) |
| docker-compose.yml | 3개 서비스 정의 |
| .dockerignore | 빌드 제외 파일 |
| .env.ec2 | EC2 환경변수 (git 미포함) |
| docker-compose.chromadb.yml | 로컬 ChromaDB 테스트용 |
| runpod/handler.py | RunPod 커스텀 핸들러 |
| runpod/Dockerfile | RunPod용 이미지 |

---

## 9. 현재 접속 정보

| 서비스 | 주소 |
|--------|------|
| 웹사이트 | http://ftoguard.kro.kr |
| EC2 직접 | http://3.38.246.215:8080 |
| EC2 SSH | ssh -i fto-key.pem ubuntu@3.38.246.215 |
| RDS MySQL | fto-db.c34w48m8sov6.ap-northeast-2.rds.amazonaws.com:3306 |

---

## 10. 트러블슈팅 히스토리

| 문제 | 원인 | 해결 |
|------|------|------|
| ModuleNotFoundError: app | PYTHONPATH 미설정 | Dockerfile에 ENV PYTHONPATH 추가 |
| SSH Permission denied (ec2-user) | Ubuntu AMI | ubuntu@ 로 접속 |
| No space left on device | EBS 30GB 부족 | 50GB로 확장 (growpart + resize2fs) |
| docker compose unknown command | docker-compose-v2 미설치 | sudo apt-get install -y docker-compose-v2 |
| ChromaDB 0건 | volume 마운트 경로 오류 | /chroma/chroma -> /data 로 수정 |
| libGL.so.1 not found | opencv 시스템 라이브러리 | Dockerfile에 libgl1 libglib2.0-0 추가 |
| Collection [design] not exist | PersistentClient (Docker에선 별도 컨테이너) | HttpClient 분기 (CHROMA_IMAGE_HOST 환경변수) |
| 빌드 0초 끝남 | Docker 캐시 | --no-cache 플래그 |
| scp 경로 에러 | PowerShell에서 ~ 미지원 | /home/ubuntu/... 절대경로 사용 |
| 분석 느림 (30초~2분) | RunPod Serverless Cold Start | EC2 문제 아님, Active Workers=1로 해결 |

---

## 11. 비용 참고

| 항목 | 11일 기준 | 월 기준 |
|------|----------|---------|
| EC2 r6i.large | ~57,000원 | ~160,000원 |
| RDS db.t3.micro | ~7,000원 | ~20,000원 |
| EBS 50GB | ~2,000원 | ~5,000원 |
| RunPod (Active=0) | ~$30-50 | 사용량 |
| RunPod (Active=1) | ~$130 | ~$360 |
