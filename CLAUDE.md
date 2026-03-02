# FTOGuard 프로젝트 - Claude 작업 가이드

## 프로젝트 개요
FTO(Freedom to Operate) 특허·디자인 침해 리스크 판단 AI 에이전트
- 특허 FTO 분석: RAG(특허 검색) + vLLM(Qwen2.5-14B) → 침해 분석
- 디자인 분석: ChromaDB 이미지 RAG (CLIP 임베딩)

---

## AWS RDS 정보 (2026-02-26 정리 완료)

| 항목 | 값 |
|------|-----|
| 엔드포인트 | `fto-db.c34w48m8sov6.ap-northeast-2.rds.amazonaws.com` |
| 포트 | 3306 |
| DB명 | `fto` |
| 유저 | `admin` |
| 비밀번호 | `rmdak2020` |
| 엔진 | MySQL 8.4 |

### RDS 테이블 구조

```
patents (4만건)           ← 특허 메타데이터 + 청구항 텍스트
├── apply_num (PK)        ← 출원번호
├── invention_title       ← 발명명
├── claim_pub             ← 공개 청구항 텍스트
├── claim_regit           ← 등록 청구항 텍스트
└── chunk_ids             ← ChromaDB 청크 ID 목록

claim_keywords (1000만건) ← Pre-filter용 키워드
├── patent_id             ← 출원번호 (patents.apply_num 참조)
├── chunk_id              ← 청구항 청크 ID
└── keyword               ← 키워드

claim_components (26만건) ← sLLM용 구성요소
├── patent_id             ← 출원번호
├── chunk_id              ← 청구항 청크 ID (UNIQUE)
├── components            ← 추출된 구성요소 목록
└── note                  ← 참조한 종속항 번호

users / chats / messages / analyses ← 서비스 테이블

⚠️ 삭제 필요 (런팟에서 실행):
design_patents, image_matches ← 이미지는 ChromaDB만 사용
```

### RDS 정리 명령어 (런팟에서 실행)
```bash
mysql -h fto-db.c34w48m8sov6.ap-northeast-2.rds.amazonaws.com -u admin -prmdak2020 fto -e "
SET FOREIGN_KEY_CHECKS=0;
DROP TABLE IF EXISTS image_matches;
DROP TABLE IF EXISTS design_patents;
SET FOREIGN_KEY_CHECKS=1;
SHOW TABLES;
"
```

### 데이터 연결 관계 (논리적 참조)
```
patents.apply_num ←── claim_keywords.patent_id
                  ←── claim_components.patent_id

claim_keywords.chunk_id ←→ claim_components.chunk_id
                        ←→ ChromaDB 벡터 ID
```

---

## 이미지 분석 (디자인 특허)

**RDS 사용 안 함** - ChromaDB만 사용

```
이미지 업로드
→ ChromaDB에서 CLIP 임베딩으로 유사 이미지 검색
→ ChromaDB 메타데이터에서 image_url 가져옴
→ 결과 이미지 표시
```

ChromaDB 위치: EC2 `/data/chroma/images/`

---

## 현재 구현 상태 (2026-03-02 업데이트)

### 완료된 것
- [x] Qwen2.5-14B LoRA → 베이스 병합 (`itsbini/qwen2.5-14b-fto-merged`)
- [x] FastAPI 백엔드 (포트 8080) + 프론트엔드 정적 파일 서빙
- [x] 채팅 UI → vLLM 연결 (`/api/chat/message`)
- [x] RDS 스키마 정리 완료
- [x] RAG 파이프라인 연결 완료
- [x] **RunPod 서버리스 엔드포인트 생성 (2026-03-02)**
  - 특허 텍스트용: `qcqek25abvhk7o`
  - 디자인 이미지용: `hmh882ms5azjye`

---

## 할 일 목록 (2026-03-02 연휴 작업)

### 1. 인프라 작업

| 작업 | 상태 | 비고 |
|------|------|------|
| ChromaDB Docker화 | ⬜ | EC2 직접 설치 → Docker Compose로 변경 |
| EC2 인스턴스 유형 변경 | ⬜ | r6i.large (KURE 때문) - 멘토/강사님 확인 필요 |
| 디자인 ChromaDB Docker | ⬜ | 이미지용 ChromaDB 컨테이너 |

### 2. 백엔드 작업

| 작업 | 상태 | 비고 |
|------|------|------|
| pre-filter 키워드 RDS 교체 | ⬜ | claim_keywords 테이블 재구축 |
| component 키워드 RDS 교체 | ⬜ | claim_components 테이블 재구축 |
| RunPod 서버리스 설정 | ✅ | 14B + VL 7B 엔드포인트 완료 |
| 백엔드 → 서버리스 연결 | ⬜ | chat.py에서 RunPod API 호출로 변경 |

### 3. 프론트엔드 작업

| 작업 | 상태 | 비고 |
|------|------|------|
| patent-chat.html 대화형 흐름 | ⬜ | 원샷 분석 → 정보 수집 후 분석 |
| design-chat.html 연결 | ⬜ | VL 모델 서버리스 연동 |
| results.html PDF 보고서 | ⬜ | 실제 LLM 분석 결과 표시 |

---

## 작업 우선순위

```
1. pre-filter 키워드 RDS 교체 (RAG 검색에 필수)
2. component 키워드 RDS 교체 (구성요소 분석에 필수)
3. 백엔드 → RunPod 서버리스 연결 (테스트)
4. 디자인 ChromaDB Docker화
5. 프론트엔드 개선
```

---

## 주요 파일 구조

```
SKN20-FINAL-2TEAM/
├── FRONTEND/              # 정적 HTML/JS/CSS (FastAPI가 서빙)
│   ├── chat.html          # 특허 FTO 채팅 페이지
│   ├── design-chat.html   # 디자인 분석 페이지
│   ├── results.html       # 분석 결과 + PDF 보고서
│   └── script.js          # apiClient (baseURL="/api")
├── backend/
│   ├── app/
│   │   ├── main.py        # FastAPI 앱 (포트 8080)
│   │   └── routers/
│   │       └── chat.py    # /api/chat/message → vLLM 호출
│   └── .env               # DB, vLLM 설정
├── rag/
│   ├── search/
│   │   └── pipeline.py    # search() + analyze() 함수
│   ├── generate.py        # vLLM 호출로 FTO 분석 생성
│   └── config.py          # 설정 파일
├── sql/
│   └── fto_schema.sql     # RDS 스키마 (현재 구조 반영)
└── CLAUDE.md              # 이 파일
```

---

## 포트 구성

| 포트 | 용도 |
|------|------|
| 8000 | vLLM 서버 (Qwen2.5-14B) |
| 8080 | FastAPI 백엔드 + 프론트엔드 |
| 8888 | JupyterLab |

---

## 모델 정보

### 특허 FTO 분석
- **모델**: `itsbini/qwen2.5-14b-fto-merged` (HuggingFace)
- **베이스**: Qwen/Qwen2.5-14B-Instruct
- **파인튜닝**: LoRA → 병합 완료
- **크기**: ~29.5GB (float16)
- **위치**: `/workspace/qwen2.5-14b-fto-merged`

### 디자인 분석 (VLM)
- **모델**: `Qwen/Qwen2.5-VL-7B-Instruct` (베이스 모델, 파인튜닝 없음)
- **크기**: ~15GB (bfloat16)
- **위치**: `/workspace/Qwen2.5-VL-7B-Instruct`
- **용도**: 이미지 분석 + 텍스트 생성 (Vision-Language)

### GPU: A100 80GB
- 14B만 → ~30GB 사용
- VL 7B만 → ~18GB 사용
- 동시 서빙 시 포트 분리 필요 (8000, 8001)

## 시스템 프롬프트 (변경 금지)
`backend/app/routers/chat.py`의 `SYSTEM_PROMPT`와
`rag/generate.py`의 `SYSTEM_PROMPT`는 학습 데이터와 동일한 형식이므로 수정 시 성능 저하 가능.

---

## RunPod 서버리스 엔드포인트 (2026-03-02 설정 완료)

### 엔드포인트 정보

| 용도 | 모델 | Endpoint ID | API URL |
|------|------|-------------|---------|
| 특허 텍스트 분석 | `itsbini/qwen2.5-14b-fto-merged` | `qcqek25abvhk7o` | `https://api.runpod.ai/v2/qcqek25abvhk7o/run` |
| 디자인 이미지 분석 | `Qwen/Qwen2.5-VL-7B-Instruct` | `hmh882ms5azjye` | `https://api.runpod.ai/v2/hmh882ms5azjye/run` |

### 서버리스 설정

| 설정 | 값 |
|------|-----|
| Max Workers | 1 |
| Active Workers | 0 (요청 없으면 비용 0) |
| GPU | A100 80GB |
| Idle Timeout | 5 sec |
| Execution Timeout | 600 sec |
| FlashBoot | 활성화 (Cold start 단축) |

### API Key

```
RUNPOD_API_KEY=<여기에 API Key 입력>
```

### 사용 예시 (cURL)

```bash
# 특허 텍스트 분석
curl -X POST https://api.runpod.ai/v2/qcqek25abvhk7o/run \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer YOUR_RUNPOD_API_KEY' \
  -d '{"input":{"prompt":"Your prompt here"}}'

# 디자인 이미지 분석
curl -X POST https://api.runpod.ai/v2/hmh882ms5azjye/run \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer YOUR_RUNPOD_API_KEY' \
  -d '{"input":{"prompt":"Your prompt here"}}'
```

### 비용 구조

- **요청 없을 때**: $0 (Active Workers = 0)
- **요청 처리 중**: A100 80GB 기준 ~$0.00111/sec (~$4/hour)
- **Cold Start**: FlashBoot로 ~2초 (첫 요청 시 모델 로딩 필요)
