// Authentication JavaScript

// Password Toggle Functionality
function setupPasswordToggles() {
    const toggleButtons = document.querySelectorAll('.password-toggle');
    
    toggleButtons.forEach(button => {
        button.addEventListener('click', function() {
            const input = this.parentElement.querySelector('input');
            const type = input.getAttribute('type') === 'password' ? 'text' : 'password';
            input.setAttribute('type', type);
            
            // Toggle icon (you can add different SVG for eye-slash)
            this.classList.toggle('active');
        });
    });
}

// Email Validation
function validateEmail(email) {
    const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return re.test(email);
}

// Password Strength Checker
function checkPasswordStrength(password) {
    let strength = 0;
    const requirements = {
        length: password.length >= 8,
        upper: /[A-Z]/.test(password),
        number: /[0-9]/.test(password),
        special: /[!@#$%^&*]/.test(password)
    };
    
    if (requirements.length) strength++;
    if (requirements.upper) strength++;
    if (requirements.number) strength++;
    if (requirements.special) strength++;
    
    return { strength, requirements };
}

// Update Password Strength UI
function updatePasswordStrength(password) {
    const strengthFill = document.getElementById('strengthFill');
    const strengthText = document.getElementById('strengthText');
    
    if (!strengthFill || !strengthText) return;
    
    const { strength, requirements } = checkPasswordStrength(password);
    
    // Remove all classes
    strengthFill.className = 'strength-fill';
    
    if (password.length === 0) {
        strengthText.textContent = '비밀번호 강도';
        return;
    }
    
    if (strength <= 2) {
        strengthFill.classList.add('weak');
        strengthText.textContent = '약함';
        strengthText.style.color = '#EF4444';
    } else if (strength === 3) {
        strengthFill.classList.add('medium');
        strengthText.textContent = '보통';
        strengthText.style.color = '#F59E0B';
    } else {
        strengthFill.classList.add('strong');
        strengthText.textContent = '강함';
        strengthText.style.color = '#10B981';
    }
    
    // Update requirements
    updateRequirement('req-length', requirements.length);
    updateRequirement('req-upper', requirements.upper);
    updateRequirement('req-number', requirements.number);
}

function updateRequirement(id, valid) {
    const element = document.getElementById(id);
    if (element) {
        if (valid) {
            element.classList.add('valid');
        } else {
            element.classList.remove('valid');
        }
    }
}

// Check if passwords match
function checkPasswordMatch() {
    const password = document.getElementById('signupPassword');
    const confirmPassword = document.getElementById('confirmPassword');
    const hint = document.getElementById('passwordMatchHint');
    
    if (!password || !confirmPassword || !hint) return true;
    
    if (confirmPassword.value === '') {
        hint.textContent = '';
        hint.className = 'form-hint';
        return false;
    }
    
    if (password.value === confirmPassword.value) {
        hint.textContent = '✓ 비밀번호가 일치합니다';
        hint.className = 'form-hint success';
        return true;
    } else {
        hint.textContent = '✗ 비밀번호가 일치하지 않습니다';
        hint.className = 'form-hint error';
        return false;
    }
}

// Email availability check (mock)
let emailCheckTimeout;
function checkEmailAvailability(email) {
    const hint = document.getElementById('emailCheckHint');
    if (!hint) return;
    
    clearTimeout(emailCheckTimeout);
    
    if (!validateEmail(email)) {
        hint.textContent = '';
        hint.className = 'form-hint';
        return;
    }
    
    hint.textContent = '확인 중...';
    hint.className = 'form-hint';
    
    emailCheckTimeout = setTimeout(() => {
        // Mock API call - in reality, this would be an actual API request
        const isAvailable = !email.includes('taken'); // Simple mock logic
        
        if (isAvailable) {
            hint.textContent = '✓ 사용 가능한 이메일입니다';
            hint.className = 'form-hint success';
        } else {
            hint.textContent = '✗ 이미 사용 중인 이메일입니다';
            hint.className = 'form-hint error';
        }
    }, 500);
}

// Validate signup form
function validateSignupForm() {
    const name = document.getElementById('signupName');
    const email = document.getElementById('signupEmail');
    const password = document.getElementById('signupPassword');
    const confirmPassword = document.getElementById('confirmPassword');
    const agreeTerms = document.getElementById('agreeTerms');
    const submitBtn = document.getElementById('signupBtn');
    
    if (!submitBtn) return;
    
    const isValid = 
        name && name.value.trim() !== '' &&
        email && validateEmail(email.value) &&
        password && checkPasswordStrength(password.value).strength >= 3 &&
        confirmPassword && password.value === confirmPassword.value &&
        agreeTerms && agreeTerms.checked;
    
    submitBtn.disabled = !isValid;
}

// Login Form Handler
const loginForm = document.getElementById('loginForm');
if (loginForm) {
    setupPasswordToggles();
    
    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const email = document.getElementById('email').value;
        const password = document.getElementById('password').value;
        const rememberMe = document.getElementById('rememberMe')?.checked ?? false;
        
        try {
            const submitBtn = loginForm.querySelector('button[type="submit"]');
            submitBtn.disabled = true;
            submitBtn.textContent = '로그인 중...';
            
            // API call
            const response = await apiClient.post('/auth/login', {
                email,
                password,
                remember_me: rememberMe
            });
            
            // Store token and user info
            authManager.login(response.token, response.user);
            
            Toast.success('로그인 성공!');
            
            // Redirect to analysis page
            setTimeout(() => {
                window.location.href = 'select-analysis-type.html';
            }, 1000);
            
        } catch (error) {
            Toast.error(error.message || '로그인에 실패했습니다.');
            
            const submitBtn = loginForm.querySelector('button[type="submit"]');
            submitBtn.disabled = false;
            submitBtn.textContent = '로그인';
        }
    });
}

// Signup Form Handler
const signupForm = document.getElementById('signupForm');
if (signupForm) {
    setupPasswordToggles();
    
    const signupEmail = document.getElementById('signupEmail');
    const signupPassword = document.getElementById('signupPassword');
    const confirmPassword = document.getElementById('confirmPassword');
    
    // Email availability check
    signupEmail?.addEventListener('input', (e) => {
        checkEmailAvailability(e.target.value);
        validateSignupForm();
    });
    
    // Password strength check
    signupPassword?.addEventListener('input', (e) => {
        updatePasswordStrength(e.target.value);
        if (confirmPassword.value) checkPasswordMatch();
        validateSignupForm();
    });
    
    // Password match check
    confirmPassword?.addEventListener('input', () => {
        checkPasswordMatch();
        validateSignupForm();
    });
    
    // Form validation on all inputs
    signupForm.querySelectorAll('input').forEach(input => {
        input.addEventListener('input', validateSignupForm);
        input.addEventListener('change', validateSignupForm);
    });
    
    signupForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const name = document.getElementById('signupName').value;
        const email = document.getElementById('signupEmail').value;
        const password = document.getElementById('signupPassword').value;
        
        try {
            const submitBtn = signupForm.querySelector('button[type="submit"]');
            submitBtn.disabled = true;
            submitBtn.textContent = '가입 중...';
            
            // API call
            const response = await apiClient.post('/auth/signup', {
                name,
                email,
                password
            });
            
            Toast.success('회원가입 성공! 로그인 페이지로 이동합니다.');
            
            // Redirect to login
            setTimeout(() => {
                window.location.href = 'login.html';
            }, 1500);
            
        } catch (error) {
            Toast.error(error.message || '회원가입에 실패했습니다.');
            
            const submitBtn = signupForm.querySelector('button[type="submit"]');
            submitBtn.disabled = false;
            submitBtn.textContent = '회원가입';
        }
    });
}

// Forgot Password Form Handler
const forgotPasswordForm = document.getElementById('forgotPasswordForm');
if (forgotPasswordForm) {
    forgotPasswordForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const email = document.getElementById('resetEmail').value;
        
        if (!validateEmail(email)) {
            Toast.error('올바른 이메일 주소를 입력하세요.');
            return;
        }
        
        try {
            const submitBtn = forgotPasswordForm.querySelector('button[type="submit"]');
            submitBtn.disabled = true;
            submitBtn.textContent = '전송 중...';
            
            // API call
            await apiClient.post('/auth/forgot-password', { email });
            
            // Show success card
            document.querySelector('.auth-card:first-child').style.display = 'none';
            document.getElementById('resetSuccessCard').style.display = 'block';
            document.getElementById('sentEmailAddress').textContent = email;
            
        } catch (error) {
            Toast.error(error.message || '이메일 전송에 실패했습니다.');
            
            const submitBtn = forgotPasswordForm.querySelector('button[type="submit"]');
            submitBtn.disabled = false;
            submitBtn.textContent = '재설정 링크 보내기';
        }
    });
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    validateSignupForm();
});
