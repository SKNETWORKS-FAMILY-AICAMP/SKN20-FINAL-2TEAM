# 상하의 (cd agent) - 멀티 에이전트 기반 개인화 코디 추천 시스템

<div align="center">
  <img src="./front/mainpage/resources/images/shanghai_white.png" alt="상하의 로고" width="200"/>
  
  [![SKN Family AI Camp](https://img.shields.io/badge/SKN%20Family%20AI%20Camp-20%EA%B8%B0-blue)](https://github.com)
  [![Team](https://img.shields.io/badge/Team-cd%20agent%20(2%EC%A1%B0)-green)](https://github.com)
  [![License](https://img.shields.io/badge/license-MIT-red)](LICENSE)
</div>

## 📌 프로젝트 소개

**상하의**는 사용자의 디지털 옷장과 셀럽 스타일을 기반으로 개인화된 코디를 추천하는 멀티 에이전트 AI 플랫폼입니다. 

"옷은 많지만 입을 옷은 없다"는 문제를 해결하기 위해, 단순한 스타일 추천을 넘어 실질적인 착장 의사결정을 지원합니다.

### 💡 핵심 가치

- **개인화된 추천**: 사용자의 옷장 아이템을 기반으로 한 실질적인 코디 제안
- **셀럽 스타일 분석**: 좋아하는 셀럽의 스타일을 내 옷으로 재현
- **멀티 에이전트 시스템**: 여러 AI Agent가 협업하여 합리적인 의사결정 제공
- **대화형 인터페이스**: 자연어 기반 챗봇으로 편리한 스타일링 경험

---

## 🎯 문제 정의

### 현재의 문제점

1. **착장 결정의 어려움**
   - 충분한 옷을 보유하고 있음에도 조합 방법을 모름
   - 셀럽 스타일을 내 옷으로 적용하는 구체적 기준 부재

2. **감각적 요소의 학습 장벽**
   - 스타일은 언어로 설명하거나 체계적으로 학습하기 어려움
   - 직접 입어보지 않고는 어울림 판단이 힘듦

3. **기존 서비스의 한계**
   - 트렌드와 셀럽 착장 제시에만 그침
   - 사용자 보유 아이템 기반 조합 가능성 미제공
   - 날씨, 상황별 개인화된 가이드 부족

---

## 🏗️ 시스템 구성

### 멀티 에이전트 아키텍처
```
┌─────────┐
│  사용자  │
└────┬────┘
     │ 자연어 질문
     ▼
┌──────────────────┐
│ 챗봇 인터페이스   │
└────┬─────┬───┬───┘
     │     │   │
     ▼     ▼   ▼
┌────────┐ ┌──────────────────┐ ┌────────────────────────┐
│ Celeb  │ │ Wardrobe Analysis│ │ Decision Orchestrator  │
│ Agent  │ │     Agent        │ │       Agent            │
└────┬───┘ └─────────┬────────┘ └───────────┬────────────┘
     │               │                      │
     └───────────────┴──────────────────────┘
                     │
                     ▼
              ┌──────────┐
              │ 최종 추천 │
              └──────────┘
```

### 주요 Agent 역할

#### 1️⃣ Celeb Agent
- 사용자의 옷장과 셀럽의 스타일 정보를 매칭
- 보유 아이템으로 구현 가능한 코디 후보 생성
- 셀럽 스타일과의 유사도 분석

#### 2️⃣ Wardrobe Analysis Agent
- 옷장 내 아이템 중복도, 활용도 분석
- 카테고리별 불균형 파악
- 구매 필요성 판단 및 추천

#### 3️⃣ Decision Orchestrator Agent
- 각 Agent의 결과를 종합 분석
- 최종 코디 추천 또는 구매 보류 결론 도출
- 사용자 피드백 기반 개인화 강화

---

## 🛠️ 기술 스택

### Frontend
```
HTML, CSS, JavaScript
```

### Backend
```
FastAPI
```

### AI/ML
```
- LLM: OpenAI GPT-4
- Agent Framework: LangGraph
- Fine-tuning
```

### RAG (Retrieval-Augmented Generation)
```
- Vector DB: ChromaDB
- Embedding: OpenAI Embeddings
```

### Infrastructure
```
Docker, AWS EC2
```

---

## 📊 사용 데이터

### RAG 지식 베이스

1. **스타일링 지식**
   - 컬러 조합론
   - 스타일별 특징 (미니멀, 스트릿, 클래식)
   - TPO별 드레스 코드
   - 체형별 코디 가이드

2. **코디 규칙**
   - 매칭 룰 (예: 데님 + 블레이저)
   - 금기 조합 (예: 양말 + 샌들)

3. **패션 용어 사전**
   - 아이템 용어 (블레이저 vs 재킷)
   - 소재 특성 (린넨, 울, 코튼)
   - 핏 가이드 (슬림핏, 레귤러핏, 오버핏)

4. **셀럽 스타일 DB**
   - 제니: 러블리, 파스텔톤, 시크
   - 주우재: 미니멀 캐주얼, 베이직 컬러

5. **트렌드 상품** (주기적 업데이트)
   - 무신사/29cm 카테고리별 Top 100

---

## 🎨 주요 기능

### 1. Smart Wardrobe (스마트 옷장)
- 옷장 아이템 디지털 등록 및 관리
- 카테고리별 분류 (TOP, BOTTOM, OUTER, ACC, SHOES)
- 아이템 활용도 및 중복도 분석

### 2. Celeb's Pick (셀럽 스타일)
- 인기 셀럽의 최신 스타일 확인
- 셀럽 룩을 내 옷으로 재현하는 방법 제안
- 유사 아이템 추천

### 3. AI Chatbot (코디 추천 챗봇)
- 자연어 기반 대화형 스타일링
- 날씨, 상황, 선호도를 고려한 맞춤 추천
- 멀티턴 대화로 조건 누적 및 조정
- 실시간 피드백 (좋아요/싫어요/저장)

### 4. Lookbook (룩북)
- 추천받은 코디 저장 및 관리
- 과거 코디 히스토리 조회
- 스타일 트렌드 분석

---

## 👥 팀 구성 및 R&R

### 백엔드
**김태빈**
- 서버 로직 및 API 설계·구현
- 데이터베이스 관리
- 프론트엔드 및 AI 모델 연동
- 안정적인 서비스 운영 환경 구축

### 프론트엔드
**박다정, 최유정**
- 사용자 흐름 기반 웹 페이지 구현
- UX/UI 설계 및 인터랙션 개발
- 백엔드 및 AI 기능 연동
- 서비스 완성도 향상

### AI 모델링
**강민지, 김나현, 조준상**
- **LLM**: 프로젝트 용도 파인튜닝, 프롬프트 설계·제어
- **Vision**: 이미지 기반 의상 분석 및 스타일 특징 추출
- 셀럽 이미지와 사용자 의류 유사도 판단
- 시각 정보 AI 활용 처리

---

## 📱 화면 구성

### 메인 페이지
- **로그인 전**: 성별 선택 및 Today's Pick
- **로그인 후**: Smart Wardrobe, Celeb's Pick, Chatbot 바로가기

### Smart Wardrobe
- 5개 카테고리 (TOP, BOTTOM, OUTER, ACC, SHOES)
- 각 아이템 이미지 및 세부 정보 표시

### Chatbot
- **사이드바**: 
  - 옷장 카테고리 바로가기
  - 대화 기록 (접이식 드롭다운)
- **채팅 영역**: 
  - AI 코디 추천 (이미지 포함)
  - 반응 버튼 (좋아요/싫어요/Lookbook 저장)
  - 추천 질문 버튼

### 기타 페이지
- FAQ, Lookbook, 회원가입/로그인, 리뷰

---

## 🚀 시작하기

### 필수 요구사항
```bash
Python 3.9+
Node.js 14+
Docker
```

### 설치 및 실행

1. **저장소 클론**
```bash
git clone https://github.com/your-team/cd-agent.git
cd cd-agent
```

2. **환경 변수 설정**
```bash
cp .env.example .env
# .env 파일에 OpenAI API 키 등 필요한 값 입력
```

3. **백엔드 실행**
```bash
cd backend
pip install -r requirements.txt --break-system-packages
uvicorn main:app --reload
```

4. **프론트엔드 실행**
```bash
cd front
# 브라우저에서 index.html 열기 또는
python -m http.server 8000
```

5. **Docker로 실행**
```bash
docker-compose up -d
```

---

## 📈 향후 계획

- [ ] 실시간 날씨 API 연동
- [ ] 쇼핑몰 연동 및 구매 링크 제공
- [ ] 소셜 기능 (친구 코디 공유)
- [ ] AR 가상 피팅 기능
- [ ] 다국어 지원

---

## 📄 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.

---

## 🤝 기여하기

프로젝트에 기여하고 싶으시다면:

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

<div align="center">
  
### ⭐ 이 프로젝트가 도움이 되셨다면 Star를 눌러주세요!

Made with ❤️ by **cd agent Team** (SKN Family AI Camp 20기 2조)

</div>
