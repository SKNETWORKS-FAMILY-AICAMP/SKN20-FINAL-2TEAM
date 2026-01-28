# BINI 프로젝트 - ERD 설계

## 1. 기능 요구사항

### 핵심 기능
1. **회원 관리**: 회원가입, 로그인, 프로필
2. **특허 데이터**: 청구항 저장/관리
3. **채팅 기록**: 사용자별 분석 이력 저장
4. **이미지 분석**: 제품 이미지 업로드 → 침해 여부 분석
5. **RAG**: 벡터 DB로 관련 청구항 검색
6. **에이전트**: 도구 호출 기반 자동화된 분석

---

## 2. ERD 다이어그램

```
┌─────────────────┐       ┌─────────────────┐
│     users       │       │    patents      │
├─────────────────┤       ├─────────────────┤
│ PK id           │       │ PK id           │
│    email        │       │    regit_num    │
│    password     │       │    title        │
│    name         │       │    applicant    │
│    created_at   │       │    filing_date  │
│    updated_at   │       │    status       │
└────────┬────────┘       │    created_at   │
         │                └────────┬────────┘
         │                         │
         │ 1:N                     │ 1:N
         ▼                         ▼
┌─────────────────┐       ┌─────────────────┐
│     chats       │       │     claims      │
├─────────────────┤       ├─────────────────┤
│ PK id           │       │ PK id           │
│ FK user_id      │       │ FK patent_id    │
│    title        │       │    claim_number │
│    created_at   │       │    claim_text   │
│    updated_at   │       │    claim_type   │
└────────┬────────┘       │    created_at   │
         │                └─────────────────┘
         │ 1:N
         ▼
┌─────────────────┐       ┌─────────────────┐
│    messages     │       │     images      │
├─────────────────┤       ├─────────────────┤
│ PK id           │       │ PK id           │
│ FK chat_id      │       │ FK analysis_id  │
│    role         │       │    file_path    │
│    content      │       │    file_name    │
│    created_at   │       │    file_size    │
└────────┬────────┘       │    mime_type    │
         │                │    created_at   │
         │ 1:1            └─────────────────┘
         ▼                         ▲
┌─────────────────┐                │ 1:N
│    analyses     │────────────────┘
├─────────────────┤
│ PK id           │
│ FK message_id   │
│ FK patent_id    │
│ FK user_id      │
│    user_query   │
│    risk_level   │
│    result_json  │
│    analysis_type│  ← 'text' | 'image'
│    created_at   │
└─────────────────┘
```

---

## 3. 테이블 상세 설계

### 3.1 users (사용자)

| 컬럼명 | 타입 | 제약조건 | 설명 |
|--------|------|----------|------|
| id | BIGINT | PK, AUTO_INCREMENT | 사용자 ID |
| email | VARCHAR(255) | UNIQUE, NOT NULL | 이메일 (로그인용) |
| password | VARCHAR(255) | NOT NULL | 암호화된 비밀번호 |
| name | VARCHAR(100) | NOT NULL | 사용자 이름 |
| profile_image | VARCHAR(500) | NULL | 프로필 이미지 URL |
| role | ENUM | DEFAULT 'user' | 'user', 'admin' |
| created_at | TIMESTAMP | DEFAULT NOW() | 가입일 |
| updated_at | TIMESTAMP | ON UPDATE NOW() | 수정일 |

```sql
CREATE TABLE users (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    email VARCHAR(255) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    name VARCHAR(100) NOT NULL,
    profile_image VARCHAR(500),
    role ENUM('user', 'admin') DEFAULT 'user',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

---

### 3.2 patents (특허)

| 컬럼명 | 타입 | 제약조건 | 설명 |
|--------|------|----------|------|
| id | BIGINT | PK, AUTO_INCREMENT | 특허 ID |
| regit_num | VARCHAR(50) | UNIQUE, NOT NULL | 등록번호 |
| title | VARCHAR(500) | NOT NULL | 특허 제목 |
| applicant | VARCHAR(255) | NULL | 출원인 |
| filing_date | DATE | NULL | 출원일 |
| registration_date | DATE | NULL | 등록일 |
| status | ENUM | DEFAULT 'active' | 'active', 'expired', 'pending' |
| ipc_code | VARCHAR(50) | NULL | IPC 분류코드 |
| abstract | TEXT | NULL | 요약 |
| created_at | TIMESTAMP | DEFAULT NOW() | 등록일 |

```sql
CREATE TABLE patents (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    regit_num VARCHAR(50) UNIQUE NOT NULL,
    title VARCHAR(500) NOT NULL,
    applicant VARCHAR(255),
    filing_date DATE,
    registration_date DATE,
    status ENUM('active', 'expired', 'pending') DEFAULT 'active',
    ipc_code VARCHAR(50),
    abstract TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

### 3.3 claims (청구항)

| 컬럼명 | 타입 | 제약조건 | 설명 |
|--------|------|----------|------|
| id | BIGINT | PK, AUTO_INCREMENT | 청구항 ID |
| patent_id | BIGINT | FK, NOT NULL | 특허 ID |
| claim_number | INT | NOT NULL | 청구항 번호 |
| claim_text | TEXT | NOT NULL | 청구항 내용 |
| claim_type | ENUM | DEFAULT 'independent' | 'independent', 'dependent' |
| parent_claim_id | BIGINT | FK, NULL | 종속항인 경우 부모 청구항 |
| created_at | TIMESTAMP | DEFAULT NOW() | 등록일 |

```sql
CREATE TABLE claims (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    patent_id BIGINT NOT NULL,
    claim_number INT NOT NULL,
    claim_text TEXT NOT NULL,
    claim_type ENUM('independent', 'dependent') DEFAULT 'independent',
    parent_claim_id BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patent_id) REFERENCES patents(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_claim_id) REFERENCES claims(id) ON DELETE SET NULL,
    UNIQUE KEY (patent_id, claim_number)
);
```

---

### 3.4 chats (채팅방)

| 컬럼명 | 타입 | 제약조건 | 설명 |
|--------|------|----------|------|
| id | BIGINT | PK, AUTO_INCREMENT | 채팅방 ID |
| user_id | BIGINT | FK, NOT NULL | 사용자 ID |
| title | VARCHAR(255) | NULL | 채팅방 제목 (자동 생성) |
| created_at | TIMESTAMP | DEFAULT NOW() | 생성일 |
| updated_at | TIMESTAMP | ON UPDATE NOW() | 마지막 활동 |

```sql
CREATE TABLE chats (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    title VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

---

### 3.5 messages (메시지)

| 컬럼명 | 타입 | 제약조건 | 설명 |
|--------|------|----------|------|
| id | BIGINT | PK, AUTO_INCREMENT | 메시지 ID |
| chat_id | BIGINT | FK, NOT NULL | 채팅방 ID |
| role | ENUM | NOT NULL | 'user', 'assistant', 'system' |
| content | TEXT | NOT NULL | 메시지 내용 |
| created_at | TIMESTAMP | DEFAULT NOW() | 작성 시간 |

```sql
CREATE TABLE messages (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    chat_id BIGINT NOT NULL,
    role ENUM('user', 'assistant', 'system') NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
);
```

---

### 3.6 analyses (분석 결과)

| 컬럼명 | 타입 | 제약조건 | 설명 |
|--------|------|----------|------|
| id | BIGINT | PK, AUTO_INCREMENT | 분석 ID |
| message_id | BIGINT | FK, NULL | 연결된 메시지 |
| user_id | BIGINT | FK, NOT NULL | 사용자 ID |
| patent_id | BIGINT | FK, NULL | 비교한 특허 |
| user_query | TEXT | NOT NULL | 사용자 입력 |
| analysis_type | ENUM | NOT NULL | 'text', 'image' |
| risk_level | ENUM | NULL | 'high', 'medium', 'low' |
| result_json | JSON | NULL | 전체 분석 결과 |
| created_at | TIMESTAMP | DEFAULT NOW() | 분석 시간 |

```sql
CREATE TABLE analyses (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    message_id BIGINT,
    user_id BIGINT NOT NULL,
    patent_id BIGINT,
    user_query TEXT NOT NULL,
    analysis_type ENUM('text', 'image') NOT NULL,
    risk_level ENUM('high', 'medium', 'low'),
    result_json JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE SET NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (patent_id) REFERENCES patents(id) ON DELETE SET NULL
);
```

---

### 3.7 images (이미지)

| 컬럼명 | 타입 | 제약조건 | 설명 |
|--------|------|----------|------|
| id | BIGINT | PK, AUTO_INCREMENT | 이미지 ID |
| analysis_id | BIGINT | FK, NOT NULL | 분석 ID |
| file_path | VARCHAR(500) | NOT NULL | 저장 경로 |
| file_name | VARCHAR(255) | NOT NULL | 원본 파일명 |
| file_size | INT | NULL | 파일 크기 (bytes) |
| mime_type | VARCHAR(50) | NULL | MIME 타입 |
| created_at | TIMESTAMP | DEFAULT NOW() | 업로드 시간 |

```sql
CREATE TABLE images (
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

---

## 4. 관계 정리

| 관계 | 설명 |
|------|------|
| users → chats | 1:N (한 사용자가 여러 채팅방) |
| chats → messages | 1:N (한 채팅방에 여러 메시지) |
| messages → analyses | 1:1 (한 메시지에 하나의 분석) |
| users → analyses | 1:N (한 사용자가 여러 분석) |
| patents → claims | 1:N (한 특허에 여러 청구항) |
| patents → analyses | 1:N (한 특허가 여러 분석에 사용) |
| analyses → images | 1:N (한 분석에 여러 이미지) |

---

## 5. 인덱스 설계

```sql
-- 자주 조회되는 컬럼에 인덱스
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_chats_user_id ON chats(user_id);
CREATE INDEX idx_messages_chat_id ON messages(chat_id);
CREATE INDEX idx_analyses_user_id ON analyses(user_id);
CREATE INDEX idx_analyses_patent_id ON analyses(patent_id);
CREATE INDEX idx_claims_patent_id ON claims(patent_id);
CREATE INDEX idx_patents_regit_num ON patents(regit_num);
```

---

## 6. 예시 데이터 흐름

### 6.1 텍스트 분석 플로우

```
1. 사용자 로그인 (users)
2. 새 채팅 시작 (chats 생성)
3. 제품 설명 입력 (messages - role: user)
4. AI 분석 실행 (analyses 생성)
5. 결과 반환 (messages - role: assistant)
```

### 6.2 이미지 분석 플로우

```
1. 사용자 로그인 (users)
2. 이미지 업로드 (images 저장)
3. 분석 요청 (analyses - type: image)
4. AI가 이미지 분석
5. 결과 반환 (result_json에 저장)
```

---

## 7. API 엔드포인트 (예시)

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | /api/auth/register | 회원가입 |
| POST | /api/auth/login | 로그인 |
| GET | /api/chats | 채팅 목록 조회 |
| POST | /api/chats | 새 채팅 생성 |
| GET | /api/chats/:id/messages | 메시지 조회 |
| POST | /api/analyses/text | 텍스트 분석 |
| POST | /api/analyses/image | 이미지 분석 |
| GET | /api/patents | 특허 목록 |
| POST | /api/patents | 특허 등록 |
| GET | /api/patents/:id/claims | 청구항 조회 |

---

## 8. 확장 고려사항

### 8.1 추후 추가 가능한 테이블

```
- user_subscriptions: 구독/결제 정보
- patent_bookmarks: 특허 북마크
- analysis_feedback: 분석 결과 피드백
- notifications: 알림
```

### 8.2 성능 최적화

- 분석 결과 캐싱 (Redis)
- 이미지 CDN 저장
- 읽기/쓰기 DB 분리

---

---

## 9. RAG 시스템 테이블

### 9.1 아키텍처 개요

```
사용자 질문
     │
     ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Agent     │───▶│  RAG 검색   │───▶│  Vector DB  │
│  (오케스트라)│    │  (Retriever)│    │ (Embedding) │
└──────┬──────┘    └─────────────┘    └─────────────┘
       │                                     │
       │           ┌─────────────┐           │
       └──────────▶│  LLM 분석   │◀──────────┘
                   │ (Generator) │    관련 청구항
                   └─────────────┘
```

### 9.2 claim_embeddings (청구항 벡터)

| 컬럼명 | 타입 | 제약조건 | 설명 |
|--------|------|----------|------|
| id | BIGINT | PK | 임베딩 ID |
| claim_id | BIGINT | FK, UNIQUE | 청구항 ID |
| embedding | VECTOR(1536) | NOT NULL | 임베딩 벡터 |
| model_name | VARCHAR(100) | NOT NULL | 임베딩 모델명 |
| created_at | TIMESTAMP | DEFAULT NOW() | 생성일 |

```sql
-- PostgreSQL + pgvector 사용 시
CREATE TABLE claim_embeddings (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    claim_id BIGINT UNIQUE NOT NULL,
    embedding VECTOR(1536) NOT NULL,  -- OpenAI ada-002 기준
    model_name VARCHAR(100) NOT NULL DEFAULT 'text-embedding-ada-002',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (claim_id) REFERENCES claims(id) ON DELETE CASCADE
);

-- 벡터 검색용 인덱스
CREATE INDEX idx_claim_embedding ON claim_embeddings
USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

### 9.3 rag_retrievals (RAG 검색 기록)

| 컬럼명 | 타입 | 제약조건 | 설명 |
|--------|------|----------|------|
| id | BIGINT | PK | 검색 ID |
| analysis_id | BIGINT | FK | 분석 ID |
| query_text | TEXT | NOT NULL | 검색 쿼리 |
| query_embedding | VECTOR(1536) | NULL | 쿼리 임베딩 |
| top_k | INT | DEFAULT 5 | 검색 개수 |
| created_at | TIMESTAMP | DEFAULT NOW() | 검색 시간 |

```sql
CREATE TABLE rag_retrievals (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    analysis_id BIGINT NOT NULL,
    query_text TEXT NOT NULL,
    query_embedding VECTOR(1536),
    top_k INT DEFAULT 5,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE
);
```

### 9.4 retrieval_results (검색 결과)

| 컬럼명 | 타입 | 제약조건 | 설명 |
|--------|------|----------|------|
| id | BIGINT | PK | 결과 ID |
| retrieval_id | BIGINT | FK | 검색 ID |
| claim_id | BIGINT | FK | 매칭된 청구항 |
| similarity_score | FLOAT | NOT NULL | 유사도 점수 |
| rank | INT | NOT NULL | 순위 |

```sql
CREATE TABLE retrieval_results (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    retrieval_id BIGINT NOT NULL,
    claim_id BIGINT NOT NULL,
    similarity_score FLOAT NOT NULL,
    rank INT NOT NULL,
    FOREIGN KEY (retrieval_id) REFERENCES rag_retrievals(id) ON DELETE CASCADE,
    FOREIGN KEY (claim_id) REFERENCES claims(id) ON DELETE CASCADE
);
```

---

## 10. 에이전트 시스템 테이블

### 10.1 에이전트 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│                      Agent                              │
├─────────────────────────────────────────────────────────┤
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐    │
│  │ RAG     │  │ 이미지  │  │ 침해    │  │ 리포트  │    │
│  │ 검색    │  │ 분석    │  │ 판단    │  │ 생성    │    │
│  │ Tool    │  │ Tool    │  │ Tool    │  │ Tool    │    │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘    │
└─────────────────────────────────────────────────────────┘
```

### 10.2 agent_sessions (에이전트 세션)

| 컬럼명 | 타입 | 제약조건 | 설명 |
|--------|------|----------|------|
| id | BIGINT | PK | 세션 ID |
| chat_id | BIGINT | FK | 채팅방 ID |
| user_id | BIGINT | FK | 사용자 ID |
| status | ENUM | NOT NULL | 'running', 'completed', 'failed' |
| started_at | TIMESTAMP | DEFAULT NOW() | 시작 시간 |
| ended_at | TIMESTAMP | NULL | 종료 시간 |

```sql
CREATE TABLE agent_sessions (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    chat_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    status ENUM('running', 'completed', 'failed', 'cancelled') DEFAULT 'running',
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP NULL,
    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

### 10.3 agent_tools (에이전트 도구 정의)

| 컬럼명 | 타입 | 제약조건 | 설명 |
|--------|------|----------|------|
| id | BIGINT | PK | 도구 ID |
| name | VARCHAR(100) | UNIQUE | 도구 이름 |
| description | TEXT | NOT NULL | 도구 설명 |
| parameters_schema | JSON | NULL | 파라미터 스키마 |
| is_active | BOOLEAN | DEFAULT TRUE | 활성화 여부 |

```sql
CREATE TABLE agent_tools (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT NOT NULL,
    parameters_schema JSON,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 초기 도구 등록
INSERT INTO agent_tools (name, description, parameters_schema) VALUES
('search_claims', '관련 특허 청구항을 RAG로 검색', '{"query": "string", "top_k": "integer"}'),
('analyze_text', '텍스트 기반 침해 분석', '{"product_desc": "string", "claim_id": "integer"}'),
('analyze_image', '이미지 기반 침해 분석', '{"image_id": "integer", "claim_id": "integer"}'),
('generate_report', '분석 리포트 생성', '{"analysis_id": "integer"}');
```

### 10.4 tool_calls (도구 호출 기록)

| 컬럼명 | 타입 | 제약조건 | 설명 |
|--------|------|----------|------|
| id | BIGINT | PK | 호출 ID |
| session_id | BIGINT | FK | 세션 ID |
| tool_id | BIGINT | FK | 도구 ID |
| input_params | JSON | NOT NULL | 입력 파라미터 |
| output_result | JSON | NULL | 출력 결과 |
| status | ENUM | NOT NULL | 'pending', 'success', 'error' |
| execution_time_ms | INT | NULL | 실행 시간 (ms) |
| created_at | TIMESTAMP | DEFAULT NOW() | 호출 시간 |

```sql
CREATE TABLE tool_calls (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    session_id BIGINT NOT NULL,
    tool_id BIGINT NOT NULL,
    input_params JSON NOT NULL,
    output_result JSON,
    status ENUM('pending', 'success', 'error') DEFAULT 'pending',
    error_message TEXT,
    execution_time_ms INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES agent_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (tool_id) REFERENCES agent_tools(id)
);
```

### 10.5 agent_steps (에이전트 추론 단계)

| 컬럼명 | 타입 | 제약조건 | 설명 |
|--------|------|----------|------|
| id | BIGINT | PK | 단계 ID |
| session_id | BIGINT | FK | 세션 ID |
| step_number | INT | NOT NULL | 단계 번호 |
| thought | TEXT | NULL | 에이전트 사고 과정 |
| action | VARCHAR(100) | NULL | 선택한 액션 |
| tool_call_id | BIGINT | FK | 도구 호출 ID |
| observation | TEXT | NULL | 도구 실행 결과 관찰 |
| created_at | TIMESTAMP | DEFAULT NOW() | 생성 시간 |

```sql
CREATE TABLE agent_steps (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    session_id BIGINT NOT NULL,
    step_number INT NOT NULL,
    thought TEXT,
    action VARCHAR(100),
    tool_call_id BIGINT,
    observation TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES agent_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (tool_call_id) REFERENCES tool_calls(id)
);
```

---

## 11. 전체 ERD (RAG + Agent 포함)

```
┌─────────────┐
│   users     │
└──────┬──────┘
       │ 1:N
       ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   chats     │────▶│  messages   │     │agent_sessions│
└──────┬──────┘ 1:N └──────┬──────┘     └──────┬──────┘
       │                   │ 1:1              │ 1:N
       │                   ▼                  ▼
       │            ┌─────────────┐    ┌─────────────┐
       │            │  analyses   │    │ agent_steps │
       │            └──────┬──────┘    └──────┬──────┘
       │                   │                  │
       │                   │           ┌──────▼──────┐
       │                   │           │ tool_calls  │
       │                   │           └──────┬──────┘
       │                   │                  │
       │                   ▼                  ▼
       │            ┌─────────────┐    ┌─────────────┐
       │            │   images    │    │ agent_tools │
       │            └─────────────┘    └─────────────┘
       │
       │            ┌─────────────┐     ┌─────────────┐
       │            │  patents    │────▶│   claims    │
       │            └─────────────┘ 1:N └──────┬──────┘
       │                                       │ 1:1
       │            ┌─────────────┐            ▼
       └───────────▶│rag_retrievals│    ┌─────────────┐
                    └──────┬──────┘    │claim_embeddings│
                           │ 1:N       └─────────────┘
                           ▼
                    ┌─────────────┐
                    │retrieval_results│
                    └─────────────┘
```

---

## 12. 데이터 흐름 (RAG + Agent)

### 12.1 전체 플로우

```
1. 사용자 입력 (텍스트 or 이미지)
              │
              ▼
2. Agent 세션 시작 (agent_sessions)
              │
              ▼
3. Agent 사고 (agent_steps - thought)
              │
              ▼
4. Tool 선택: search_claims
              │
              ▼
5. RAG 검색 (rag_retrievals)
   - 쿼리 임베딩 생성
   - 벡터 유사도 검색
   - 상위 K개 청구항 반환 (retrieval_results)
              │
              ▼
6. Tool 선택: analyze_text or analyze_image
              │
              ▼
7. LLM 분석 (analyses)
   - 청구항 vs 제품 비교
   - risk_level 판단
              │
              ▼
8. Tool 선택: generate_report
              │
              ▼
9. 결과 반환 (messages - role: assistant)
```

### 12.2 RAG 검색 상세

```sql
-- 유사한 청구항 검색 쿼리 예시
SELECT
    c.id,
    c.claim_text,
    p.regit_num,
    p.title,
    1 - (ce.embedding <=> query_embedding) as similarity
FROM claim_embeddings ce
JOIN claims c ON ce.claim_id = c.id
JOIN patents p ON c.patent_id = p.id
ORDER BY ce.embedding <=> query_embedding
LIMIT 5;
```

---

## 13. 기술 스택 추천

| 구분 | 기술 | 용도 |
|------|------|------|
| **Vector DB** | PostgreSQL + pgvector | 청구항 임베딩 저장/검색 |
| | 또는 Pinecone/Weaviate | 전용 벡터 DB |
| **Embedding** | OpenAI ada-002 | 텍스트 임베딩 |
| | 또는 SBERT (한국어) | 로컬 임베딩 |
| **Agent Framework** | LangChain | 에이전트 오케스트레이션 |
| | 또는 LlamaIndex | RAG 특화 |
| **LLM** | Fine-tuned Gemma 1B | 침해 분석 |
| | GPT-4 Vision | 이미지 분석 |

---

## 14. 에이전트 도구 상세

### 14.1 search_claims (RAG 검색)
```python
def search_claims(query: str, top_k: int = 5) -> List[Claim]:
    """
    사용자 제품 설명으로 관련 청구항 검색

    1. query를 임베딩
    2. claim_embeddings에서 유사도 검색
    3. 상위 top_k개 반환
    """
    pass
```

### 14.2 analyze_text (텍스트 분석)
```python
def analyze_text(product_desc: str, claim_id: int) -> AnalysisResult:
    """
    Fine-tuned 모델로 침해 분석

    1. 청구항 조회
    2. 프롬프트 생성
    3. 모델 추론
    4. JSON 결과 반환
    """
    pass
```

### 14.3 analyze_image (이미지 분석)
```python
def analyze_image(image_id: int, claim_id: int) -> AnalysisResult:
    """
    이미지 기반 침해 분석

    1. 이미지 로드
    2. Vision 모델로 제품 특징 추출
    3. 청구항과 비교
    4. 결과 반환
    """
    pass
```

### 14.4 generate_report (리포트 생성)
```python
def generate_report(analysis_id: int) -> Report:
    """
    분석 결과를 리포트로 정리

    1. 분석 결과 조회
    2. 마크다운/PDF 리포트 생성
    3. 저장 및 반환
    """
    pass
```

---

*이 ERD를 기반으로 개발을 진행하시면 됩니다.*
