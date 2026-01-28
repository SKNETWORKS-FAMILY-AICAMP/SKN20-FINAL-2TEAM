# BINI 프로젝트 - ERD (최종)

## 1. 시스템 개요

### 1.1 서비스 목표
**상품 출시 전 특허 침해 여부 사전 검증 서비스**

### 1.2 핵심 플로우

```
┌─────────────────────────────────────────────────────────┐
│              로그인 필수 (비로그인 사용 불가)              │
└────────────────────────┬────────────────────────────────┘
                         │
                    사용자 입력
                         │
           ┌─────────────┴─────────────┐
           ▼                           ▼
    ┌─────────────┐             ┌─────────────┐
    │ 이미지 입력  │             │ 텍스트 입력  │
    └──────┬──────┘             └──────┬──────┘
           │                           │
           ▼                           ▼
    ┌─────────────┐             ┌─────────────┐
    │로카르노 분류 │             │ Key값 추출  │
    │ (자동)      │             │             │
    └──────┬──────┘             └──────┬──────┘
           │                           │
           ▼                           ▼
    ┌─────────────┐             ┌─────────────┐
    │ 이미지 RAG  │             │ 청구항 RAG  │
    │ (Top 20)    │             │             │
    └──────┬──────┘             └──────┬──────┘
           │                           │
           ▼                           ▼
    ┌─────────────┐             ┌─────────────┐
    │ 유사도 모델  │             │  Rerank    │
    │ (학습된)    │             │             │
    └──────┬──────┘             └──────┬──────┘
           │                           │
           ▼                           ▼
    ┌─────────────┐             ┌─────────────┐
    │  LLM 답변   │             │ sLLM 답변   │
    └──────┬──────┘             └──────┬──────┘
           │                           │
           └───────────┬───────────────┘
                       ▼
              ┌─────────────────┐
              │  채팅 기록 저장  │
              │  (사용자별)      │
              └─────────────────┘
```

---

## 2. ERD 다이어그램

```
═══════════════════════════════════════════════════════════
                     사용자 & 채팅
═══════════════════════════════════════════════════════════

┌─────────────────┐
│     users       │
├─────────────────┤
│ PK id           │
│    email        │
│    password     │
│    name         │
│    created_at   │
└────────┬────────┘
         │ 1:N
         ▼
┌─────────────────┐
│     chats       │
├─────────────────┤
│ PK id           │
│ FK user_id      │
│    title        │
│    created_at   │
│    updated_at   │
└────────┬────────┘
         │ 1:N
         ▼
┌─────────────────┐
│    messages     │
├─────────────────┤
│ PK id           │
│ FK chat_id      │
│    role         │  ← 'user' | 'assistant'
│    content      │
│    message_type │  ← 'text' | 'image'
│    created_at   │
└────────┬────────┘
         │ 1:1 (user 메시지만)
         ▼
┌─────────────────┐
│    analyses     │
├─────────────────┤
│ PK id           │
│ FK message_id   │
│    input_type   │  ← 'text' | 'image'
│    risk_level   │  ← 'high' | 'medium' | 'low'
│    result_json  │
│    model_used   │
│    created_at   │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌────────┐ ┌────────────────┐
│ 이미지  │ │ 텍스트 분석     │
│ 분석   │ │                │
└────────┘ └────────────────┘


═══════════════════════════════════════════════════════════
                  이미지 분석 관련
═══════════════════════════════════════════════════════════

┌─────────────────┐
│ analysis_images │  ← 사용자가 올린 이미지
├─────────────────┤
│ PK id           │
│ FK analysis_id  │
│    file_path    │
│    file_name    │
│    locarno_class│  ← 자동 분류된 로카르노 코드
│    created_at   │
└─────────────────┘

┌─────────────────┐
│ image_matches   │  ← RAG + 유사도 모델 결과
├─────────────────┤
│ PK id           │
│ FK analysis_id  │
│ FK design_patent_id │
│    rag_score    │  ← RAG 유사도
│    model_score  │  ← 학습 모델 유사도
│    is_similar   │  ← 최종 판정
│    rank         │
└─────────────────┘


═══════════════════════════════════════════════════════════
                  텍스트 분석 관련
═══════════════════════════════════════════════════════════

┌─────────────────┐
│analysis_keywords│  ← 추출된 키워드
├─────────────────┤
│ PK id           │
│ FK analysis_id  │
│    keyword      │
│    importance   │
└─────────────────┘

┌─────────────────┐
│ claim_matches   │  ← RAG + Rerank 결과
├─────────────────┤
│ PK id           │
│ FK analysis_id  │
│ FK claim_id     │
│    rag_score    │  ← RAG 유사도
│    rerank_score │  ← Rerank 점수
│    match_result │  ← 'match' | 'no_match' | 'uncertain'
│    rank         │
└─────────────────┘


═══════════════════════════════════════════════════════════
                  특허 데이터 (RAG 대상)
═══════════════════════════════════════════════════════════

┌─────────────────┐
│ design_patents  │  ← 디자인 특허 (이미지용)
├─────────────────┤
│ PK id           │
│    regit_num    │
│    title        │
│    locarno_class│
│    applicant    │
│    image_path   │
│    created_at   │
└────────┬────────┘
         │ 1:1
         ▼
┌─────────────────┐
│ design_embeddings│ ← 이미지 임베딩
├─────────────────┤
│ FK design_patent_id │
│    embedding    │
│    model_name   │
└─────────────────┘


┌─────────────────┐
│    patents      │  ← 일반 특허 (텍스트용)
├─────────────────┤
│ PK id           │
│    regit_num    │
│    title        │
│    applicant    │
│    ipc_code     │
│    created_at   │
└────────┬────────┘
         │ 1:N
         ▼
┌─────────────────┐
│     claims      │  ← 청구항
├─────────────────┤
│ PK id           │
│ FK patent_id    │
│    claim_number │
│    claim_text   │
│    claim_type   │
└────────┬────────┘
         │ 1:1
         ▼
┌─────────────────┐
│claim_embeddings │  ← 텍스트 임베딩
├─────────────────┤
│ FK claim_id     │
│    embedding    │
│    model_name   │
└─────────────────┘
```

---

## 3. 테이블 상세

### 3.1 users (사용자) - 로그인 필수

```sql
CREATE TABLE users (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    email VARCHAR(255) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

### 3.2 chats (채팅방)

```sql
CREATE TABLE chats (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    title VARCHAR(255),
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
    role ENUM('user', 'assistant') NOT NULL,
    content TEXT NOT NULL,
    message_type ENUM('text', 'image') DEFAULT 'text',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
    INDEX idx_chat_id (chat_id)
);
```

### 3.4 analyses (분석 결과)

```sql
CREATE TABLE analyses (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    message_id BIGINT UNIQUE NOT NULL,
    input_type ENUM('text', 'image') NOT NULL,
    risk_level ENUM('high', 'medium', 'low'),
    result_json JSON,
    model_used VARCHAR(100),
    processing_time_ms INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
);
```

### 3.5 analysis_images (분석용 이미지)

```sql
CREATE TABLE analysis_images (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    analysis_id BIGINT NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    locarno_class VARCHAR(20),  -- 자동 분류된 로카르노 코드
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
);
```

### 3.6 image_matches (이미지 매칭 결과)

```sql
CREATE TABLE image_matches (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    analysis_id BIGINT NOT NULL,
    design_patent_id BIGINT NOT NULL,
    rag_score FLOAT,           -- RAG 유사도
    model_score FLOAT,         -- 학습된 유사도 모델 점수
    is_similar BOOLEAN,        -- 최종 유사 판정
    rank INT,
    FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE,
    FOREIGN KEY (design_patent_id) REFERENCES design_patents(id)
);
```

### 3.7 analysis_keywords (추출된 키워드)

```sql
CREATE TABLE analysis_keywords (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    analysis_id BIGINT NOT NULL,
    keyword VARCHAR(255) NOT NULL,
    importance FLOAT,  -- 중요도 점수
    FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
);
```

### 3.8 claim_matches (청구항 매칭 결과)

```sql
CREATE TABLE claim_matches (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    analysis_id BIGINT NOT NULL,
    claim_id BIGINT NOT NULL,
    rag_score FLOAT,
    rerank_score FLOAT,
    match_result ENUM('match', 'no_match', 'uncertain'),
    rank INT,
    FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE,
    FOREIGN KEY (claim_id) REFERENCES claims(id)
);
```

### 3.9 design_patents (디자인 특허)

```sql
CREATE TABLE design_patents (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    regit_num VARCHAR(50) UNIQUE NOT NULL,
    title VARCHAR(500) NOT NULL,
    locarno_class VARCHAR(20),  -- 로카르노 분류
    applicant VARCHAR(255),
    image_path VARCHAR(500),
    filing_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_locarno (locarno_class)
);
```

### 3.10 design_embeddings (디자인 이미지 임베딩)

```sql
CREATE TABLE design_embeddings (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    design_patent_id BIGINT UNIQUE NOT NULL,
    embedding VECTOR(512),  -- CLIP 등
    model_name VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (design_patent_id) REFERENCES design_patents(id) ON DELETE CASCADE
);
```

### 3.11 patents (일반 특허)

```sql
CREATE TABLE patents (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    regit_num VARCHAR(50) UNIQUE NOT NULL,
    title VARCHAR(500) NOT NULL,
    applicant VARCHAR(255),
    ipc_code VARCHAR(50),
    abstract TEXT,
    filing_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 3.12 claims (청구항)

```sql
CREATE TABLE claims (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    patent_id BIGINT NOT NULL,
    claim_number INT NOT NULL,
    claim_text TEXT NOT NULL,
    claim_type ENUM('independent', 'dependent') DEFAULT 'independent',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patent_id) REFERENCES patents(id) ON DELETE CASCADE,
    UNIQUE KEY (patent_id, claim_number)
);
```

### 3.13 claim_embeddings (청구항 임베딩)

```sql
CREATE TABLE claim_embeddings (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    claim_id BIGINT UNIQUE NOT NULL,
    embedding VECTOR(1536),
    model_name VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (claim_id) REFERENCES claims(id) ON DELETE CASCADE
);
```

---

## 4. 테이블 요약

| 구분 | 테이블 | 용도 |
|------|--------|------|
| 사용자 | `users` | 회원 (로그인 필수) |
| 채팅 | `chats` | 채팅방 |
| | `messages` | 메시지 |
| 분석 | `analyses` | 분석 결과 |
| | `analysis_images` | 업로드 이미지 + 로카르노 |
| | `analysis_keywords` | 추출된 키워드 |
| | `image_matches` | 이미지 RAG + 유사도 결과 |
| | `claim_matches` | 청구항 RAG + Rerank 결과 |
| 디자인특허 | `design_patents` | 디자인 특허 정보 |
| | `design_embeddings` | 이미지 벡터 |
| 일반특허 | `patents` | 특허 정보 |
| | `claims` | 청구항 |
| | `claim_embeddings` | 텍스트 벡터 |

**총 13개 테이블**

---

## 5. 데이터 플로우 상세

### 5.1 이미지 입력 플로우

```
1. 사용자 이미지 업로드
         │
         ▼
2. 로카르노 분류 모델 → locarno_class 저장
         │
         ▼
3. 같은 locarno_class의 design_patents에서 RAG 검색 (Top 20)
         │
         ▼
4. 유사도 모델로 각각 점수 계산 (model_score)
         │
         ▼
5. 임계값 이상인 것만 필터링 → is_similar = true
         │
         ▼
6. LLM이 결과 기반으로 답변 생성
         │
         ▼
7. 저장: analyses, analysis_images, image_matches
```

### 5.2 텍스트 입력 플로우

```
1. 사용자 텍스트 입력
         │
         ▼
2. 키워드 추출 → analysis_keywords 저장
         │
         ▼
3. 키워드로 claims에서 RAG 검색
         │
         ▼
4. Reranker로 재정렬 → rerank_score
         │
         ▼
5. sLLM이 청구항 비교 분석 → match_result
         │
         ▼
6. 저장: analyses, analysis_keywords, claim_matches
```

---

## 6. API 설계

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | `/api/auth/register` | 회원가입 |
| POST | `/api/auth/login` | 로그인 |
| GET | `/api/chats` | 내 채팅 목록 |
| POST | `/api/chats` | 새 채팅 |
| GET | `/api/chats/:id` | 채팅 상세 |
| DELETE | `/api/chats/:id` | 채팅 삭제 |
| POST | `/api/analyze/image` | 이미지 분석 |
| POST | `/api/analyze/text` | 텍스트 분석 |

---

*이 ERD를 기반으로 개발을 진행합니다.*
