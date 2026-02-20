# FTOGuard Results 페이지 비즈벨 스타일 통일 가이드

## 📋 수정 대상 파일
1. results.html
2. graph-rag.html  
3. combined-results.html
4. design-results.html

---

## ✅ 공통 수정사항

### 1. HEAD 섹션에 Pretendard 폰트 추가

**위치**: `<title>` 태그 다음, 기존 `<style>` 태그 앞

```html
<style>
    /* Pretendard 폰트 (비즈벨과 동일) */
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');
    
    * {
        font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
    }
    
    :root {
        --primary: #FF6B35;
    }
    
    .text-primary { color: var(--primary); }
    .bg-primary { background-color: var(--primary); }
    .border-primary { border-color: var(--primary); }
    .hover\:bg-primary\/90:hover { background-color: rgba(255, 107, 53, 0.9); }
    .focus\:ring-primary:focus { 
        --tw-ring-color: rgba(255, 107, 53, 0.5);
    }
</style>
```

### 2. BODY 닫기 태그 전에 header 로더 추가

```html
    <script>
        // Load header.html
        fetch('header.html')
            .then(response => response.text())
            .then(data => {
                document.getElementById('app-header').innerHTML = data;
                
                const scripts = document.getElementById('app-header').querySelectorAll('script');
                scripts.forEach(script => {
                    const newScript = document.createElement('script');
                    if (script.src) {
                        newScript.src = script.src;
                    } else {
                        newScript.textContent = script.textContent;
                    }
                    document.body.appendChild(newScript);
                });
            })
            .catch(error => console.error('Error loading header:', error));
    </script>
</body>
</html>
```

### 3. 색상 변경 (Find & Replace)

| 찾기 | 바꾸기 |
|------|--------|
| `bg-blue-600` | `bg-primary` |
| `text-blue-600` | `text-primary` |
| `hover:bg-blue-500` | `hover:bg-primary/90` |
| `hover:bg-blue-600` | `hover:bg-primary/90` |
| `border-blue-600` | `border-primary` |
| `bg-slate-50` | `bg-neutral-50` |
| `bg-slate-100` | `bg-neutral-100` |
| `border-slate-200` | `border-neutral-200` |
| `border-slate-100` | `border-neutral-100` |
| `text-slate-900` | `text-black` |
| `text-slate-800` | `text-black` |
| `text-slate-500` | `text-neutral-600` |
| `text-slate-600` | `text-neutral-700` |

### 4. 디자인 시스템 통일

```css
/* 모서리 반경 */
rounded-[2rem] → rounded-3xl
rounded-2xl → rounded-xl (변경 필요 시)

/* 그림자 */
shadow-2xl → shadow-lg

/* 패딩 */
p-10 → p-8 md:p-10
py-4 → py-3.5

/* 폰트 크기 */
text-3xl font-black → text-2xl md:text-3xl font-bold
text-2xl font-black → text-xl md:text-2xl font-semibold
```

---

## 📄 파일별 특수 사항

### results.html
- ✅ 이미 `<div id="app-header"></div>` 있음
- ✅ custom CSS 파일 (styles-verdict.css) 유지
- ⚠️ body 배경: `bg-slate-50` → `bg-neutral-50`
- 🎨 verdict 관련 CSS는 유지하되, 컬러만 변경

**변경 필요한 특수 클래스:**
```css
.btn-primary-large { background: var(--primary); }
.btn-primary-large:hover { background: rgba(255, 107, 53, 0.9); }
```

### graph-rag.html
- ⚠️ body 배경: `bg-slate-950` 유지 (다크 테마 의도)
- 🎨 노드 색상 변경 필요:
  - `.node-user` fill: `#3B82F6` → `var(--primary)` (선택사항)
- ✅ 버튼: `bg-blue-600` → `bg-primary`

### combined-results.html & design-results.html
- ✅ 이미 `<div id="app-header"></div>` 있음
- ⚠️ body 배경: `bg-slate-50` → `bg-neutral-50`
- 🎨 탭 활성화 색상: `border-blue-600` → `border-primary`
- 🎨 아이콘 색상: `text-blue-600` → `text-primary`

---

## 🎯 빠른 수정 체크리스트

각 파일당:

- [ ] 1. HEAD에 Pretendard 폰트 스타일 추가
- [ ] 2. BODY 닫기 전 header 로더 스크립트 추가  
- [ ] 3. `bg-slate-50` → `bg-neutral-50` 변경
- [ ] 4. `text-slate-900` → `text-black` 변경
- [ ] 5. `bg-blue-600` → `bg-primary` 변경
- [ ] 6. `text-blue-600` → `text-primary` 변경
- [ ] 7. `hover:bg-blue-*` → `hover:bg-primary/90` 변경
- [ ] 8. 테스트: 페이지 로드 및 기능 확인

---

## 💾 저장 위치
수정된 파일은 `/mnt/user-data/outputs/` 에 저장

---

## ⚠️ 주의사항

1. **기능 유지**: JavaScript 함수명, ID, class명 절대 변경 금지
2. **CSS 우선순위**: 기존 custom CSS 파일(styles.css, styles-verdict.css)이 새 스타일보다 우선할 수 있음
3. **테스트 필수**: 각 페이지의 주요 기능 동작 확인 필요

---

## 🎨 최종 확인사항

모든 페이지가:
- ✅ Pretendard 폰트 사용
- ✅ #FF6B35 오렌지 Primary 컬러
- ✅ 공통 header.html 로드
- ✅ neutral-* 색상 팔레트
- ✅ 비즈벨 스타일 버튼/카드/테두리
