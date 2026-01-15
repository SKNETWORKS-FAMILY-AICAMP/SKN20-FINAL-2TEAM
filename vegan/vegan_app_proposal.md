# 비건 라이프 큐레이션 앱 기획서
**VeganLife Curator - Agent 기반 AI 서비스**

---

## 1. 프로젝트 개요

### 1.1 서비스 컨셉
비건/베지테리언 사용자를 위한 AI 기반 라이프 큐레이션 플랫폼

### 1.2 핵심 가치
- **3초 이내 판단**: 음식 사진 또는 성분표를 스캔하면 즉시 비건 여부 판단
- **개인화된 큐레이션**: 사용자의 비건 단계(7단계)에 맞춘 맞춤형 추천
- **신뢰성**: RAG 기반 한국 공식 데이터 소스 검증

### 1.3 타겟 사용자
- 비건/베지테리언 입문자 (Level 5-7)
- Regular Vegan (Level 3-4)
- Strict Vegan (Level 1-2)

---

## 2. 핵심 기능

### 2.1 VeganScan (음식/성분 스캔)
**사용자 플로우**
```
음식 사진 촬영 → AI 분석 (3초 이내) → 결과 + 대체 상품 추천
```

**주요 기능**
- 음식 사진 비건 판단
- 영양성분표 OCR 스캔
- 성분별 상세 분석
- 대체 식품 추천

### 2.2 Chatbot (영양 상담)
- 비건 식단 관련 질문 응답
- 개인화된 영양 조언
- 식당 정보 제공

### 2.3 Recipe (냉장고 스캔 & 레시피 추천)
- 냉장고 재료 인식
- 비건 레시피 생성
- 부족한 영양소 보충 제안

### 2.4 식당 찾기
- 현위치 기반 비건 식당 검색
- 메뉴별 비건 여부 확인

### 2.5 마이페이지
- 식단 기록 및 영양 대시보드
- 비건 여정 추적 (시작일, 진행률)
- 커뮤니티 배지 시스템

---

## 3. Agent 아키텍처 설계

### 3.1 전체 구조
```
User Request
    ↓
[Master Agent] - 전체 워크플로우 조율
    ↓
[Specialized Agents] - 각 도메인별 전문 처리
    ↓
Response to User
```

### 3.2 Agent 목록 및 역할

#### **Master Agent (AgentOrchestrator)**
- **역할**: 전체 시스템의 두뇌, 워크플로우 조율
- **책임**:
  - 사용자 요청 분석 및 적절한 Agent 호출
  - Agent 간 데이터 전달 및 순서 관리
  - 최종 응답 생성 및 에러 핸들링

#### **Vision Agent (GPT-4 Vision 기반)**
- **역할**: 음식 이미지 분석
- **Input**: 사용자가 업로드한 음식 사진
- **Process**:
  - GPT-4 Vision API 호출
  - 음식 종류 식별
  - 가능한 성분 추정
- **Output**: 음식명 + 추정 성분 리스트

#### **Image Agent (냉장고/레시피용)**
- **역할**: 냉장고 재료 인식
- **Input**: 냉장고 사진
- **Process**:
  - 여러 식재료 동시 인식
  - 수량 및 상태 판단
- **Output**: 재료 리스트 + 수량

#### **OCR Agent**
- **역할**: 영양성분표 텍스트 추출
- **Input**: 제품 성분표 이미지
- **Process**:
  - Google Cloud Vision OCR
  - 텍스트 정제 (노이즈 제거, 줄바꿈 처리)
- **Output**: 추출된 성분 텍스트

#### **GPT-4 Vision API Agent**
- **역할**: 성분표 직접 해석
- **Input**: 성분표 이미지
- **Process**:
  - Vision API로 성분 직접 추출
  - OCR Agent 결과와 Cross-validation
- **Output**: 성분 리스트

#### **Safety Agent**
- **역할**: 1차 안전성 검증
- **Input**: 추출된 성분 리스트
- **Process**:
  - 명확한 동물성 성분 필터링 (젤라틴, 우유, 계란 등)
  - 위험 성분 감지 (알레르기 유발 물질)
- **Output**: SAFE / WARNING / REJECT

#### **Vegan Level Agent**
- **역할**: 사용자 비건 단계별 판단
- **Input**: 
  - 성분 리스트
  - 사용자 비건 레벨 (1~7)
- **Process**:
  - Rule-based 판단 (Level 1-2: 엄격)
  - LLM 기반 유연한 판단 (Level 5-7)
- **Output**: OK / CAUTION / NOT_VEGAN

**비건 레벨 정의**
| Level | 유형 | 판단 기준 |
|-------|------|-----------|
| 1-2 | Strict Vegan | 모든 동물성 성분 거부 |
| 3-4 | Regular Vegan | 주요 동물성 거부, 첨가물 케이스별 판단 |
| 5-6 | Flexitarian | 육류 거부, 유제품/계란 일부 허용 |
| 7 | Beginner | 점진적 전환, 대부분 허용 |

#### **RAG System Agent (Knowledge Retrieval)**
- **역할**: 한국 데이터 소스 기반 성분 검증
- **Input**: 성분명 (한글/영문)
- **Process**:
  1. VectorDB 검색 (유사 성분 임베딩)
  2. Keyword 검색 (정확한 매칭)
  3. Reranking (신뢰도 기반)
- **Output**: 검증된 성분 정보 + 신뢰도 + 출처

**데이터 소스 (신뢰도 계층)**
- Tier 1 (1.0): 한국비건인증원, 식약처
- Tier 2 (0.8): 한국채식연합, 대형 유통사
- Tier 3 (0.6): 커뮤니티 피드백

#### **FAISS Vector DB Agent**
- **역할**: 벡터 검색 전담
- **Input**: 성분 임베딩 쿼리
- **Process**:
  - FAISS 인덱스 검색
  - Top-K 유사 성분 추출
- **Output**: 유사 성분 리스트 + 스코어

#### **Product Agent**
- **역할**: 대체 상품 추천
- **Input**: 
  - NOT_VEGAN으로 판정된 성분
  - 사용자 선호도
- **Process**:
  - VectorDB에서 비건 대체 상품 검색
  - 사용자 구매 이력 기반 필터링
- **Output**: 대체 상품 리스트 (3~5개)

#### **Recipe Agent**
- **역할**: 비건 레시피 생성
- **Input**: 
  - 사용자가 가진 재료 (냉장고 스캔 결과)
  - 부족한 영양소 정보
- **Process**:
  - LLM 기반 레시피 생성
  - 영양소 균형 검증
- **Output**: 레시피 텍스트 + 영양 정보

#### **Vegan-Level-Agent (Chatbot용)**
- **역할**: 대화형 비건 상담
- **Input**: 사용자 질문 (자연어)
- **Process**:
  - 의도 분류 (성분 질문 / 식당 추천 / 영양 상담)
  - RAG Agent 호출 (필요 시)
  - 개인화된 응답 생성
- **Output**: 대화형 응답

#### **Nutrition Agent**
- **역할**: 영양 분석 및 조언
- **Input**: 사용자 식단 기록
- **Process**:
  - 일일 영양소 섭취량 계산
  - 부족/과다 영양소 식별
  - 개선 제안
- **Output**: 영양 대시보드 데이터

#### **PostgreSQL Agent**
- **역할**: 사용자 데이터 관리
- **책임**:
  - 사용자 프로필 CRUD
  - 스캔 히스토리 저장
  - 식단 기록 관리

---

## 4. 주요 워크플로우 (Sequence Diagram 기반)

### 4.1 VeganScan 플로우
```
Step 1: 사진 업로드 (User → Frontend)
  ↓
Step 2: 이미지 분석 (Master Agent → Vision/OCR Agent)
  - GPT-4 Vision 분석 OR OCR 추출
  ↓
Step 3: 성분 추출 (Master Agent → GPT-4 Vision API)
  - 구조화된 성분 리스트 생성
  ↓
Step 4: 지식 검색 (Master Agent → RAG System)
  - VectorDB 검색 → FAISS Agent
  - 각 성분별 비건 여부 검증
  ↓
Step 5: 안전성 검증 (3초 이내 목표)
  - Safety Agent: 1차 필터링
  - Vegan Level Agent: 사용자 레벨별 판단
  ↓
Step 6: 결과 출력
  - ✅ VEGAN FRIENDLY (초록불)
  - ⚠️ CAUTION (노란불 - 유제품 포함 등)
  - ❌ NOT VEGAN (빨간불 - 유청 단백 등)
  - 대체 상품 추천 (Product Agent)
```

### 4.2 Chatbot 플로우
```
User 질문 → Master Agent → Vegan-Level-Agent
  ↓ (필요시)
RAG System → 지식 검색
  ↓
Nutrition Agent → 영양 정보 추가
  ↓
응답 생성 → User
```

### 4.3 Recipe 플로우
```
냉장고 사진 → Image Agent → 재료 리스트
  ↓
Master Agent → Recipe Agent
  ↓ (영양 확인)
Nutrition Agent → 부족 영양소 식별
  ↓
Recipe Agent → 레시피 생성 (LLM)
  ↓
User에게 레시피 + 추가 재료 제안
```

---

## 5. 기술 스택

### 5.1 AI/LLM
- **GPT-4 Vision**: 이미지 분석
- **GPT-4**: LLM 추론 및 대화
- **Google Cloud Vision**: OCR 백업
- **Sentence Transformers**: 임베딩 (ko-sbert 고려)

### 5.2 Backend
- **FastAPI**: API 서버
- **LangChain/LangGraph**: Agent 오케스트레이션
- **Celery**: 비동기 작업 큐

### 5.3 Database
- **PostgreSQL**: 사용자 데이터, 스캔 히스토리
- **FAISS**: VectorDB (Self-hosted 옵션)
  - 대안: Pinecone (Managed)
- **Redis**: 캐싱, 세션

### 5.4 Frontend
- **React Native**: 모바일 앱
- **TailwindCSS**: UI 스타일링

---

## 6. RAG 시스템 상세

### 6.1 데이터 수집
- 한국비건인증원 공식 제품 리스트
- 식약처 식품첨가물 DB
- 한국채식연합 가이드라인
- 쿠팡/마켓컬리 제품 크롤링

### 6.2 임베딩 & 벡터 DB
```
성분명 → Embedding Model → 1536차원 벡터 → FAISS Index
```

### 6.3 검색 전략
- **Hybrid Search**: Vector Search + Keyword Search
- **Reranking**: 신뢰도 가중치 적용
- **LLM Verification**: 최종 판단은 GPT-4에 위임

---

## 7. 차별화 포인트

### 7.1 3초 이내 판단
- 사전 캐싱 (Redis)
- Vision API 병렬 호출
- Rule-based 1차 필터링 → LLM 2차 판단

### 7.2 한국 데이터 특화
- 한글 성분명 동의어 처리
- 한국 공식 기관 데이터 우선순위

### 7.3 개인화
- 7단계 비건 레벨 시스템
- 사용자별 알레르기 정보 반영

### 7.4 신뢰성
- 출처 표시 (식약처, 비건인증원 등)
- 신뢰도 점수 공개

---

## 8. 확장 계획

### Phase 1 (MVP)
- VeganScan 기능
- 기본 Chatbot
- 사용자 프로필 관리

### Phase 2
- Recipe 추천 시스템
- 식당 찾기
- 커뮤니티 기능 (피드백 루프)

### Phase 3
- 개인화 추천 강화 (협업 필터링)
- 영양 대시보드 고도화
- 비건 챌린지 및 배지 시스템

---

## 9. 비용 추정 (월간)

| 항목 | 예상 비용 |
|------|-----------|
| OpenAI API (GPT-4) | $500 (1만 스캔 기준) |
| Google Cloud Vision | $150 |
| AWS 인프라 (ECS, S3, RDS) | $300 |
| Pinecone (대안: FAISS 무료) | $70 or $0 |
| **Total** | **~$1,000/month** |

**비용 최적화 방안**
- FAISS Self-hosted로 VectorDB 비용 절감
- GPT-4 → GPT-4 Turbo (명확한 케이스)
- Redis 캐싱으로 API 호출 감소

---

## 10. 기대 효과

### 사용자 가치
- 비건 입문자의 학습 곡선 단축
- 장보기 시간 절약 (3초 판단)
- 안전한 식단 관리

### 비즈니스 가치
- 비건 제품 제휴 마케팅
- 프리미엄 구독 모델
- 데이터 기반 트렌드 분석

---

## 11. 리스크 및 대응

### 기술적 리스크
- **GPT-4 API 비용**: FAISS + Rule-based로 부분 대체
- **한국어 성능**: ko-sbert 임베딩 병행 사용

### 데이터 리스크
- **정보 부정확성**: 신뢰도 점수 공개, 커뮤니티 피드백 루프
- **업데이트 지연**: 주간 크롤링 자동화

---

## 12. 다음 단계 (논의 사항)

### 기술 검증
- [ ] GPT-4 Vision 한국 음식 인식률 테스트
- [ ] FAISS vs Pinecone 성능 비교
- [ ] 3초 응답 시간 달성 가능성 검증

### 데이터 확보
- [ ] 한국비건인증원 데이터 접근 방법 확인
- [ ] 식약처 API 사용 가능 여부 조사

### MVP 범위 결정
- [ ] Phase 1 기능 우선순위 합의
- [ ] 개발 기간 산정 (2개월 내 가능?)

---

**작성일**: 2026-01-15  
**작성자**: AI Bootcamp Final Project Team  
**문서 상태**: Draft (논의용)
