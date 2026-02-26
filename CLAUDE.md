# FTOGuard 프로젝트 - Claude 작업 가이드

## 프로젝트 개요
FTO(Freedom to Operate) 특허·디자인 침해 리스크 판단 AI 에이전트
- 특허 FTO 분석: RAG(특허 검색) + vLLM(Qwen2.5-14B) → 침해 분석
- 디자인 분석: ChromaDB 이미지 RAG (CLIP 임베딩)

---

## 새 런팟 시작 시 작업 순서

### 1. 환경 설정

```bash
# 패키지 설치
pip install vllm openai fastapi uvicorn sqlalchemy pydantic-settings \
    python-jose[cryptography] pymysql python-multipart aiofiles chromadb

# .env 생성 (RDS 연결)
cat > /root/SKN20-FINAL-2TEAM/backend/.env << 'EOF'
DATABASE_URL=mysql+pymysql://admin:rmdak2020@fto-db.c34w48m8sov6.ap-northeast-2.rds.amazonaws.com:3306/fto
SECRET_KEY=demo-secret-key-2026
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
CORS_ORIGINS=["*"]
VLLM_BASE_URL=http://localhost:8000/v1
VLLM_MODEL=/workspace/qwen2.5-14b-fto-merged
DEV_BYPASS_AUTH=true
EOF
```

### 2. vLLM 서버 실행

```bash
# 병합된 모델이 /workspace에 있으면 바로 실행
vllm serve /workspace/qwen2.5-14b-fto-merged \
    --host 0.0.0.0 --port 8000 --dtype float16 > /workspace/vllm.log 2>&1 &

# /workspace에 없으면 HuggingFace에서 다운로드 후 실행
# (모델: itsbini/qwen2.5-14b-fto-merged, 약 29.5GB)
export HF_HOME=/workspace/hf_cache
vllm serve itsbini/qwen2.5-14b-fto-merged \
    --host 0.0.0.0 --port 8000 --dtype float16 > /workspace/vllm.log 2>&1 &

# 서버 준비 확인 (2~3분 소요)
tail -f /workspace/vllm.log
# "Application startup complete." 메시지 확인
```

### 3. FastAPI 백엔드 실행

```bash
cd /root/SKN20-FINAL-2TEAM/backend
uvicorn app.main:app --host 0.0.0.0 --port 8080 > /workspace/backend.log 2>&1 &

# 확인
curl http://localhost:8080/health
```

### 4. 접속 방법 (SSH 터널)

```bash
# Mac 로컬 터미널에서 실행
ssh -L 8080:localhost:8080 root@<IP> -p <PORT> -i ~/.ssh/id_ed25519 -N

# 브라우저 접속
# http://localhost:8080/chat.html
```

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

## 현재 구현 상태

### 완료된 것
- [x] Qwen2.5-14B LoRA → 베이스 병합 (`itsbini/qwen2.5-14b-fto-merged`)
- [x] vLLM 서버 (포트 8000)
- [x] FastAPI 백엔드 (포트 8080) + 프론트엔드 정적 파일 서빙
- [x] 채팅 UI → vLLM 연결 (`/api/chat/message`)
- [x] RDS 스키마 정리 완료 (2026-02-26)
- [x] DEV_BYPASS_AUTH=true (데모용 인증 우회)

### 다음 작업: RAG 연결
- [ ] RAG 파이프라인 연결 (`rag/search/pipeline.py` → chat 엔드포인트)
- [ ] ChromaDB 연결 (텍스트 + 이미지)
- [ ] 결과 페이지 실제 데이터 연결 (`results.html`)
- [ ] 보고서 PDF에 실제 LLM 분석 결과 표시

---

## RAG 연결 작업

### RAG 파이프라인 흐름
```
채팅 메시지 입력
→ claim_keywords에서 keyword 매칭 (Pre-filter)
→ ChromaDB에서 chunk_id로 유사 청구항 검색 (Dense + BM25)
→ chunk_id → claim_components에서 구성요소 조회
→ patent_id → patents에서 메타데이터 조회
→ vLLM(Qwen2.5-14B)으로 침해 여부 판단
→ 결과 반환 + DB 저장
→ results.html?id=xxx 로 이동
→ PDF 보고서 다운로드
```

### 수정할 파일
1. `backend/app/routers/chat.py`
   - `send_chat_message()` → `pipeline.analyze()` 호출로 교체
2. `rag/config.py`
   - RDS 연결 설정
   - `VLLM_API_URL = "http://localhost:8000/v1"`
   - `VLLM_MODEL_NAME = "/workspace/qwen2.5-14b-fto-merged"`
3. `rag/search/pipeline.py`
   - RDS + ChromaDB 연결
4. `backend/app/routers/chat.py` + `results.html`
   - 분석 결과 DB 저장 → results 페이지 연동

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

- **모델**: `itsbini/qwen2.5-14b-fto-merged` (HuggingFace)
- **베이스**: Qwen/Qwen2.5-14B-Instruct
- **파인튜닝**: LoRA → 병합 완료
- **크기**: ~29.5GB (float16)
- **필요 VRAM**: A100 40GB 이상 권장

## 시스템 프롬프트 (변경 금지)
`backend/app/routers/chat.py`의 `SYSTEM_PROMPT`와
`rag/generate.py`의 `SYSTEM_PROMPT`는 학습 데이터와 동일한 형식이므로 수정 시 성능 저하 가능.
