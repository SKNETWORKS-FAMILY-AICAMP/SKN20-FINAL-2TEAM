# RunPod 서버리스 — LoRA 동적 로딩 배포 가이드

## 배경

머지 모델(`itsbini/qwen2.5-14b-fto-merged`)의 토크나이저가 깨져서 base 토크나이저를 사용 중.
모델 가중치도 제대로 머지되지 않았을 가능성 높음.
평가(94.3% 정확도)는 LoRA 동적 로딩으로 수행했으므로, 동일 환경으로 변경.

| 항목 | 기존 (머지) | 변경 (LoRA) |
|------|-------------|-------------|
| 모델 | `itsbini/qwen2.5-14b-fto-merged` | `Qwen/Qwen2.5-14B-Instruct` + LoRA |
| LoRA | 없음 (머지됨) | `itsbini/qwen2.5-14b-fto` |
| 토크나이저 | base 것 사용 (깨짐) | base 모델과 동일 |
| max_model_len | 16384 | 4096 (평가와 동일) |
| max_tokens | 4096 | 2048 (평가와 동일) |

---

## 전체 배포 순서

### 1단계: Docker Hub 계정 준비

Docker Hub 계정이 필요. 없으면 https://hub.docker.com 에서 무료 가입.

### 2단계: PC에서 Docker 이미지 빌드 & 푸시

**Docker Desktop을 켜야 함.** Docker Desktop 실행 후:

```bash
# 1) Docker Desktop이 실행 중인지 확인
docker info

# 2) Docker Hub 로그인
docker login
# → Username, Password 입력

# 3) runpod 폴더로 이동
cd C:/00project/SKN20-FINAL-2TEAM/runpod

# 4) 이미지 빌드 (본인 Docker Hub username으로 변경)
docker build -t <dockerhub-username>/fto-vllm-lora:v1 .

# 5) Docker Hub에 푸시
docker push <dockerhub-username>/fto-vllm-lora:v1
```

예시: Docker Hub username이 `itsbini`라면:
```bash
docker build -t itsbini/fto-vllm-lora:v1 .
docker push itsbini/fto-vllm-lora:v1
```

### 3단계: RunPod에서 새 Template 생성

RunPod 대시보드 → **Serverless** → **Custom Template** → **New Template**

| 항목 | 값 |
|------|-----|
| **Template Name** | `fto-vllm-lora` |
| **Container Image** | `<dockerhub-username>/fto-vllm-lora:v1` |
| **Container Disk** | `150 GB` |

**Environment Variables (5개):**

| Key | Value |
|-----|-------|
| `BASE_MODEL` | `Qwen/Qwen2.5-14B-Instruct` |
| `LORA_MODEL` | `itsbini/qwen2.5-14b-fto` |
| `MAX_MODEL_LEN` | `4096` |
| `HF_TOKEN` | (기존 HF 토큰 그대로) |
| `TRUST_REMOTE_CODE` | `1` |

나머지는 건드리지 않음. **Save Template**.

### 4단계: 새 Serverless Endpoint 생성

RunPod 대시보드 → **Serverless** → **New Endpoint**

| 항목 | 값 |
|------|-----|
| **Endpoint Name** | `fto-patent-lora` |
| **Template** | `fto-vllm-lora` (방금 만든 것) |
| **GPU** | `A100 80GB` |
| **Max Workers** | `1` |
| **Active Workers** | `0` |
| **Idle Timeout** | `5 sec` |
| **FlashBoot** | 활성화 |

생성하면 **Endpoint ID**가 나옴 (예: `abc123xyz`).

### 5단계: .env 파일 수정

```bash
# 새로 추가
RUNPOD_PATENT_ENDPOINT_ID=abc123xyz    # ← 4단계에서 받은 Endpoint ID

# 기존 건 주석처리 (삭제해도 됨)
# RUNPOD_PATENT_BASE_URL=https://api.runpod.ai/v2/d4afjk42vdje6l/openai/v1
```

### 6단계: 테스트

서버 재시작 후 테스트. 정상 작동 확인되면 다음 단계.

### 7단계: 기존 엔드포인트 삭제

RunPod 대시보드 → 기존 엔드포인트 (`d4afjk42vdje6l`) → Delete

---

## 관련 파일

| 파일 | 역할 |
|------|------|
| `runpod/handler.py` | RunPod 서버리스 커스텀 handler (vLLM + LoRA) |
| `runpod/Dockerfile` | Docker 이미지 설정 |
| `rag/config.py` | `RUNPOD_PATENT_ENDPOINT_ID` 설정 추가 |
| `rag/generate.py` | `_call_runpod_serverless()` 직접 호출 방식 추가 |

## 롤백 방법

문제 발생 시:
1. `.env`에서 `RUNPOD_PATENT_ENDPOINT_ID` 삭제
2. `RUNPOD_PATENT_BASE_URL` 주석 해제
3. 서버 재시작 → 기존 머지 모델 엔드포인트로 복귀
