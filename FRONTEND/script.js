// ==========================
// 개발 모드 설정 (배포 시 false로 변경!)
// ==========================
const DEV_BYPASS_AUTH = false;

// ==========================
// Auth State Management
// ==========================
class AuthManager {
    constructor() {
        this.token = sessionStorage.getItem('authToken');
        this.user = JSON.parse(sessionStorage.getItem('user') || 'null');
        // 만료된 토큰 자동 정리
        if (this.token && !this.isTokenValid()) {
            this._clear();
        }
    }

    isAuthenticated() {
        return !!this.token && this.isTokenValid();
    }

    isTokenValid() {
        if (!this.token) return false;
        try {
            const payload = JSON.parse(atob(this.token.split('.')[1]));
            return Date.now() < payload.exp * 1000;
        } catch {
            return false;
        }
    }

    login(token, user) {
        this.token = token;
        this.user = user;
        sessionStorage.setItem('authToken', token);
        sessionStorage.setItem('user', JSON.stringify(user));
    }

    _clear() {
        sessionStorage.removeItem('authToken');
        sessionStorage.removeItem('user');
        this.token = null;
        this.user = null;
    }

    logout() {
        this._clear();
        window.location.href = 'login.html';
    }

    getUser() {
        return this.user;
    }

    getToken() {
        return this.token;
    }
}

const authManager = new AuthManager();

// ==========================
// Header + Footer Include + Init
// ==========================
document.addEventListener("DOMContentLoaded", () => {

    // --------------------------
    // HEADER 로딩
    // --------------------------
    const headerContainer = document.getElementById("app-header");

    if (headerContainer) {
        fetch("header.html")
            .then(res => {
                if (!res.ok) throw new Error("header.html 로드 실패");
                return res.text();
            })
            .then(html => {
                headerContainer.innerHTML = html;

                // 헤더 삽입 후 실행
                setActiveNav();
                updateAuthUI();
                initMobileMenu();
            })
            .catch(err => {
                console.error("공통 헤더 로딩 오류:", err);
            });
    } else {
        updateAuthUI();
    }

    // --------------------------
    // FOOTER 로딩 (추가된 부분)
    // --------------------------
    const footerContainer = document.getElementById("app-footer");

    if (footerContainer) {
        fetch("footer.html")
            .then(res => {
                if (!res.ok) throw new Error("footer.html 로드 실패");
                return res.text();
            })
            .then(html => {
                footerContainer.innerHTML = html;
            })
            .catch(err => {
                console.error("공통 푸터 로딩 오류:", err);
            });
    }

    requireAuth();
});

// ==========================
// Active Nav 처리
// ==========================
function setActiveNav() {
    const currentPage = location.pathname.split("/").pop() || "index.html";

    // 드롭다운 하위 페이지 → 부모 "리스크 분석" 링크를 active 처리
    const analysisPages = ["analysis.html", "patent-chat.html", "design-chat.html", "select-analysis-type.html"];

    document.querySelectorAll("[data-nav]").forEach(link => {
        const target = link.getAttribute("data-nav");

        link.classList.remove("text-primary", "font-semibold");

        const isActive = target === currentPage ||
            (target === "select-analysis-type.html" && analysisPages.includes(currentPage));

        if (isActive) {
            link.classList.add("text-primary", "font-semibold");
        }
    });

    // 드롭다운 아이템 active 표시
    document.querySelectorAll(".dropdown-nav-item").forEach(item => {
        const href = item.getAttribute("href")?.split("?")[0];
        item.classList.remove("bg-primary/5", "text-primary");
        if (href === currentPage) {
            item.classList.add("bg-primary/5");
            // 아이콘 컨테이너 강조
            const iconWrap = item.querySelector(".dropdown-icon-wrap");
            if (iconWrap) iconWrap.classList.add("ring-1", "ring-primary/30");
        }
    });
}

// ==========================
// Auth UI Update
// ==========================
function updateAuthUI() {
    if (authManager.token && !authManager.isTokenValid()) {
        authManager._clear();
    }

    const isLoggedIn = authManager.isAuthenticated();
    const user = authManager.getUser();

    // 데스크톱
    const loggedOut = document.getElementById("authLoggedOut");
    const loggedIn = document.getElementById("authLoggedIn");
    const loginBtn = document.getElementById("loginBtn");

    if (loggedOut) loggedOut.style.display = isLoggedIn ? "none" : "";
    if (loggedIn) loggedIn.style.display = isLoggedIn ? "" : "none";

    if (loginBtn && !isLoggedIn) {
        loginBtn.textContent = "로그인";
        loginBtn.onclick = () => (window.location.href = "login.html");
    }

    if (isLoggedIn && user) {
        const nameEl = document.getElementById("profileName");
        const emailEl = document.getElementById("profileEmail");
        const badgeEl = document.getElementById("profilePlanBadge");
        if (nameEl) nameEl.textContent = user.name || "사용자";
        if (emailEl) emailEl.textContent = user.email || "";
        if (badgeEl) {
            const plan = (user.plan || "free").toUpperCase();
            badgeEl.textContent = plan;
            const colors = { FREE: "bg-neutral-100 text-neutral-600", PRO: "bg-blue-100 text-blue-700", MAX: "bg-amber-100 text-amber-700" };
            badgeEl.className = `inline-block mt-1 text-[10px] font-bold px-2 py-0.5 rounded-full ${colors[plan] || colors.FREE}`;
        }
    }

    // 모바일
    const loginBtnMobile = document.getElementById("loginBtn-mobile");
    const loggedInMobile = document.getElementById("authLoggedInMobile");
    if (loginBtnMobile) {
        loginBtnMobile.style.display = isLoggedIn ? "none" : "";
        if (!isLoggedIn) {
            loginBtnMobile.textContent = "로그인";
            loginBtnMobile.onclick = () => (window.location.href = "login.html");
        }
    }
    if (loggedInMobile) loggedInMobile.style.display = isLoggedIn ? "" : "none";
}

// ==========================
// Mobile Menu (header.html의 script가 innerHTML로는 실행 안 되므로 여기서 초기화)
// ==========================
function initMobileMenu() {
    const mobileMenuButton = document.getElementById("mobile-menu-button");
    const mobileMenu = document.getElementById("mobile-menu");

    if (mobileMenuButton && mobileMenu) {
        mobileMenuButton.addEventListener("click", () => {
            mobileMenu.classList.toggle("hidden");
        });
    }

    // 모바일 메뉴 배경 클릭 시 닫기
    if (mobileMenu) {
        mobileMenu.addEventListener("click", (e) => {
            if (e.target === mobileMenu) mobileMenu.classList.add("hidden");
        });
    }
}

// 모바일 리스크 분석 서브메뉴 토글 (header.html에서 onclick으로 호출)
function toggleMobileAnalysisMenu() {
    const submenu = document.getElementById("mobile-analysis-submenu");
    const icon = document.getElementById("mobile-analysis-icon");
    if (submenu) {
        submenu.classList.toggle("hidden");
        if (icon) {
            icon.classList.toggle("fa-chevron-down");
            icon.classList.toggle("fa-chevron-up");
        }
    }
}

// 모바일 사용 방법 서브메뉴 토글 (header.html에서 onclick으로 호출)
function toggleMobileDemoMenu() {
    const submenu = document.getElementById("mobile-demo-submenu");
    const icon = document.getElementById("mobile-demo-icon");
    if (submenu) {
        submenu.classList.toggle("hidden");
        if (icon) {
            icon.classList.toggle("fa-chevron-down");
            icon.classList.toggle("fa-chevron-up");
        }
    }
}

function closeMobileMenu() {
    const mobileMenu = document.getElementById("mobile-menu");
    if (mobileMenu) mobileMenu.classList.add("hidden");
}

// ==========================
// Auth Guard
// ==========================
function requireAuth() {
    if (DEV_BYPASS_AUTH) return;

    const protectedPages = [
        "analysis.html",
        "chat.html",
        "results.html",
        "history.html",
        "select-analysis-type.html",
        "patent-chat.html",
        "design-chat.html",
        "mypage.html"
    ];

    const currentPage = location.pathname.split("/").pop();

    if (protectedPages.includes(currentPage) && !authManager.isAuthenticated()) {
        window.location.replace("login.html");
    }
}

// ==========================
// API Helper
// ==========================
class APIClient {
    constructor(baseURL = "/api") {
        this.baseURL = baseURL;
    }

    async request(endpoint, options = {}) {
        const token = authManager.getToken();

        const res = await fetch(`${this.baseURL}${endpoint}`, {
            ...options,
            headers: {
                "Content-Type": "application/json",
                ...(token && { Authorization: `Bearer ${token}` }),
                ...options.headers,
            },
        });

        if (res.status === 401 && !DEV_BYPASS_AUTH) authManager.logout();
        if (!res.ok) throw new Error("API Error");

        return res.json();
    }

    get(endpoint) {
        return this.request(endpoint);
    }

    post(endpoint, data) {
        return this.request(endpoint, {
            method: "POST",
            body: JSON.stringify(data),
        });
    }

    postForm(endpoint, formData) {
        const token = authManager.getToken();
        return fetch(`${this.baseURL}${endpoint}`, {
            method: "POST",
            headers: {
                ...(token && { Authorization: `Bearer ${token}` }),
            },
            body: formData,
        }).then(async (res) => {
            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || res.statusText);
            }
            return res.json();
        });
    }
}

const apiClient = new APIClient();

// ==========================
// Public helpers
// ==========================
function checkAuthAndRedirect(page) {
    if (DEV_BYPASS_AUTH) {
        window.location.href = page;
        return;
    }

    authManager.isAuthenticated()
        ? (window.location.href = page)
        : (window.location.href = "login.html");
}

window.authManager = authManager;
window.apiClient = apiClient;
window.checkAuthAndRedirect = checkAuthAndRedirect;

// ==========================
// FAQ Toggle
// ==========================
function toggleFAQ(button) {
    const answer = button.nextElementSibling;
    const icon = button.querySelector("svg");
    const isOpen = button.getAttribute("data-open") === "true";

    if (isOpen) {
        answer.style.maxHeight = "0px";
        answer.style.opacity = "0";
        icon.style.transform = "rotate(0deg)";
        button.setAttribute("data-open", "false");
    } else {
        answer.style.maxHeight = answer.scrollHeight + "px";
        answer.style.opacity = "1";
        icon.style.transform = "rotate(180deg)";
        button.setAttribute("data-open", "true");
    }
}

window.toggleFAQ = toggleFAQ;