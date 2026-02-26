# sLLM 서빙 가이드 (Qwen2.5-VL-7B-Instruct + vLLM + RunPod)

---

## 모델 정보

| 항목 | 내용 |
|------|------|
| 모델 | `Qwen/Qwen2.5-VL-7B-Instruct` |
| 특징 | 텍스트 + 이미지 동시 처리 (Vision-Language) |
| 필요 VRAM | ~18 GB (bf16 기준) |
| 권장 GPU | RTX 3090 / RTX 4090 (24 GB) |

---

## Step 1. RunPod 포드 생성

- GPU: **RTX 3090 또는 RTX 4090 (24 GB VRAM)** 선택
- Template: PyTorch
- **Network Volume 연결** (모델 보존용)
- 포트 8000 외부 오픈 설정 (HTTP 포트로 추가)

---

## Step 1-5. vLLM 설치 확인 (최초 1회)

> PyTorch 템플릿 사용 시 vLLM이 없을 수 있음.  확인 후 없으면 설치.

```bash
# 설치 여부 확인
pip show vllm

# 없으면 설치
pip install vllm
```

---

## Step 2. 최초 1회 — 디스크 심볼릭 링크 설정

> ⚠️ RunPod의 `/root` 파티션은 용량이 매우 작음. vLLM 캐시가 `/root/.triton`에 쌓여 디스크 풀 에러 발생.
> `/workspace`(네트워크 볼륨)로 심볼릭 링크를 걸어야 함. **매 포드 시작마다 실행.**

```bash
mkdir -p /workspace/.triton /workspace/.cache
ln -sf /workspace/.triton /root/.triton
ln -sf /workspace/.cache /root/.cache
```

---

## Step 3. 최초 1회 — 모델 다운로드

> `/workspace`에 저장 = RunPod 네트워크 볼륨 → 포드 재시작해도 유지

```bash
cat > /tmp/download.py << 'EOF'
import os
os.environ['HF_HUB_DISABLE_XET'] = '1'
os.environ['HF_HOME'] = '/workspace/hf_cache'
from huggingface_hub import snapshot_download
snapshot_download(
    'Qwen/Qwen2.5-VL-7B-Instruct',
    local_dir='/workspace/Qwen2.5-VL-7B-Instruct'
)
print('다운로드 완료!')
EOF

python3 /tmp/download.py
```

- 소요 시간: 약 5~10분 (약 15 GB)
- 완료 시 `다운로드 완료!` 출력
- **이후 재다운로드 불필요** (네트워크 볼륨에 유지됨)

---

## Step 4. 매번 — vLLM 서버 실행

### 포드를 Start할 때마다 아래 명령 실행

### 백그라운드 실행 명령어
```bash
HF_HOME=/workspace/hf_cache TMPDIR=/workspace nohup python -m vllm.entrypoints.openai.api_server --model /workspace/Qwen2.5-VL-7B-Instruct --host 0.0.0.0 --port 8000 --dtype bfloat16 --max-model-len 8192 --gpu-memory-utilization 0.85 --enable-auto-tool-choice --tool-call-parser hermes > /workspace/vllm.log 2>&1 &
```

```bash
# 로그 실시간 확인
tail -f /workspace/vllm.log
```

- 소요 시간: 약 1~2분 (모델 GPU 로드)
- 성공 시 출력:
  ```
  INFO: Application startup complete.
  INFO: Uvicorn running on http://0.0.0.0:8000
  ```
- 이후 RunPod 프록시 URL로 API 요청 가능:
  ```
  https://<pod-id>-8000.proxy.runpod.net/v1
  ```

---

## Step 5. 서버 동작 확인

```bash
curl http://localhost:8000/v1/models
```

- 모델 목록 JSON이 반환되면 정상

---

## .env 설정 (design/.env)

```env
# RunPod 프록시 URL (포트 8000을 HTTP로 오픈한 경우)
VLLM_API_BASE=https://<pod-id>-8000.proxy.runpod.net/v1

# 로컬 모델 경로 (vLLM 서버 실행 시 --model 경로와 동일하게)
VLLM_MODEL=/workspace/Qwen2.5-VL-7B-Instruct

# 예시
# VLLM_API_BASE=https://m39wlfn1unsmhm-8000.proxy.runpod.net/v1
# VLLM_MODEL=/workspace/Qwen2.5-VL-7B-Instruct
```

- RunPod 대시보드 → 포드 → Connect → HTTP Service의 URL 확인
- `design_chatbot.py`, `utils.py` 모두 이 환경변수를 자동으로 읽음

---

## Step 6. 챗봇 실행

> **전제**: Step 4 vLLM 서버가 실행 중이고 `.env`에 `VLLM_API_BASE` / `VLLM_MODEL` 설정 완료

### 환경

```
conda 환경: langchain
실행 위치:  design/src/
```

### 실행

```bash
cd design/src

# API 서버로 실행 (프론트엔드 연동)
python api.py

# 또는 직접 테스트
python chatbot_test.py
```

### 챗봇 기능 & 입력 형식

| 기능 | 입력 예시 |
|------|----------|
| 이미지 → 유사 디자인 검색 + FTO 리포트 | `run_chatbot(image_path="경로/이미지.jpg")` |
| 일반 질문 | `run_chatbot(text_query="디자인 특허란?")` |
| 디자인 DB 검색 | `run_chatbot(text_query="펌프형 용기 디자인 찾아줘")` |
| 웹 검색 | `run_chatbot(text_query="2024년 디자인 특허 출원 통계 알려줘")` |

### 동작 흐름

```
[텍스트 입력] → 일반질문 노드
    ├─ DB 검색 키워드 감지  → search_design_db 호출 → LLM 요약
    ├─ 웹 검색 키워드 감지  → web_search 호출 → LLM 요약
    └─ 그 외               → LLM 직접 답변

[이미지 입력] → VLM 분석 → 유사 디자인 검색 → 사용자 선택(interrupt)
             → 상세 비교 → FTO 리포트 생성
```

### LLM 구성

| 역할 | 모델 | 비고 |
|------|------|------|
| 텍스트 생성 (리포트, 질의응답) | Qwen2.5-VL-7B-Instruct | vLLM 서빙 |
| 이미지 분석 / 비교 (VLM) | Qwen2.5-VL-7B-Instruct | 단일 모델로 통합 |
| 한국어 → 영어 번역 (CLIP 검색용) | Qwen2.5-VL-7B-Instruct | utils.py |

---

## RunPod 포드 관리 요령

| 상황 | 행동 | 모델 유지 |
|------|------|----------|
| 잠깐 안 쓸 때 | 포드 **Stop** | 유지 (GPU 비용 없음) |
| 다시 쓸 때 | 포드 **Start** → Step 4 실행 | 유지 |
| 포드 교체 시 | **Terminate + Delete Volume 체크 해제** | 유지 |
| 볼륨까지 삭제 | Terminate + Delete Volume 체크 | 사라짐 → Step 2부터 재실행 |

---

## 트러블슈팅

| 에러 | 원인 | 해결 |
|------|------|------|
| `CUDA out of memory` | GPU VRAM 부족 | RTX 3090/4090(24GB)으로 교체 |
| `Background writer channel closed` | HuggingFace xet 다운로드 버그 | Step 3 명령어 사용 (os.environ으로 비활성화) |
| `HF_HUB_DISABLE_XET` 무시됨 | 서브프로세스에 env 미전달 | vllm serve 직접 실행 전 모델 미리 다운로드 |
| `vllm: command not found` | vLLM 미설치 (PyTorch 템플릿) | `pip install vllm` 실행 (Step 1-5) |
| `tmux: command not found` | tmux 미설치 | nohup 사용 (Step 4) |
| 502 Bad Gateway | vLLM 서버 미실행 또는 로딩 중 | `ps aux \| grep vllm` 로 프로세스 확인, 없으면 Step 4 재실행 |
| SSH 끊김 후 서버 종료 | 포그라운드 실행 상태에서 연결 종료 | Step 4의 nohup 백그라운드 실행 방식 사용 |
| 포트 추가 후 SSH 끊김 | RunPod 포트 설정 변경 시 재시작 발생 | 정상 현상, 재연결 후 Step 2 → Step 4 재실행 |
| `No space left on device: /root/.triton` | `/root` 파티션 용량 부족 | Step 2 심볼릭 링크 실행 후 재시도 |
| `--port: command not found` | 백슬래시 줄바꿈이 shell에서 작동 안 함 | Step 4의 한 줄 명령어 사용 |
