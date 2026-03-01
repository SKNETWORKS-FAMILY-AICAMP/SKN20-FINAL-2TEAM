# EC2 배포 가이드 (인프라 담당용)

> 전체 아키텍처는 `dj.md` 참고

---

## 1. EC2 인스턴스 생성

```
AWS Console → EC2 → 인스턴스 시작

- 이름: fto-docker
- AMI: Amazon Linux 2023
- 인스턴스 유형: r6i.large (16GB RAM)
- 키 페어: 기존 것 선택 또는 새로 생성
- 스토리지: 30GB (데이터 + Docker 이미지)
- 보안 그룹: 인스턴스 생성 시 "새 보안 그룹 생성" 선택, SSH만 열어도 됨
  (나머지 포트는 생성 후 아래 1-1에서 추가)
```

### 1-1. 보안 그룹 설정 (EC2 생성 후)

보안 그룹 = EC2의 방화벽. "이 포트로 누가 접속할 수 있나?" 설정.

```
AWS Console 접속
→ EC2 → 좌측 메뉴 "인스턴스" 클릭
→ 방금 만든 인스턴스 (fto-docker) 클릭
→ 하단 탭에서 "보안" 탭 클릭
→ "보안 그룹" 링크 클릭 (sg-xxxxx 형태)
→ "인바운드 규칙" 탭 클릭
→ "인바운드 규칙 편집" 버튼 클릭
```

아래 규칙 추가:

```
[규칙 추가] 버튼을 눌러서 하나씩 추가

유형              포트    소스             설명
────────────────────────────────────────────────────
SSH               22     내 IP            서버 접속용
사용자 지정 TCP   8080   0.0.0.0/0        백엔드 (누구나 접속)
사용자 지정 TCP   8001   0.0.0.0/0        ChromaDB 특허
사용자 지정 TCP   8002   0.0.0.0/0        ChromaDB 디자인
```

```
"소스" 선택 방법:
- "내 IP" 선택 → 자동으로 현재 내 IP가 입력됨
- "Anywhere-IPv4" 선택 → 0.0.0.0/0 (누구나 접속 가능)
- 직접 입력 → 팀원 IP/32 (예: 123.456.789.0/32)
```

```
⚠️ 주의:
- 8001, 8002 (ChromaDB)는 DB라서 "Anywhere"로 열면 누구나 접속 가능
- 데모/학습용이면 Anywhere OK, 실무면 팀원 IP만 허용
- 프로젝트 끝나면 (3/11 이후) EC2 삭제하면 자동으로 없어짐
```

→ "규칙 저장" 클릭

---

## 2. SSH 접속

```bash
ssh -i ~/.ssh/your-key.pem ec2-user@EC2_PUBLIC_IP
```

---

## 3. Docker 설치

```bash
# Docker 설치
sudo yum install -y docker
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker ec2-user

# 재접속 (권한 적용)
exit
ssh -i ~/.ssh/your-key.pem ec2-user@EC2_PUBLIC_IP

# 확인
docker --version
docker compose version
```

---

## 4. 프로젝트 클론

```bash
cd ~
git clone https://github.com/YOUR_REPO/SKN20-FINAL-2TEAM.git
cd SKN20-FINAL-2TEAM
```

---

## 5. 데이터 업로드

**로컬 PC에서 실행** (EC2가 아님):

```bash
# data/ 폴더를 EC2로 전송 (약 10분)
scp -i ~/.ssh/your-key.pem -r data/ ec2-user@EC2_PUBLIC_IP:~/SKN20-FINAL-2TEAM/data/
```

```
data/ 폴더 구조:
├── chroma-patent/     ← 특허 벡터 (~1.9GB)
│   ├── chroma.sqlite3
│   └── d7dbe90e.../   ← HNSW 인덱스
└── chroma-design/     ← 디자인 벡터 (~75MB)
    ├── chroma.sqlite3
    └── 6c04f8e4.../
```

> data/는 git에 포함 안 됨 (.gitignore). 반드시 scp로 수동 업로드.
> KURE 임베딩 모델로 78,716건 특허를 벡터화한 결과물이라 Docker가 자동 생성 안 함.

---

## 6. ChromaDB Docker 실행

```bash
cd ~/SKN20-FINAL-2TEAM
docker compose -f docker-compose.chromadb.yml up -d
```

확인:

```bash
# 컨테이너 상태
docker ps

# 특허 ChromaDB
curl http://localhost:8001/api/v2/heartbeat

# 디자인 ChromaDB
curl http://localhost:8002/api/v2/heartbeat
```

---

## 7. 팀원 연결

팀원은 `.env`에 EC2 IP만 넣으면 됨:

```env
CHROMA_HOST=EC2_PUBLIC_IP
CHROMA_PORT=8001
```

data/ 폴더 복사 필요 없음. EC2 ChromaDB를 원격으로 사용.

---

## 8. 비용

| 항목 | 11일 예상 |
|------|----------|
| EC2 r6i.large | ~57,000원 |
| 스토리지 30GB | ~1,000원 |
| 데이터 전송 | ~2,000원 |
| **합계** | **~60,000원** (30만원 예산) |

---

## 트러블슈팅

```bash
# 로그 확인
docker logs chromadb-patent
docker logs chromadb-design

# 컨테이너 재시작
docker compose -f docker-compose.chromadb.yml restart

# 완전 재생성 (데이터 유지)
docker compose -f docker-compose.chromadb.yml down
docker compose -f docker-compose.chromadb.yml up -d

# 메모리 확인
free -h
docker stats
```