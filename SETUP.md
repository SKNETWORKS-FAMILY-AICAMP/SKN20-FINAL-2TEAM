# FTOGuard 새 RunPod 환경 셋업 가이드

---

## 1. 사전 준비물 (사용자가 직접 제공해야 할 것)

| 항목 | 설명 | 어디서 가져오나 |
|------|------|----------------|
| `fto-key.pem` | EC2 SSH 접속 키 | 로컬 PC에서 업로드 → `/root/SKN20-FINAL-2TEAM/fto-key.pem` |
| EC2 IP | RAG 인덱스 데이터 복사용 | 현재: `52.78.233.64` (변경 시 확인) |
| RunPod Public IP | RDS 보안 그룹에 추가 필요 | `curl -s ifconfig.me` 로 확인 |
| AWS 콘솔 접근 | RDS 보안 그룹 인바운드 규칙 편집 | sg-0845fa884046b99f5 → MySQL 3306 → RunPod IP/32 추가 |

> **fto-key.pem은 .gitignore에 등록되어 있으므로 git에 올라가지 않음. 매번 직접 업로드 필요.**

---

## 2. 환경 설정 (순서대로 실행)

### 2-1. 프로젝트 클론 (최초 1회)
```bash
cd /root
git clone https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN20-FINAL-2TEAM.git
cd SKN20-FINAL-2TEAM
```

### 2-2. .env 파일 생성
```bash
cat > /root/SKN20-FINAL-2TEAM/.env << 'EOF'
# ── RDS MySQL ──
DATABASE_URL=mysql+pymysql://admin:rmdak2020@fto-db.c34w48m8sov6.ap-northeast-2.rds.amazonaws.com:3306/fto
MYSQL_HOST=fto-db.c34w48m8sov6.ap-northeast-2.rds.amazonaws.com
MYSQL_PORT=3306
MYSQL_USER=admin
MYSQL_PASSWORD=rmdak2020
MYSQL_DATABASE=fto

# ── ChromaDB (로컬 사용 — EC2 원격 연결 안 함) ──
# CHROMA_HOST, CHROMA_PORT 설정하지 않으면 로컬 PersistentClient 사용
# CHROMA_HOST=52.78.233.64
# CHROMA_PORT=8001
# CHROMA_IMAGE_PORT=8002

# ── vLLM 서버 ──
VLLM_BASE_URL=http://localhost:8000/v1
VLLM_MODEL=/workspace/qwen2.5-14b-fto-merged

# ── OpenAI GPT 폴백 ──
OPENAI_API_KEY=<팀 노션에서 확인>

# ── JWT 인증 ──
SECRET_KEY=demo-secret-key-2026
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# ── 서비스 설정 ──
CORS_ORIGINS=["*"]
DEV_BYPASS_AUTH=true

# ── HuggingFace ──
HF_TOKEN=<팀 노션에서 확인>
EOF
```

### 2-3. backend/.env 생성 (backend 전용)
```bash
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

### 2-4. RDS 보안 그룹 설정
```bash
# 1. RunPod IP 확인
curl -s ifconfig.me

# 2. AWS 콘솔 → EC2 → 보안 그룹 → sg-0845fa884046b99f5
#    인바운드 규칙 편집 → 규칙 추가:
#    유형: MYSQL/Aurora | 포트: 3306 | 소스: <RunPod IP>/32
#    → 규칙 저장

# 3. 연결 테스트
python3 -c "
import pymysql
conn = pymysql.connect(host='fto-db.c34w48m8sov6.ap-northeast-2.rds.amazonaws.com',
    port=3306, user='admin', password='rmdak2020', database='fto')
cur = conn.cursor(); cur.execute('SHOW TABLES')
for r in cur.fetchall(): print(r[0])
conn.close(); print('--- RDS 연결 성공 ---')
"
```

---

## 3. RAG 인덱스 데이터 복사 (EC2 → RunPod)

> **fto-key.pem을 먼저 업로드해야 이 단계 진행 가능**

```bash
# SSH 키 권한 설정
chmod 600 /root/SKN20-FINAL-2TEAM/fto-key.pem

# EC2 접속 테스트
ssh -o StrictHostKeyChecking=no -i /root/SKN20-FINAL-2TEAM/fto-key.pem ubuntu@52.78.233.64 "echo 'EC2 연결 성공'"

# rag/index/ 복사 (약 1.8GB, 3~5분 소요)
mkdir -p /root/SKN20-FINAL-2TEAM/rag/index
scp -r -i /root/SKN20-FINAL-2TEAM/fto-key.pem \
    ubuntu@52.78.233.64:/home/ubuntu/SKN20-FINAL-2TEAM/rag/index/* \
    /root/SKN20-FINAL-2TEAM/rag/index/

# 복사 확인 (아래 3개 필수)
ls -la /root/SKN20-FINAL-2TEAM/rag/index/
# 예상 결과:
#   chroma_db/      (1.6GB) ← 필수: ChromaDB 벡터 DB
#   bm25_index/     (252MB) ← 권장: BM25 스파스 인덱스
#   tokenizer.py    (3KB)   ← 권장: 한국어 형태소 분석기
```

---

## 4. vLLM 서버 실행

```bash
# /workspace에 병합 모델이 있는 경우
vllm serve /workspace/qwen2.5-14b-fto-merged \
    --host 0.0.0.0 --port 8000 --dtype float16 > /workspace/vllm.log 2>&1 &

# /workspace에 없는 경우 (HuggingFace에서 다운로드, ~29.5GB)
export HF_HOME=/workspace/hf_cache
vllm serve itsbini/qwen2.5-14b-fto-merged \
    --host 0.0.0.0 --port 8000 --dtype float16 > /workspace/vllm.log 2>&1 &

# 서버 준비 확인 (2~3분 소요)
tail -f /workspace/vllm.log
# "Application startup complete." 메시지 확인 후 Ctrl+C

# API 테스트
curl -s http://localhost:8000/v1/models | python3 -m json.tool
```

---

## 5. FastAPI 백엔드 실행

```bash
cd /root/SKN20-FINAL-2TEAM/backend
nohup uvicorn app.main:app --host 0.0.0.0 --port 8080 > /workspace/backend.log 2>&1 &

# 헬스체크
curl -s http://localhost:8080/health
# {"status":"healthy"} 확인
```

---

## 6. 접속 (SSH 터널)

```bash
# 로컬 Mac 터미널에서:
ssh -L 8080:localhost:8080 root@<RUNPOD_IP> -p <RUNPOD_PORT> -i ~/.ssh/id_ed25519 -N

# 브라우저에서:
# http://localhost:8080/chat.html        ← 특허 FTO 채팅
# http://localhost:8080/design-chat.html ← 디자인 분석
# http://localhost:8080/results.html     ← 분석 결과
```

---

## 7. 통합 테스트

```bash
# FTO 분석 테스트
curl -s -X POST http://localhost:8080/api/chat/message \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "message=나이아신아마이드 5%와 히알루론산을 포함하는 미백 보습 크림&analysis_type=fto"

# 예상 응답: {"analysis_complete":true, "analysis_id":1, ...}
# 약 2~3분 소요 (RAG 검색 + vLLM 생성)
```

---

## 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| `RDS 연결 실패` | RunPod IP가 보안 그룹에 없음 | AWS 콘솔에서 IP 추가 |
| `HNSW index 에러` | `.env`에 `CHROMA_HOST` 설정됨 | `.env`에서 CHROMA_HOST 주석처리 (로컬 사용) |
| `CHROMA_PORT int 파싱 에러` | `CHROMA_PORT=` 빈 값 | CHROMA_PORT 줄 삭제 또는 주석처리 |
| `context_length_exceeded` | 청구항 텍스트가 너무 김 | `rag/generate.py`의 `_truncate_claims` max_chars 조절 |
| `vLLM 서버 안 뜸` | GPU 메모리 부족 | A100 40GB 이상 필요 |
| `RAG 검색 0건` | `rag/index/chroma_db/` 없음 | EC2에서 복사 (3번 단계) |
| `포트 8080 사용 중` | 이전 프로세스 남아있음 | `fuser -k 8080/tcp` 후 재시작 |

---

## 포트 구성

| 포트 | 용도 |
|------|------|
| 8000 | vLLM 서버 (Qwen2.5-14B) |
| 8080 | FastAPI 백엔드 + 프론트엔드 |
| 8888 | JupyterLab |
