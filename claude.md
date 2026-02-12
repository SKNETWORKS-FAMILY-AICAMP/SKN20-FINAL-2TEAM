# BINI 프로젝트 - Claude 가이드

> **Claude에게**: 대화 시작 시 이 파일을 먼저 읽고 프로젝트 상황을 파악한 후 진행하세요.

## 프로젝트 목적

**상품 출시 전 특허 침해 여부 사전 검증 서비스**
- 사용자가 출시하려는 제품이 기존 특허를 침해하는지 AI로 사전 판단

---

## 디렉토리 구조

```
SKN20-FINAL-2TEAM/
├── bini/                    # 핵심 sLLM 학습 모듈
│   ├── training/            # 학습/평가/추론 스크립트
│   ├── data/                # 학습 데이터
│   ├── outputs/             # 학습된 모델 (gemma3-1b-it-lora)
│   └── docs/                # 문서 (ERD, 학습 리포트)
│
├── backend/                 # FastAPI 백엔드 (MySQL 연결)
│   └── app/
│       ├── routers/         # API 라우터 (auth, chat, analysis, search)
│       ├── services/        # 비즈니스 로직 (search_service.py)
│       └── models/          # SQLAlchemy 모델
│
├── scripts/                 # 유틸리티 스크립트
│   └── import_patents.py    # 특허 JSON → MySQL import
│
├── FRONTEND/                # 정적 HTML/JS 프론트엔드
├── jsons_backup.zip         # 원본 특허 JSON 백업 (3,271개)
└── docker-compose.yml       # Docker 설정 (사용 안 함, 로컬 MySQL 사용)
```

---

## MySQL 데이터베이스 (완료)

### 연결 정보
```
Host: localhost
Port: 3306
Database: bini
User: root
Password: newpassword123
```

### 테이블 구조
| 테이블 | 건수 | 용도 |
|--------|------|------|
| `patents` | 3,271 | 특허 기본 정보 |
| `patent_ipc` | 17,273 | IPC 분류코드 (1:N) |
| `claims` | 158,584 | 청구항 (first/last 버전, 금반언 지원) |
| `claim_elements` | 763,719 | 키워드 검색용 요소 |

### 금반언(Estoppel) 지원
- `claims.version_type`: 'first' (출원) / 'last' (등록)
- `claims.change_type`: '삭제'인 경우 금반언 적용 대상
- 출원 시 있었으나 등록 시 삭제된 청구항은 침해 판단에서 제외

---

## 백엔드 API (FastAPI)

### 엔드포인트
```
/api/auth      # 인증 (로그인/회원가입)
/api/chat      # 채팅 기록
/api/analysis  # 특허 분석
/api/search    # 하이브리드 검색 (신규)
```

### 검색 API (신규)
```
GET  /api/search/keywords?q=헤스페리딘    # 키워드 검색
GET  /api/search/fulltext?q=화장료        # 전문 검색
GET  /api/search/patent/{id}/estoppel     # 금반언 조회
POST /api/search/hybrid                    # RDB + RAG 결과 병합
```

### 하이브리드 검색 플로우
```
사용자 입력
    │
    ├── RDB 검색 (claim_elements) ──┐
    │                               │
    └── RAG 검색 (ChromaDB, 팀원) ──┼── 결과 병합 → sLLM
                                    │
                            금반언 필터 적용
```

---

## 현재 상태

| 완료 | 진행 중 | 해야 할 일 |
|------|---------|-----------|
| ✅ MySQL 설정 | | sLLM 연동 |
| ✅ 특허 데이터 import (3,271건) | | RAG 팀원과 연동 |
| ✅ 하이브리드 검색 서비스 | | 프론트엔드 연결 |
| ✅ 검색 API 엔드포인트 | | |
| ✅ 금반언 지원 | | |
| sLLM 1B 학습 (97.1%) | | 4B 모델 학습 |

---

## 다음 작업: sLLM 연동

검색 결과를 sLLM 프롬프트에 주입하여 침해 판단:

```python
# 예상 플로우
1. 사용자 입력 → 키워드 추출
2. RDB 검색 + RAG 검색 → 결과 병합
3. 병합된 청구항 + 사용자 입력 → sLLM 프롬프트
4. sLLM 출력 (JSON) → 백엔드 후처리 → 사용자에게 표시
```

---

## 빠른 명령어

```bash
# 백엔드 실행
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload

# MySQL 접속
mysql -u root -pnewpassword123 bini

# 데이터 확인
mysql -u root -pnewpassword123 bini -e "SELECT COUNT(*) FROM patents;"

# sLLM 학습/평가
cd bini && python training/train.py
python training/evaluate.py
```

---

## 환경 설정

### backend/.env
```
DATABASE_URL=mysql+pymysql://root:newpassword123@localhost:3306/bini
```

### bini/.env
```
HF_TOKEN=your_huggingface_token
```

---

## 팀 정보

- 프로젝트: SKN20-FINAL-2TEAM
- GitHub: SKNETWORKS-FAMILY-AICAMP/SKN20-FINAL-2TEAM
