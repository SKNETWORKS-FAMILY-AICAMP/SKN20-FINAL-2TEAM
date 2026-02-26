# FTOGuard 프로젝트 - Claude 작업 가이드

## 프로젝트 개요
FTO(Freedom to Operate) 특허·디자인 침해 리스크 판단 AI 에이전트
- 특허 FTO 분석: RAG(특허 검색) + vLLM(Qwen2.5-14B) → 침해 분석
- 디자인 분석: CLIP 이미지 임베딩 기반

---

## 새 런팟 시작 시 작업 순서

### 1. 환경 설정

```bash
# 패키지 설치
pip install vllm openai fastapi uvicorn sqlalchemy pydantic-settings \
    python-jose[cryptography] pymysql python-multipart aiofiles

# .env 생성
cat > /root/SKN20-FINAL-2TEAM/backend/.env << 'EOF'
DATABASE_URL=sqlite:////workspace/bini.db
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

## 현재 구현 상태

### 완료된 것
- [x] Qwen2.5-14B LoRA → 베이스 병합 (`itsbini/qwen2.5-14b-fto-merged` on HuggingFace)
- [x] vLLM 서버 (포트 8000)
- [x] FastAPI 백엔드 (포트 8080) → 프론트엔드 정적 파일 서빙 포함
- [x] 채팅 UI → vLLM 연결 (`/api/chat/message`)
- [x] 대화 히스토리 DB 저장 (SQLite)
- [x] DEV_BYPASS_AUTH=true (데모용 인증 우회)

### 미완성 (RAG 연결 후 작업 예정)
- [ ] RAG 파이프라인 연결 (`rag/search/pipeline.py` → chat 엔드포인트)
- [ ] 결과 페이지 실제 데이터 연결 (`results.html` mock → 실제 분석 결과)
- [ ] 보고서 PDF에 실제 LLM 분석 결과 표시

---

## RAG 연결 작업 (다음 세션)

### RAG 연결 시 필요한 정보
- RDS 접속 정보: host, DB명, user, password
- ChromaDB 데이터 위치 (로컬 파일 경로 or S3)

### RAG 연결 시 수정할 파일
1. `backend/app/routers/chat.py`
   - `send_chat_message()` 함수에서 vLLM 직접 호출 → `pipeline.analyze()` 호출로 교체
2. `rag/config.py`
   - `VLLM_API_URL = "http://localhost:8000/v1"` 설정
   - `VLLM_MODEL_NAME = "/workspace/qwen2.5-14b-fto-merged"` 설정
   - RDS 연결 설정
3. `backend/app/routers/chat.py` + `results.html`
   - 분석 결과 DB 저장 → results 페이지 실제 데이터 연동

### RAG 연결 흐름
```
채팅 메시지
→ pipeline.analyze(query)        # rag/search/pipeline.py
  → search(query)                # ChromaDB + SQLite/RDS 특허 검색
  → generate_fto(results, query) # vLLM으로 침해 분석
→ 결과 DB 저장
→ results.html?id=xxx 로 이동
→ PDF 보고서 다운로드
```

---

## 주요 파일 구조

```
SKN20-FINAL-2TEAM/
├── FRONTEND/           # 정적 HTML/JS/CSS (FastAPI가 서빙)
│   ├── chat.html       # 특허 FTO 채팅 페이지
│   ├── design-chat.html # 디자인 분석 페이지
│   ├── results.html    # 분석 결과 + PDF 보고서
│   └── script.js       # apiClient (baseURL="/api")
├── backend/
│   ├── app/
│   │   ├── main.py     # FastAPI 앱 (포트 8080, FRONTEND 정적 서빙)
│   │   └── routers/
│   │       └── chat.py # /api/chat/message → vLLM 호출
│   └── .env            # DB, vLLM 설정
├── SLLM_model/
│   └── inference.py    # vLLM OpenAI-compatible API 클라이언트
├── rag/
│   ├── search/
│   │   └── pipeline.py # search() + analyze() 함수
│   ├── generate.py     # vLLM/GPT 호출로 FTO 분석 생성
│   └── config.py       # VLLM_API_URL, VLLM_MODEL_NAME 설정
└── merge_upload.py     # LoRA 병합 스크립트 (HF_TOKEN 환경변수 필요)
```

---

## 포트 구성

| 포트 | 용도 |
|------|------|
| 8000 | vLLM 서버 (Qwen2.5-14B) |
| 8080 | FastAPI 백엔드 + 프론트엔드 |
| 8888 | JupyterLab |

nginx 외부 포트: 8001→8000, 8081→8080

---

## 모델 정보

- **모델**: `itsbini/qwen2.5-14b-fto-merged` (HuggingFace)
- **베이스**: Qwen/Qwen2.5-14B-Instruct
- **파인튜닝**: LoRA → 병합 완료
- **저장 위치**: `/workspace/qwen2.5-14b-fto-merged` (런팟 /workspace)
- **크기**: ~29.5GB (float16)
- **필요 VRAM**: A100 40GB 이상 권장

## 시스템 프롬프트 (변경 금지)
`backend/app/routers/chat.py`의 `SYSTEM_PROMPT`와
`rag/generate.py`의 `SYSTEM_PROMPT`는 학습 데이터와 동일한 형식이므로 수정 시 성능 저하 가능.
