// Theme Toggle
const themeToggle = document.getElementById('themeToggle');
const htmlElement = document.documentElement;

// Load saved theme
const savedTheme = localStorage.getItem('theme') || 'light';
htmlElement.setAttribute('data-theme', savedTheme);
if (savedTheme === 'dark') {
    themeToggle.checked = true;
}

// Theme toggle handler
themeToggle?.addEventListener('change', function() {
    const theme = this.checked ? 'dark' : 'light';
    htmlElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
});

// Navigation Active State
const currentPath = window.location.pathname;
const navLinks = document.querySelectorAll('.nav-link');

navLinks.forEach(link => {
    const href = link.getAttribute('href');
    if (currentPath === href || (currentPath === '/' && href === '/')) {
        link.classList.add('active');
    } else {
        link.classList.remove('active');
    }
});

// Auth State Management
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
            const expiry = payload.exp * 1000;
            return Date.now() < expiry;
        } catch (e) {
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
        this.token = null;
        this.user = null;
        localStorage.removeItem('authToken');
        localStorage.removeItem('user');
        window.location.href = 'login.html';
    }
    
    getToken() {
        return this.token;
    }
    
    getUser() {
        return this.user;
    }
}

const authManager = new AuthManager();

// Update UI based on auth state
function updateAuthUI() {
    const loginBtn = document.getElementById('loginBtn');
    const headerActions = document.querySelector('.header-actions');
    
    if (authManager.isAuthenticated()) {
        const user = authManager.getUser();
        if (loginBtn) {
            loginBtn.textContent = '로그아웃';
            loginBtn.onclick = () => authManager.logout();
        }
        
        // Add user info
        const userInfo = document.createElement('div');
        userInfo.className = 'user-info';
        userInfo.innerHTML = `
            <span class="user-email">${user.email}</span>
        `;
        headerActions?.insertBefore(userInfo, loginBtn);
    } else {
        if (loginBtn) {
            loginBtn.textContent = '로그인';
            loginBtn.onclick = () => window.location.href = 'login.html';
        }
    }
}

// Check auth on protected pages
function requireAuth() {
    const protectedPages = ['analysis.html', 'chat.html', 'results.html', 'history.html'];
    const currentPage = window.location.pathname.split('/').pop();
    
    if (protectedPages.includes(currentPage) && !authManager.isAuthenticated()) {
        Toast.warning('로그인이 필요한 서비스입니다.');
        setTimeout(() => {
            window.location.href = 'login.html';
        }, 1500);
        return false;
    }
    return true;
}

// API Helper
class APIClient {
    constructor(baseURL) {
        this.baseURL = baseURL || 'http://localhost:8000/api';
    }
    
    async request(endpoint, options = {}) {
        const url = `${this.baseURL}${endpoint}`;
        const token = authManager.getToken();
        
        const config = {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                ...(token && { 'Authorization': `Bearer ${token}` }),
                ...options.headers,
            },
        };
        
        try {
            const response = await fetch(url, config);
            
            // Handle token expiry
            if (response.status === 401) {
                authManager.logout();
                throw new Error('인증이 만료되었습니다. 다시 로그인해주세요.');
            }
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.message || '요청에 실패했습니다.');
            }
            
            return await response.json();
        } catch (error) {
            console.error('API Error:', error);
            throw error;
        }
    }
    
    get(endpoint) {
        return this.request(endpoint, { method: 'GET' });
    }
    
    post(endpoint, data) {
        return this.request(endpoint, {
            method: 'POST',
            body: JSON.stringify(data),
        });
    }
    
    put(endpoint, data) {
        return this.request(endpoint, {
            method: 'PUT',
            body: JSON.stringify(data),
        });
    }
    
    delete(endpoint) {
        return this.request(endpoint, { method: 'DELETE' });
    }
}

const apiClient = new APIClient();

// Toast Notification System
class Toast {
    static show(message, type = 'info', duration = 3000) {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        
        const container = document.getElementById('toast-container') || this.createContainer();
        container.appendChild(toast);
        
        // Animate in
        setTimeout(() => toast.classList.add('show'), 10);
        
        // Remove after duration
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        }, duration);
    }
    
    static createContainer() {
        const container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container';
        document.body.appendChild(container);
        return container;
    }
    
    static success(message) {
        this.show(message, 'success');
    }
    
    static error(message) {
        this.show(message, 'error');
    }
    
    static warning(message) {
        this.show(message, 'warning');
    }
    
    static info(message) {
        this.show(message, 'info');
    }
}

// Modal System
class Modal {
    static show(title, content, actions = []) {
        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        
        const modal = document.createElement('div');
        modal.className = 'modal';
        modal.innerHTML = `
            <div class="modal-header">
                <h3 class="modal-title">${title}</h3>
                <button class="modal-close">&times;</button>
            </div>
            <div class="modal-content">
                ${content}
            </div>
            <div class="modal-actions">
                ${actions.map(action => `
                    <button class="btn-${action.type || 'secondary'}" data-action="${action.action}">
                        ${action.label}
                    </button>
                `).join('')}
            </div>
        `;
        
        overlay.appendChild(modal);
        document.body.appendChild(overlay);
        
        // Close handlers
        const close = () => {
            overlay.classList.remove('show');
            setTimeout(() => overlay.remove(), 300);
        };
        
        overlay.querySelector('.modal-close').onclick = close;
        overlay.onclick = (e) => {
            if (e.target === overlay) close();
        };
        
        // Action handlers
        actions.forEach(action => {
            const btn = overlay.querySelector(`[data-action="${action.action}"]`);
            btn.onclick = () => {
                if (action.handler) action.handler();
                if (!action.keepOpen) close();
            };
        });
        
        setTimeout(() => overlay.classList.add('show'), 10);
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    updateAuthUI();
    requireAuth();
});

// Check auth and redirect
function checkAuthAndRedirect(page) {
    if (authManager.isAuthenticated()) {
        window.location.href = page;
    } else {
        Toast.warning('로그인이 필요한 서비스입니다.');
        setTimeout(() => {
            window.location.href = 'login.html';
        }, 1500);
    }
}

// Export for other modules
window.authManager = authManager;
window.apiClient = apiClient;
window.Toast = Toast;
window.Modal = Modal;
window.checkAuthAndRedirect = checkAuthAndRedirect;
