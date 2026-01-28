# BINI 프로젝트 ERD v2

## 1. 시스템 개요

### 1.1 Agent 기반 대화 플로우

```
사용자 입력
     │
     ▼
┌─────────────────────────────────┐
│           Agent                 │
│  ┌─────────────────────────┐    │
│  │    정보 충분한가?        │    │
│  └───────────┬─────────────┘    │
│         ┌────┴────┐             │
│         ▼         ▼             │
│       NO         YES            │
│         │         │             │
│         ▼         ▼             │
│  ┌──────────┐ ┌──────────┐     │
│  │ 추가질문  │ │ 분석실행  │     │
│  │ Tool     │ │ Tool     │     │
│  └──────────┘ └──────────┘     │
└─────────────────────────────────┘
```

### 1.2 두 가지 분석 플로우

| 입력 타입 | 처리 과정 |
|-----------|-----------|
| **이미지+텍스트** | 이미지 RAG → 유사도 모델 → 임계값 필터 → LLM 답변 |
| **텍스트만** | 키워드 추출 → 청구항 RAG → Rerank → sLLM 답변 |

### 1.3 핵심 기능
- 로그인/회원가입
- 채팅 기반 상담 **(Agent가 추가 질문)**
- 이미지 유사도 검색
- 텍스트 기반 청구항 검색
- 채팅 기록 저장 (사용자별)

---

## 2. ERD 다이어그램

```
                              ┌─────────────────┐
                              │     users       │
                              ├─────────────────┤
                              │ PK id           │
                              │    email        │
                              │    password     │
                              │    name         │
                              │    created_at   │
                              └────────┬────────┘
                                       │
                         ┌─────────────┴─────────────┐
                         │ 1:N                       │ 1:N
                         ▼                           ▼
              ┌─────────────────┐          ┌─────────────────┐
              │     chats       │          │   user_patents  │
              ├─────────────────┤          │   (북마크/관심) │
              │ PK id           │          ├─────────────────┤
              │ FK user_id      │          │ FK user_id      │
              │    title        │          │ FK patent_id    │
              │    created_at   │          └─────────────────┘
              └────────┬────────┘
                       │ 1:N
                       ▼
              ┌─────────────────┐
              │    messages     │
              ├─────────────────┤
              │ PK id           │
              │ FK chat_id      │
              │    role         │ ← 'user' | 'assistant'
              │    content      │
              │    input_type   │ ← 'text' | 'image_text'
              │    created_at   │
              └────────┬────────┘
                       │ 1:1
                       ▼
              ┌─────────────────┐
              │    analyses     │
              ├─────────────────┤
              │ PK id           │
              │ FK message_id   │
              │    input_type   │ ← 'text' | 'image_text'
              │    keywords     │ ← JSON (추출된 키워드)
              │    risk_level   │
              │    result_json  │
              │    created_at   │
              └────────┬────────┘
                       │
         ┌─────────────┼─────────────┐
         │ 1:N         │             │ N:M
         ▼             │             ▼
┌─────────────────┐    │    ┌─────────────────┐
│ analysis_images │    │    │ analysis_claims │
├─────────────────┤    │    ├─────────────────┤
│ PK id           │    │    │ FK analysis_id  │
│ FK analysis_id  │    │    │ FK claim_id     │
│    file_path    │    │    │    similarity   │
│    file_name    │    │    │    rerank_score │
└─────────────────┘    │    │    rank         │
                       │    └────────┬────────┘
                       │             │
                       │             │
══════════════════════════════════════════════════════
           특허 데이터 (RAG 대상)
══════════════════════════════════════════════════════
                       │             │
                       │             ▼
              ┌─────────────────┐
              │    patents      │
              ├─────────────────┤
              │ PK id           │
              │    regit_num    │ ← 등록번호
              │    title        │
              │    applicant    │
              │    ipc_code     │
              │    created_at   │
              └────────┬────────┘
                       │ 1:N
         ┌─────────────┴─────────────┐
         ▼                           ▼
┌─────────────────┐         ┌─────────────────┐
│     claims      │         │  patent_images  │
├─────────────────┤         ├─────────────────┤
│ PK id           │         │ PK id           │
│ FK patent_id    │         │ FK patent_id    │
│    claim_number │         │    image_path   │
│    claim_text   │         │    description  │
│    claim_type   │         │    image_type   │
└────────┬────────┘         └────────┬────────┘
         │ 1:1                       │ 1:1
         ▼                           ▼
┌─────────────────┐         ┌─────────────────┐
│ claim_embeddings│         │ image_embeddings│
├─────────────────┤         ├─────────────────┤
│ FK claim_id     │         │ FK patent_image_id│
│    embedding    │         │    embedding    │
│    model_name   │         │    model_name   │
└─────────────────┘         └─────────────────┘
```

---

## 3. 테이블 상세

### 3.1 users (사용자)

```sql
CREATE TABLE users (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    email VARCHAR(255) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    name VARCHAR(100) NOT NULL,
    profile_image VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

### 3.2 chats (채팅방)

```sql
CREATE TABLE chats (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    title VARCHAR(255),  -- 첫 메시지 기반 자동 생성
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id)
);
```

### 3.3 messages (메시지)

```sql
CREATE TABLE messages (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    chat_id BIGINT NOT NULL,
    role ENUM('user', 'assistant', 'system') NOT NULL,
    content TEXT NOT NULL,
    input_type ENUM('text', 'image_text') DEFAULT 'text',  -- 사용자 메시지만 해당
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
    INDEX idx_chat_id (chat_id)
);
```

### 3.4 analyses (분석 결과)

```sql
CREATE TABLE analyses (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    message_id BIGINT UNIQUE NOT NULL,  -- 1:1 관계
    input_type ENUM('text', 'image_text') NOT NULL,

    -- 텍스트 분석용
    extracted_keywords JSON,  -- ["tributyl acetylcitrate", "미백", "크림"]

    -- 공통 결과
    risk_level ENUM('high', 'medium', 'low'),
    risk_score FLOAT,  -- 0.0 ~ 1.0
    result_json JSON,  -- 전체 분석 결과

    -- 메타데이터
    model_used VARCHAR(100),  -- 'gemma-1b-lora' or 'gpt-4-vision'
    processing_time_ms INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
);
```

### 3.5 analysis_images (분석에 사용된 이미지)

```sql
CREATE TABLE analysis_images (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    analysis_id BIGINT NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    file_size INT,
    mime_type VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
);
```

### 3.6 analysis_claims (분석-청구항 매핑)

```sql
-- 분석에서 검색된 관련 청구항들
CREATE TABLE analysis_claims (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    analysis_id BIGINT NOT NULL,
    claim_id BIGINT NOT NULL,

    -- RAG 검색 결과
    similarity_score FLOAT,  -- 벡터 유사도 (0~1)
    rerank_score FLOAT,      -- Rerank 후 점수
    final_rank INT,          -- 최종 순위

    -- 매칭 결과
    match_result ENUM('match', 'no_match', 'uncertain'),

    FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE,
    FOREIGN KEY (claim_id) REFERENCES claims(id) ON DELETE CASCADE,
    UNIQUE KEY (analysis_id, claim_id)
);
```

---

## 4. 특허 데이터 테이블

### 4.1 patents (특허)

```sql
CREATE TABLE patents (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    regit_num VARCHAR(50) UNIQUE NOT NULL,  -- 등록번호
    title VARCHAR(500) NOT NULL,
    applicant VARCHAR(255),
    filing_date DATE,
    registration_date DATE,
    ipc_code VARCHAR(50),  -- 국제특허분류
    abstract TEXT,
    status ENUM('active', 'expired') DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_regit_num (regit_num),
    INDEX idx_ipc_code (ipc_code)
);
```

### 4.2 claims (청구항) - 텍스트 RAG 대상

```sql
CREATE TABLE claims (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    patent_id BIGINT NOT NULL,
    claim_number INT NOT NULL,
    claim_text TEXT NOT NULL,
    claim_type ENUM('independent', 'dependent') DEFAULT 'independent',
    parent_claim_id BIGINT,  -- 종속항인 경우
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patent_id) REFERENCES patents(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_claim_id) REFERENCES claims(id),
    UNIQUE KEY (patent_id, claim_number)
);
```

### 4.3 claim_embeddings (청구항 임베딩) - 텍스트 RAG

```sql
-- PostgreSQL + pgvector 사용
CREATE TABLE claim_embeddings (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    claim_id BIGINT UNIQUE NOT NULL,
    embedding VECTOR(1536) NOT NULL,  -- OpenAI ada-002 or 768 for Korean models
    model_name VARCHAR(100) DEFAULT 'text-embedding-ada-002',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (claim_id) REFERENCES claims(id) ON DELETE CASCADE
);

-- 벡터 검색 인덱스
CREATE INDEX idx_claim_emb ON claim_embeddings
USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

### 4.4 patent_images (특허 이미지) - 이미지 RAG 대상

```sql
CREATE TABLE patent_images (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    patent_id BIGINT NOT NULL,
    image_path VARCHAR(500) NOT NULL,
    image_type ENUM('drawing', 'diagram', 'photo', 'chart') DEFAULT 'drawing',
    description TEXT,  -- 이미지 설명 (있는 경우)
    figure_number VARCHAR(20),  -- 도면 번호 (예: "도 1", "Fig. 1")
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patent_id) REFERENCES patents(id) ON DELETE CASCADE
);
```

### 4.5 image_embeddings (이미지 임베딩) - 이미지 RAG

```sql
CREATE TABLE image_embeddings (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    patent_image_id BIGINT UNIQUE NOT NULL,
    embedding VECTOR(512) NOT NULL,  -- CLIP 모델 기준
    model_name VARCHAR(100) DEFAULT 'openai/clip-vit-base-patch32',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patent_image_id) REFERENCES patent_images(id) ON DELETE CASCADE
);

-- 벡터 검색 인덱스
CREATE INDEX idx_image_emb ON image_embeddings
USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

---

## 5. 데이터 플로우

### 5.1 텍스트만 입력된 경우

```
1. 사용자: "tributyl acetylcitrate가 들어간 미백 크림을 출시하려고 해"
                    │
                    ▼
2. 키워드 추출: ["tributyl acetylcitrate", "미백", "크림"]
                    │
                    ▼
3. 키워드 → 임베딩 변환
                    │
                    ▼
4. claim_embeddings에서 유사도 검색 (Top 10)
                    │
                    ▼
5. Reranker로 재정렬 (Top 3)
                    │
                    ▼
6. sLLM (학습된 Gemma 1B)로 분석
   - 청구항 vs 제품 비교
   - risk_level 판단
                    │
                    ▼
7. 결과 저장:
   - messages (user + assistant)
   - analyses (분석 결과)
   - analysis_claims (검색된 청구항들)
```

### 5.2 이미지+텍스트 입력된 경우

```
1. 사용자: [제품 이미지] + "이 제품 출시해도 될까?"
                    │
                    ▼
2. 이미지 저장 (analysis_images)
                    │
                    ▼
3. 이미지 → CLIP 임베딩 변환
                    │
                    ▼
4. image_embeddings에서 유사도 검색
                    │
                    ▼
5. 유사도 임계값 필터링 (예: > 0.7)
                    │
         ┌─────────┴─────────┐
         ▼                   ▼
   유사 이미지 있음      유사 이미지 없음
         │                   │
         ▼                   ▼
   해당 특허 청구항      "유사한 특허 없음"
   가져와서 분석              응답
         │
         ▼
6. LLM (GPT-4V or 멀티모달)로 분석
   - 이미지 vs 특허 이미지 비교
   - 구성요소 대응 판단
                    │
                    ▼
7. 결과 저장
```

---

## 6. API 설계

### 6.1 인증

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | `/api/auth/register` | 회원가입 |
| POST | `/api/auth/login` | 로그인 (JWT 발급) |
| POST | `/api/auth/refresh` | 토큰 갱신 |
| GET | `/api/auth/me` | 내 정보 조회 |

### 6.2 채팅

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/chats` | 내 채팅 목록 |
| POST | `/api/chats` | 새 채팅 시작 |
| GET | `/api/chats/:id` | 채팅 상세 (메시지 포함) |
| DELETE | `/api/chats/:id` | 채팅 삭제 |

### 6.3 분석

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | `/api/analyze/text` | 텍스트 분석 |
| POST | `/api/analyze/image` | 이미지+텍스트 분석 |
| GET | `/api/analyses/:id` | 분석 결과 상세 |

### 6.4 특허 (관리자)

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/patents` | 특허 목록 |
| POST | `/api/patents` | 특허 등록 |
| POST | `/api/patents/:id/claims` | 청구항 추가 |
| POST | `/api/patents/:id/images` | 이미지 추가 |
| POST | `/api/patents/embed` | 임베딩 생성 (배치) |

---

## 7. 기술 스택 추천

### 7.1 백엔드

| 구분 | 추천 | 대안 |
|------|------|------|
| Framework | FastAPI (Python) | Django, Flask |
| DB | PostgreSQL + pgvector | MySQL + Milvus |
| Auth | JWT | OAuth2 |
| Storage | S3 / MinIO | Local filesystem |

### 7.2 AI/ML

| 구분 | 추천 | 용도 |
|------|------|------|
| 텍스트 임베딩 | OpenAI ada-002 | 청구항 RAG |
| | 또는 KoSimCSE | 한국어 특화 |
| 이미지 임베딩 | CLIP | 이미지 RAG |
| Reranker | bge-reranker | 검색 결과 재정렬 |
| 텍스트 분석 | Fine-tuned Gemma 1B | 침해 판단 |
| 이미지 분석 | GPT-4 Vision | 이미지 비교 |

### 7.3 프론트엔드

| 구분 | 추천 |
|------|------|
| Framework | React / Next.js |
| UI | Tailwind CSS |
| 상태관리 | Zustand / React Query |

---

## 8. 테이블 요약

| 테이블명 | 용도 | 주요 관계 |
|----------|------|-----------|
| **users** | 사용자 정보 | - |
| **chats** | 채팅방 | users 1:N |
| **messages** | 채팅 메시지 | chats 1:N |
| **analyses** | 분석 결과 | messages 1:1 |
| **analysis_images** | 업로드 이미지 | analyses 1:N |
| **analysis_claims** | 검색된 청구항 | analyses N:M claims |
| **patents** | 특허 정보 | - |
| **claims** | 청구항 | patents 1:N |
| **claim_embeddings** | 청구항 벡터 | claims 1:1 |
| **patent_images** | 특허 이미지 | patents 1:N |
| **image_embeddings** | 이미지 벡터 | patent_images 1:1 |

**총 11개 테이블**

---

## 9. 추가 고려사항

### 9.1 유사도 임계값 설정

```python
# config.py
SIMILARITY_THRESHOLDS = {
    "text_rag": 0.75,      # 텍스트 유사도 최소값
    "image_rag": 0.70,     # 이미지 유사도 최소값
    "rerank_cutoff": 0.5,  # Rerank 후 컷오프
}
```

### 9.2 Reranker 적용

```python
# RAG 검색 후 Rerank
def search_and_rerank(query: str, top_k: int = 10, final_k: int = 3):
    # 1. 벡터 검색 (Top K)
    candidates = vector_search(query, top_k)

    # 2. Reranker로 재정렬
    reranked = reranker.rerank(query, candidates)

    # 3. 상위 N개 반환
    return reranked[:final_k]
```

### 9.3 이미지 유사도 모델 학습

```python
# 유사 이미지 판별 모델 (선택적)
# - Siamese Network 또는
# - Contrastive Learning 기반
# - 특허 이미지 도메인에 특화
```

---

---

## 10. Agent 시스템 테이블

### 10.1 Agent 플로우

```
사용자: "크림 출시하려고 해"
              │
              ▼
┌──────────────────────────────────────┐
│  Agent Step 1                        │
│  Thought: "성분 정보가 없네"          │
│  Action: ask_question               │
│  Output: "어떤 성분이 들어가나요?"     │
└──────────────────────────────────────┘
              │
              ▼
사용자: "tributyl acetylcitrate 들어가"
              │
              ▼
┌──────────────────────────────────────┐
│  Agent Step 2                        │
│  Thought: "성분 정보 있음, 검색하자"   │
│  Action: search_claims              │
│  Output: [관련 청구항 3개]            │
└──────────────────────────────────────┘
              │
              ▼
┌──────────────────────────────────────┐
│  Agent Step 3                        │
│  Thought: "청구항 찾음, 분석하자"      │
│  Action: analyze_infringement       │
│  Output: {risk_level: "높음", ...}   │
└──────────────────────────────────────┘
```

### 10.2 conversation_states (대화 상태)

```sql
-- 현재 대화에서 수집된 정보 추적
CREATE TABLE conversation_states (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    chat_id BIGINT UNIQUE NOT NULL,

    -- 수집된 정보
    product_type VARCHAR(100),           -- "크림", "세럼" 등
    ingredients JSON,                     -- ["tributyl acetylcitrate", ...]
    product_description TEXT,            -- 상세 설명
    has_image BOOLEAN DEFAULT FALSE,

    -- 상태
    info_complete BOOLEAN DEFAULT FALSE, -- 분석 가능 여부
    current_step VARCHAR(50),            -- 'collecting', 'searching', 'analyzing', 'done'

    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
);
```

### 10.3 agent_actions (Agent 행동 기록)

```sql
CREATE TABLE agent_actions (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    chat_id BIGINT NOT NULL,
    message_id BIGINT,                   -- 트리거한 메시지

    -- Agent 사고 과정
    thought TEXT,                        -- "성분 정보가 없네..."
    action_type ENUM(
        'ask_question',                  -- 추가 질문
        'search_claims',                 -- 청구항 RAG
        'search_images',                 -- 이미지 RAG
        'analyze',                       -- 분석 실행
        'respond'                        -- 최종 응답
    ) NOT NULL,

    -- 입출력
    action_input JSON,                   -- Tool 입력
    action_output JSON,                  -- Tool 출력

    -- 메타
    execution_time_ms INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE SET NULL
);
```

### 10.4 필요 정보 체크리스트

```sql
-- 분석에 필요한 정보 정의
CREATE TABLE required_info_checks (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    chat_id BIGINT NOT NULL,

    info_type ENUM(
        'product_type',      -- 제품 유형 (크림, 세럼 등)
        'ingredients',       -- 성분
        'usage',            -- 용도/효능
        'image'             -- 제품 이미지
    ) NOT NULL,

    is_provided BOOLEAN DEFAULT FALSE,
    provided_value TEXT,
    asked_at TIMESTAMP,                  -- 질문한 시간
    answered_at TIMESTAMP,               -- 답변 받은 시간

    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
    UNIQUE KEY (chat_id, info_type)
);
```

---

## 11. 전체 ERD (Agent 포함)

```
┌─────────────┐
│   users     │
└──────┬──────┘
       │ 1:N
       ▼
┌─────────────┐      ┌─────────────────────┐
│   chats     │─────▶│ conversation_states │
└──────┬──────┘ 1:1  └─────────────────────┘
       │
       │ 1:N
       ├──────────────────┐
       ▼                  ▼
┌─────────────┐    ┌─────────────────┐
│  messages   │    │  agent_actions  │
└──────┬──────┘    └─────────────────┘
       │ 1:1
       ▼
┌─────────────┐    ┌─────────────────────┐
│  analyses   │    │ required_info_checks│
└─────────────┘    └─────────────────────┘
```

---

## 12. Agent 구현 예시

### 12.1 정보 충분성 체크

```python
def is_info_sufficient(chat_id: int) -> bool:
    """분석에 필요한 정보가 충분한지 확인"""
    state = get_conversation_state(chat_id)

    # 필수: 성분 또는 이미지
    has_ingredients = state.ingredients and len(state.ingredients) > 0
    has_image = state.has_image

    return has_ingredients or has_image
```

### 12.2 Agent 로직

```python
def agent_step(chat_id: int, user_message: str) -> str:
    # 1. 메시지에서 정보 추출
    extracted = extract_info(user_message)
    update_conversation_state(chat_id, extracted)

    # 2. 정보 충분한지 체크
    if not is_info_sufficient(chat_id):
        # 부족한 정보 질문
        missing = get_missing_info(chat_id)
        question = generate_question(missing)

        log_agent_action(chat_id,
            thought=f"{missing} 정보가 부족함",
            action_type='ask_question',
            action_output=question
        )
        return question

    # 3. 정보 충분하면 분석 실행
    state = get_conversation_state(chat_id)

    if state.has_image:
        # 이미지 플로우
        results = image_rag_pipeline(state)
    else:
        # 텍스트 플로우
        results = text_rag_pipeline(state)

    log_agent_action(chat_id,
        thought="정보 충분, 분석 실행",
        action_type='analyze',
        action_output=results
    )

    return format_response(results)
```

### 12.3 추가 질문 예시

```python
QUESTIONS = {
    'ingredients': "제품에 어떤 성분이 들어가나요?",
    'product_type': "어떤 종류의 제품인가요? (크림, 세럼, 토너 등)",
    'usage': "제품의 주요 효능이나 용도가 무엇인가요?",
}

def generate_question(missing_info: str) -> str:
    return QUESTIONS.get(missing_info, "제품에 대해 더 자세히 설명해주세요.")
```

---

## 13. 테이블 최종 요약

| 구분 | 테이블 | 용도 |
|------|--------|------|
| 사용자 | `users` | 회원 정보 |
| 채팅 | `chats`, `messages` | 대화 기록 |
| **Agent** | `conversation_states` | 대화 상태/수집 정보 |
| **Agent** | `agent_actions` | Agent 행동 로그 |
| **Agent** | `required_info_checks` | 필요 정보 체크 |
| 분석 | `analyses`, `analysis_images`, `analysis_claims` | 분석 결과 |
| 특허 | `patents`, `claims`, `patent_images` | 특허 데이터 |
| RAG | `claim_embeddings`, `image_embeddings` | 벡터 임베딩 |

**총 14개 테이블**

---

*이 ERD v2를 기반으로 개발을 진행하시면 됩니다.*
