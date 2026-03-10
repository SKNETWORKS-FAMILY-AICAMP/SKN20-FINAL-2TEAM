# FTOGuard 재배포 가이드 (팀원용)

> 이 문서를 따라하면 처음부터 끝까지 배포 가능
> 아키텍처 설명은 DEPLOY.md 참고
> Claude CLI에 이 파일을 넘겨도 됨

---

## 사전 준비물

| 항목 | 용도 |
|------|------|
| AWS 계정 | EC2, RDS |
| RunPod 계정 | LLM GPU 서빙 |
| Docker Hub 계정 | RunPod 이미지 업로드 |
| Docker Desktop | RunPod 이미지 빌드 (로컬) |
| SSH 키 (.pem) | EC2 접속 (생성 시 다운로드) |
| data/ 폴더 | ChromaDB + BM25 데이터 (팀원에게 받기, git 미포함) |
| .env.ec2 파일 | API 키 등 (팀원에게 받거나 직접 작성) |

---

## Step 1: RunPod Serverless 엔드포인트 생성

GPU 필요한 LLM은 RunPod에서 돌린다. EC2에는 GPU 없음.

### 1-1. 특허 FTO 모델 (Qwen2.5-14B + LoRA)

로컬 PC에서 Docker Desktop 실행 후:

```bash
docker login
cd SKN20-FINAL-2TEAM/runpod
docker build -t <username>/fto-vllm-lora:v1 .
docker push <username>/fto-vllm-lora:v1
```

(<username> = 본인 Docker Hub 아이디)

RunPod Dashboard -> Serverless -> Custom Template -> New Template:
- Template Name: fto-vllm-lora
- Container Image: `<username>/fto-vllm-lora:v1`
- Container Disk: 150 GB

환경변수 5개:

| Key | Value |
|-----|-------|
| BASE_MODEL | Qwen/Qwen2.5-14B-Instruct |
| LORA_MODEL | itsbini/qwen2.5-14b-fto |
| MAX_MODEL_LEN | 4096 |
| HF_TOKEN | (HuggingFace 토큰) |
| TRUST_REMOTE_CODE | 1 |

Serverless -> New Endpoint:
- Template: fto-vllm-lora / GPU: A100 80GB
- Max Workers: 1 / Active Workers: 0 (발표 전 1로 변경)
- Idle Timeout: 5 sec / FlashBoot: 활성화

-> **Endpoint ID 메모** (예: hmh882ms5azjye)

### 1-2. 디자인 VLM (Qwen2.5-VL-7B)

별도 Serverless 엔드포인트 생성. GPU: RTX 4090 24GB 이상.
-> **Base URL 메모** (예: `https://api.runpod.ai/v2/xxxxx/openai/v1`)

---

## Step 2: AWS RDS MySQL

기존 RDS 사용 또는 새로 생성.

새로 만들 경우:
```
AWS Console -> RDS -> 데이터베이스 생성
- 엔진: MySQL 8.x
- 인스턴스: db.t3.micro
- 스토리지: 20GB
- 퍼블릭 액세스: 예
- DB 이름: fto
```

-> **RDS 엔드포인트** 메모
-> 보안그룹에서 3306 포트 열기

기존: `fto-db.c34w48m8sov6.ap-northeast-2.rds.amazonaws.com:3306/fto`

---

## Step 3: AWS EC2 인스턴스 생성

```
AWS Console -> EC2 -> 인스턴스 시작
- AMI: Ubuntu Server 22.04 LTS (Amazon Linux 아님!)
- 인스턴스 유형: r6i.large (16GB RAM) *** 중요! 8GB 미만 부족
- 키 페어: 새로 생성 -> .pem 다운로드
- 스토리지: 50GB (30GB는 부족할 수 있음)
- 보안 그룹: SSH(22) 허용
```

-> **퍼블릭 IP** 메모
-> Ubuntu는 SSH 사용자명 **ubuntu** (ec2-user 아님!)

---

## Step 4: EC2에 Docker 설치

### 4-1. SSH 접속 (로컬 PC에서)

```bash
# Windows PowerShell
ssh -i "C:\Users\USERNAME\Downloads\fto-key.pem" ubuntu@EC2_PUBLIC_IP

# Mac/Linux
ssh -i ~/.ssh/fto-key.pem ubuntu@EC2_PUBLIC_IP
```

### 4-2. Docker 설치 (EC2에서)

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker ubuntu
```

### 4-3. 재접속 (권한 적용 필수!)

```bash
exit
# 다시 SSH 접속
docker --version       # sudo 없이 되면 성공
docker compose version
```

---

## Step 5: 프로젝트 클론 + 데이터 업로드

### 5-1. git clone (EC2에서)

```bash
cd ~
git clone https://github.com/your-org/SKN20-FINAL-2TEAM.git
cd SKN20-FINAL-2TEAM
```

### 5-2. data/ 업로드 (로컬 PC에서, 10~20분)

data/ 폴더는 git에 없음. 팀원에게 받아서 수동 업로드.

```bash
# Windows PowerShell (~ 안 됨! 절대경로 사용)
scp -i "C:\Users\USERNAME\Downloads\fto-key.pem" -r C:\path\to\data\ ubuntu@EC2_PUBLIC_IP:/home/ubuntu/SKN20-FINAL-2TEAM/data/
```

### 5-3. 확인 (EC2에서)

```bash
ls -la data/    # chroma-patent/ chroma-design/ bm25_index/ 3개 OK
du -sh data/*   # patent ~1.9GB, design ~75MB, bm25 ~173MB
```

---

## Step 6: 환경변수 설정

### 6-1. .env.ec2 작성 (로컬 PC에서)

```env
# MySQL (RDS)
MYSQL_HOST=your-rds-endpoint.amazonaws.com
MYSQL_PORT=3306
MYSQL_USER=admin
MYSQL_PASSWORD=your-password
MYSQL_DATABASE=fto

# RunPod (특허)
RUNPOD_API_KEY=your-runpod-api-key
RUNPOD_PATENT_ENDPOINT_ID=your-endpoint-id

# RunPod (디자인)
RUNPOD_DESIGN_BASE_URL=https://api.runpod.ai/v2/your-endpoint/openai/v1
DESIGN_VLLM_MODEL=Qwen/Qwen2.5-VL-7B-Instruct

# OpenAI
OPENAI_API_KEY=your-openai-key

# Tavily (웹 검색)
TAVILY_API_KEY=your-tavily-key

# HuggingFace
HF_TOKEN=your-hf-token

# 인증
SECRET_KEY=your-secret-key
DEV_BYPASS_AUTH=true

# AWS S3
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret
AWS_REGION=ap-northeast-2
S3_BUCKET_NAME=ftoguard-design-images
```

### 6-2. EC2로 전송 (로컬 PC에서)

```bash
scp -i "C:\Users\USERNAME\Downloads\fto-key.pem" .env.ec2 ubuntu@EC2_PUBLIC_IP:/home/ubuntu/SKN20-FINAL-2TEAM/.env.ec2
```

---

## Step 7: Docker 빌드 & 실행

EC2에서:

```bash
cd ~/SKN20-FINAL-2TEAM

# 빌드 (5~10분)
docker compose --env-file .env.ec2 build --no-cache

# 실행
docker compose --env-file .env.ec2 up -d

# 확인 (3개 컨테이너 Up)
docker ps

# 로그 ("Uvicorn running..." 나오면 성공)
docker logs fto-backend --tail 30
```

첫 디자인 분석 요청 시 CLIP 모델 다운로드 (~340MB, 1~2분). 성공 로그:
```
[design] ChromaDB HttpClient: chromadb-design:8000
[design] 컬렉션 design 로드: 21801개
[design] LangGraph 디자인 챗봇 로드 성공
```

---

## Step 8: 보안그룹 포트 열기

```
AWS Console -> EC2 -> 인스턴스 -> 보안 탭 -> 보안 그룹
-> 인바운드 규칙 편집 -> 규칙 추가:

유형              포트    소스         설명
SSH               22     내 IP        서버 접속
사용자 지정 TCP   8080   0.0.0.0/0    웹 서비스
```

---

## Step 9: 접속 확인 & 도메인

브라우저: `http://EC2_PUBLIC_IP:8080` -> FTOGuard 페이지 나오면 성공!

도메인 (선택):
- 내도메인.한국 에서 무료 등록
- 웹 포워딩: `http://EC2_PUBLIC_IP:8080`
- EC2 IP 바뀌면 포워딩 대상 업데이트 (Elastic IP로 고정 가능)

---

## 운영 명령어 (EC2에서)

```bash
docker ps                                           # 상태
docker logs fto-backend --tail 50                   # 로그
docker compose --env-file .env.ec2 restart          # 재시작
docker compose --env-file .env.ec2 down             # 중지
docker compose --env-file .env.ec2 up -d            # 시작

# 코드 업데이트 후 재배포
git pull
docker compose --env-file .env.ec2 build --no-cache
docker compose --env-file .env.ec2 up -d

# 용량 정리
docker system prune -a -f
df -h /
```

---

## 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| 접속 안 됨 | 보안그룹 8080 안 열림 | 인바운드 규칙 추가 |
| SSH denied (ec2-user) | Ubuntu AMI | ubuntu@ 사용 |
| docker compose 없음 | 미설치 | sudo apt-get install -y docker-compose-v2 |
| 빌드 실패 (No space) | 용량 부족 | docker system prune -a -f 또는 EBS 확장 |
| 500 에러 (특허) | ChromaDB 데이터 없음 | data/ 업로드 확인 |
| 500 에러 (디자인) | Collection not exist | CHROMA_IMAGE_HOST 환경변수 확인 |
| libGL.so.1 not found | opencv 라이브러리 | Dockerfile에 libgl1 libglib2.0-0 확인 |
| ModuleNotFoundError | PYTHONPATH | Dockerfile에 ENV PYTHONPATH 확인 |
| 분석 느림 (30초~2분) | RunPod Cold Start | Active Workers=1 |
| 빌드 0초 끝남 | Docker 캐시 | --no-cache 추가 |

### EBS 용량 확장 (EC2 중지 없이)

```
AWS Console -> EC2 -> Elastic Block Store -> 볼륨 -> 수정 -> 크기 변경
```

```bash
sudo growpart /dev/nvme0n1 1
sudo resize2fs /dev/nvme0n1p1
```

### 인스턴스 유형 변경 (EC2 중지 필요)

EC2 -> 인스턴스 -> 중지 -> "중지됨" 대기 -> 인스턴스 유형 변경 -> 시작

---

## 비용 참고

| 항목 | 11일 기준 | 월 기준 |
|------|----------|---------|
| EC2 r6i.large | ~57,000원 | ~160,000원 |
| RDS db.t3.micro | ~7,000원 | ~20,000원 |
| EBS 50GB | ~2,000원 | ~5,000원 |
| RunPod (Active=0) | ~$30-50 | 사용량 |
| RunPod (Active=1) | ~$130 | ~$360 |

---

## RunPod 롤백

1. .env.ec2에서 RUNPOD_PATENT_ENDPOINT_ID 삭제
2. RUNPOD_PATENT_BASE_URL=기존URL 추가
3. docker compose restart
