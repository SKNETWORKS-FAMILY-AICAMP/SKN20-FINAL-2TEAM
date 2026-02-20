// ==========================
// 개발 모드 설정 (배포 시 false로 변경!)
// ==========================
const DEV_BYPASS_AUTH = false;

// ==========================
// Auth State Management
// ==========================
class AuthManager {
    constructor() {
        this.token = localStorage.getItem('authToken');
        this.user = JSON.parse(localStorage.getItem('user') || 'null');
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
        localStorage.setItem('authToken', token);
        localStorage.setItem('user', JSON.stringify(user));
    }

    logout() {
        localStorage.clear();
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

    document.querySelectorAll("[data-nav]").forEach(link => {
        const target = link.getAttribute("data-nav") || link.getAttribute("href");

        link.classList.remove("text-primary", "font-semibold");

        if (target === currentPage) {
            link.classList.add("text-primary", "font-semibold");
        }
    });
}

// ==========================
// Auth UI Update
// ==========================
function updateAuthUI() {
    const loginBtn = document.getElementById("loginBtn");
    if (!loginBtn) return;

    if (authManager.token && !authManager.isTokenValid()) {
        localStorage.removeItem("authToken");
        localStorage.removeItem("user");
        authManager.token = null;
        authManager.user = null;
    }

    if (authManager.isAuthenticated()) {
        loginBtn.textContent = "로그아웃";
        loginBtn.onclick = () => authManager.logout();
    } else {
        loginBtn.textContent = "로그인";
        loginBtn.onclick = () => (window.location.href = "login.html");
    }
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
        "history.html"
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
