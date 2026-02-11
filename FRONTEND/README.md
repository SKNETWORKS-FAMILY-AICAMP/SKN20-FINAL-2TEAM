# FTOGuard 프론트엔드 완전 가이드

## 📂 프로젝트 구조

```
FRONTEND/
├── index.html                    # 메인 랜딩 페이지
├── about.html                    # 소개 페이지
├── how-it-works.html             # 작동 원리 페이지
├──────────────────────────────────
├── login.html                    # 로그인 페이지
├── signup.html                   # 회원가입 페이지
├── forgot-password.html          # 비밀번호 재설정
├──────────────────────────────────
├── analysis.html                 # 채팅 기반 분석 입력
├── results.html                  # 텍스트 FTO 분석 결과
├── design-results.html           # 디자인 유사도 분석 결과
├── combined-results.html         # 멀티모달 종합 결과
├──────────────────────────────────
├── header.html                   # 공통 헤더 컴포넌트
├── styles.css                    # 공통 스타일시트
├── toast.css                     # Toast 알림 스타일
├──────────────────────────────────
├── script.js                     # 공통 유틸리티 (AuthManager, APIClient)
├── toast.js                      # Toast 알림 시스템
├── auth.js                       # 인증 관련 로직
├── analysis-complete.js          # 분석 워크플로우 + 라우팅
├── verdict.js                    # FTO 결과 렌더링
├── design-results.js             # 디자인 결과 렌더링
├── combined-results.js           # 멀티모달 결과 렌더링
└── analysis-routing-addon.js     # 라우팅 로직 추가 코드
```

---

## 🎯 워크플로우 (사용자 플로우)

### **1. 인증 플로우**
```
방문자
  ↓
index.html (랜딩 페이지)
  ↓ [분석 시작] 클릭
  ↓
인증 확인
  ├─ 로그인됨 → analysis.html
  └─ 비로그인 → login.html
                    ↓
              signup.html (회원가입)
                    ↓
              login.html (로그인)
                    ↓
              analysis.html
```

### **2. 분석 플로우**
```
analysis.html (채팅 입력)
  ↓
중앙 오케스트레이터 (라우터)
  ├─ 텍스트만 → 텍스트 에이전트
  ├─ 이미지만 → 디자인 에이전트
  └─ 둘 다 → 두 에이전트 병렬 실행
  ↓
분석 완료
  ├─ 텍스트 FTO → results.html
  ├─ 디자인 → design-results.html
  └─ 멀티모달 → combined-results.html
```

---

## 🔧 핵심 파일 설명

### **1. 공통 시스템**

#### `header.html`
```html
공통 헤더 컴포넌트
- 로고
- 네비게이션 (홈, 작동 원리, 리스크 분석, 소개)
- 로그인/로그아웃 버튼
- Active 상태 자동 표시
```

#### `script.js`
```javascript
// AuthManager - JWT 토큰 관리
authManager.login(token, user)
authManager.logout()
authManager.isAuthenticated()

// APIClient - API 호출 래퍼
apiClient.post('/endpoint', data)
apiClient.get('/endpoint')
```

#### `toast.js`
```javascript
// Toast 알림 시스템
Toast.success('메시지')
Toast.error('메시지')
Toast.warning('메시지')
Toast.info('메시지')
```

---

### **2. 인증 페이지**

#### `login.html` + `auth.js`
```javascript
// 기능:
- 이메일/비밀번호 로그인
- 비밀번호 보기/숨기기 토글
- Remember Me 체크박스
- 로그인 실패 시 Toast 에러
- 성공 시 analysis.html로 리다이렉트
```

#### `signup.html` + `auth.js`
```javascript
// 기능:
- 이메일 중복 체크 (Mock)
- 비밀번호 강도 실시간 체크
- 비밀번호 확인 매칭
- 필수값 검증 후 버튼 활성화
- 회원가입 성공 시 Toast + 로그인 페이지로 이동
```

---

### **3. 분석 페이지**

#### `analysis.html` + `analysis-complete.js`
```javascript
// 기능:
1. 텍스트/이미지 입력
2. 파일 업로드 (드래그 & 드롭)
3. 분석 유형 자동 감지
4. 워크플로우 시각화
   - 키워드 추출
   - Vector DB 검색
   - SLLM/VLM 분석
   - 위험도 판단
   - 대안 탐색
5. 정보 충분성 체크
6. 구조화된 질문 확인 UI
7. 결과 페이지 라우팅
```

**라우팅 로직:**
```javascript
// analysis-complete.js의 addFinalAnalysisResult 함수

if (analysisType === 'fto') {
    resultPageUrl = `results.html?id=${analysisId}&type=fto`;
} else if (analysisType === 'design') {
    resultPageUrl = `design-results.html?id=${analysisId}&type=design`;
} else if (analysisType === 'multimodal') {
    resultPageUrl = `combined-results.html?id=${analysisId}&type=multimodal`;
}
```

---

### **4. 결과 페이지**

#### `results.html` + `verdict.js`
```
텍스트 FTO 분석 결과 전용

표시 내용:
✅ 침해 리스크 요약 (신호등 색상)
✅ 신뢰도 바
✅ 검색된 특허 목록
✅ 구성요소 대응 관계 테이블
✅ 자유실시기술 제안
✅ PDF 다운로드 버튼
```

#### `design-results.html` + `design-results.js`
```
디자인 유사도 분석 결과 전용

표시 내용:
✅ Top-N 이미지 그리드 (3열)
✅ 유사도 점수 + 프로그레스 바
✅ 유사/비유사 배지
✅ 모델 평가 UI (개발자용)
✅ 사람 검증 입력 필드
✅ AI-사람 판단 불일치 사례
```

#### `combined-results.html` + `combined-results.js`
```
멀티모달 종합 결과

표시 내용:
✅ 종합 리스크 평가 (FTO + 디자인)
✅ 탭 1: 텍스트 FTO 분석
✅ 탭 2: 디자인 유사도 분석
✅ 종합 판단 (두 결과 통합)
```

---

## 🚀 적용 방법

### **Step 1: analysis-complete.js 수정**

기존 `addFinalAnalysisResult` 함수를 다음과 같이 수정:

```javascript
// 기존 코드 (line 972-1033)
function addFinalAnalysisResult(riskLevel) {
    // ...
    <button class="btn-primary" onclick="window.location.href='results.html?id=${currentAnalysisId || 'DEMO-' + Date.now()}'">
    // ...
}

// 수정 후 코드
function addFinalAnalysisResult(riskLevel, analysisType = 'fto') {
    // ...
    
    // 🔥 분석 타입에 따라 결과 페이지 분기
    const analysisId = currentAnalysisId || 'DEMO-' + Date.now();
    let resultPageUrl;
    
    if (analysisType === 'fto') {
        resultPageUrl = `results.html?id=${analysisId}&type=fto`;
    } else if (analysisType === 'design') {
        resultPageUrl = `design-results.html?id=${analysisId}&type=design`;
    } else if (analysisType === 'multimodal') {
        resultPageUrl = `combined-results.html?id=${analysisId}&type=multimodal`;
    }
    
    // ...
    <button class="btn-primary" onclick="window.location.href='${resultPageUrl}'">
    // ...
}
```

### **Step 2: executeWorkflow 함수 수정**

```javascript
// line 599-609 수정
// Step 6: Complete
await updateWorkflowStep('complete');
updateAgentProgress('orchestrator', 100, '분석 완료');

removeTypingIndicator();

const riskLevel = Math.random() > 0.7 ? 'warning' : Math.random() > 0.4 ? 'safe' : 'danger';

// 🔥 analysisType 파라미터 전달
addFinalAnalysisResult(riskLevel, analysisType);

updateAgentStatus('complete');
```

---

## 📋 체크리스트

### ✅ 완료된 기능
- [x] 공통 헤더 시스템
- [x] Toast 알림 시스템
- [x] 로그인/회원가입
- [x] 비밀번호 재설정
- [x] 채팅 기반 분석 입력
- [x] 파일 업로드 (이미지, PDF)
- [x] 워크플로우 시각화
- [x] 정보 충분성 판단
- [x] 구조화된 질문 확인
- [x] 텍스트 FTO 결과 화면
- [x] 디자인 유사도 결과 화면
- [x] 멀티모달 종합 결과 화면
- [x] 라우팅 로직
- [x] 모델 평가 UI
- [x] 사람 검증 입력

### ❌ 미구현 기능
- [ ] Graph RAG 시각화 (D3.js/Cytoscape.js)
- [ ] 실제 API 연동
- [ ] PDF 다운로드 기능
- [ ] 이메일 중복 체크 API

---

## 🎨 디자인 시스템

### 색상 팔레트
```css
/* Traffic Light System */
--color-safe: #10B981     /* 녹색 - 안전 */
--color-warning: #F59E0B  /* 노란색 - 경고 */
--color-danger: #EF4444   /* 빨간색 - 위험 */

/* Brand Colors */
--color-primary: #3B82F6  /* 파란색 */
--color-secondary: #8B5CF6 /* 보라색 */

/* Neutrals */
--slate-50: #F8FAFC
--slate-900: #0F172A
```

### 타이포그래피
```css
/* Headings */
text-3xl font-black    /* 페이지 타이틀 */
text-xl font-bold      /* 섹션 헤더 */

/* Body */
text-base              /* 기본 텍스트 */
text-sm text-slate-500 /* 보조 텍스트 */
```

---

## 🔐 보안 고려사항

1. **JWT 토큰 관리**
   - LocalStorage 저장
   - 만료 시간 체크
   - 자동 로그아웃

2. **API 요청 인터셉터**
   - 모든 요청에 Authorization 헤더 자동 추가
   - 401 응답 시 자동 로그아웃

3. **Protected Routes**
   - analysis.html, results.html 접근 시 인증 체크
   - 비인증 시 login.html로 리다이렉트

---

## 📱 반응형 디자인

```css
/* Breakpoints */
sm: 640px   /* Mobile */
md: 768px   /* Tablet */
lg: 1024px  /* Desktop */
xl: 1280px  /* Large Desktop */

/* Grid System */
grid-cols-1 md:grid-cols-2 lg:grid-cols-3
```

---

## 🐛 디버깅 팁

1. **헤더가 안 보이면**
   - `styles.css` 포함 확인
   - `script.js` 로드 확인
   - Console에서 `fetch("header.html")` 에러 확인

2. **Toast가 안 나오면**
   - `toast.js` + `toast.css` 포함 확인
   - `Toast.success()` 호출 전에 DOM 로드 완료 확인

3. **라우팅이 안 되면**
   - `analysisType` 변수 값 확인
   - `addFinalAnalysisResult(riskLevel, analysisType)` 파라미터 확인

---

## 📞 문의

문제 발생 시:
1. 브라우저 Console 확인
2. Network 탭에서 API 호출 확인
3. LocalStorage에 `auth_token` 존재 확인

---

**작성일**: 2026-02-11
**버전**: 1.0.0
**완성도**: 85%
