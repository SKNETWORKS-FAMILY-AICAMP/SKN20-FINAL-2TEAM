# 비건 라이프 큐레이션 앱 미니기획서
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


## 3. 주요 워크플로우 (Sequence Diagram 기반)

### 3.1 VeganScan 플로우
```
- Maseter Agent : 워크플로우 조율
- Vision Agent : 음식 이미지 분석
- OCR Agent :  영양성분표 텍스트 추출
- Vegan Level Agent : 사용자 비건 단계별 판단
- Product Agent : 대체 상품 추천


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
Step 5: 비건 레벨별 검증 (3초 이내 목표)
  - Vegan Level Agent: 사용자 레벨별 판단
  ↓
Step 6: 결과 출력
  - ✅ VEGAN FRIENDLY (초록불)
  - ⚠️ CAUTION (노란불 - 유제품 포함 등)
  - ❌ NOT VEGAN (빨간불 - 유청 단백 등)
  - 대체 상품 추천 (Product Agent)
```

### 3.2 Chatbot 플로우
```
- Maseter Agent : 워크플로우 조율
- Vegan Level Agent : 사용자 비건 단계별 판단
- Nutrition Agent : 영양 분석 및 조언

User 질문 → Master Agent → Vegan-Level-Agent
  ↓ (필요시)
RAG System → 지식 검색
  ↓
Nutrition Agent → 영양 정보 추가
  ↓
응답 생성 → User
```

### 3.3 Recipe 플로우
```
- Maseter Agent : 워크플로우 조율
- Recipe Agent : 비건 레시피 생성
- Nutrition Agent : 영양 분석 및 조언

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

