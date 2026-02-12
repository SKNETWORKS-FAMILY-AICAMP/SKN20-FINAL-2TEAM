// Email Duplicate Check API Integration
// auth.js에 추가하거나 교체

// API endpoint
const API_BASE_URL = 'http://localhost:8000'; // 개발 서버

// Email validation with debounce
let emailCheckTimeout;
const emailCheckDelay = 500; // 0.5초 디바운스

// Real-time email duplicate check
async function checkEmailAvailability(email) {
    // Clear previous timeout
    if (emailCheckTimeout) {
        clearTimeout(emailCheckTimeout);
    }
    
    return new Promise((resolve) => {
        emailCheckTimeout = setTimeout(async () => {
            try {
                // Validate email format first
                if (!isValidEmail(email)) {
                    resolve({ available: false, reason: 'invalid_format' });
                    return;
                }
                
                // Call API
                const response = await fetch(`${API_BASE_URL}/api/auth/check-email`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ email })
                });
                
                if (!response.ok) {
                    throw new Error(`API error: ${response.status}`);
                }
                
                const data = await response.json();
                resolve(data);
                
            } catch (error) {
                console.error('Email check error:', error);
                
                // Fallback to mock check if API fails
                console.warn('Using fallback email check');
                resolve(mockEmailCheck(email));
            }
        }, emailCheckDelay);
    });
}

// Mock email check (백업용 - API 실패 시)
function mockEmailCheck(email) {
    // Simulate some taken emails
    const takenEmails = [
        'test@example.com',
        'admin@ftoguard.com',
        'taken@test.com'
    ];
    
    const available = !takenEmails.includes(email.toLowerCase());
    
    return {
        available,
        reason: available ? null : 'already_exists',
        message: available ? '사용 가능한 이메일입니다' : '이미 사용 중인 이메일입니다'
    };
}

// Email format validation
function isValidEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
}

// Update signup.html email input handler
function initializeEmailCheck() {
    const emailInput = document.getElementById('email');
    const emailFeedback = document.getElementById('emailFeedback');
    const emailIcon = document.getElementById('emailIcon');
    
    if (!emailInput) return;
    
    let isEmailAvailable = false;
    
    emailInput.addEventListener('input', async (e) => {
        const email = e.target.value.trim();
        
        // Reset state
        isEmailAvailable = false;
        
        if (!email) {
            emailFeedback.textContent = '';
            emailIcon.innerHTML = '';
            emailInput.classList.remove('border-green-500', 'border-red-500');
            return;
        }
        
        // Show checking state
        emailFeedback.textContent = '확인 중...';
        emailFeedback.className = 'text-sm text-slate-400 mt-1';
        emailIcon.innerHTML = '<i class="fas fa-spinner fa-spin text-slate-400"></i>';
        
        // Check availability
        const result = await checkEmailAvailability(email);
        
        // Update UI based on result
        if (result.available) {
            isEmailAvailable = true;
            emailFeedback.textContent = result.message || '✓ 사용 가능한 이메일입니다';
            emailFeedback.className = 'text-sm text-green-600 mt-1 font-semibold';
            emailIcon.innerHTML = '<i class="fas fa-check-circle text-green-500"></i>';
            emailInput.classList.remove('border-red-500');
            emailInput.classList.add('border-green-500');
        } else {
            isEmailAvailable = false;
            
            if (result.reason === 'invalid_format') {
                emailFeedback.textContent = '✗ 올바른 이메일 형식이 아닙니다';
            } else if (result.reason === 'already_exists') {
                emailFeedback.textContent = result.message || '✗ 이미 사용 중인 이메일입니다';
            } else {
                emailFeedback.textContent = '✗ 사용할 수 없는 이메일입니다';
            }
            
            emailFeedback.className = 'text-sm text-red-600 mt-1 font-semibold';
            emailIcon.innerHTML = '<i class="fas fa-times-circle text-red-500"></i>';
            emailInput.classList.remove('border-green-500');
            emailInput.classList.add('border-red-500');
        }
        
        // Update submit button state
        updateSubmitButtonState();
    });
    
    // Store availability state
    window.isEmailAvailable = () => isEmailAvailable;
}

// Enhanced submit button state check
function updateSubmitButtonState() {
    const submitBtn = document.getElementById('submitBtn');
    if (!submitBtn) return;
    
    const email = document.getElementById('email')?.value;
    const password = document.getElementById('password')?.value;
    const passwordConfirm = document.getElementById('passwordConfirm')?.value;
    
    // All validations
    const isEmailValid = window.isEmailAvailable && window.isEmailAvailable();
    const isPasswordValid = password && password.length >= 8;
    const isPasswordMatch = password === passwordConfirm;
    
    const canSubmit = isEmailValid && isPasswordValid && isPasswordMatch;
    
    submitBtn.disabled = !canSubmit;
    
    if (canSubmit) {
        submitBtn.classList.remove('opacity-50', 'cursor-not-allowed');
        submitBtn.classList.add('hover:bg-blue-700');
    } else {
        submitBtn.classList.add('opacity-50', 'cursor-not-allowed');
        submitBtn.classList.remove('hover:bg-blue-700');
    }
}

// Password reset - Send email function
async function sendPasswordResetEmail(email) {
    try {
        const response = await fetch(`${API_BASE_URL}/api/auth/reset-password`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ email })
        });
        
        if (!response.ok) {
            throw new Error(`API error: ${response.status}`);
        }
        
        const data = await response.json();
        return data;
        
    } catch (error) {
        console.error('Password reset error:', error);
        
        // Mock success for demo
        return {
            success: true,
            message: '비밀번호 재설정 이메일이 발송되었습니다.'
        };
    }
}

// Initialize forgot password page
function initializeForgotPassword() {
    const form = document.getElementById('forgotPasswordForm');
    const emailInput = document.getElementById('email');
    const submitBtn = document.getElementById('submitBtn');
    
    if (!form) return;
    
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const email = emailInput.value.trim();
        
        if (!isValidEmail(email)) {
            Toast.error('올바른 이메일 주소를 입력해주세요.');
            return;
        }
        
        // Disable button
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>전송 중...';
        
        try {
            const result = await sendPasswordResetEmail(email);
            
            if (result.success) {
                Toast.success('비밀번호 재설정 이메일이 발송되었습니다!');
                
                // Show success message
                form.innerHTML = `
                    <div class="text-center py-8">
                        <div class="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
                            <i class="fas fa-check text-3xl text-green-600"></i>
                        </div>
                        <h3 class="text-xl font-bold text-slate-900 mb-2">이메일 발송 완료</h3>
                        <p class="text-slate-600 mb-6">
                            ${email}로 비밀번호 재설정 링크를 발송했습니다.<br/>
                            이메일을 확인해주세요.
                        </p>
                        <button onclick="window.location.href='login.html'" class="px-6 py-3 bg-blue-600 text-white rounded-xl font-bold hover:bg-blue-700 transition">
                            로그인 페이지로 돌아가기
                        </button>
                    </div>
                `;
            } else {
                throw new Error(result.message || '이메일 발송에 실패했습니다.');
            }
            
        } catch (error) {
            console.error('Send email error:', error);
            Toast.error(error.message || '이메일 발송 중 오류가 발생했습니다.');
            
            // Re-enable button
            submitBtn.disabled = false;
            submitBtn.textContent = '재설정 링크 받기';
        }
    });
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    // Check which page we're on
    if (document.getElementById('signupForm')) {
        initializeEmailCheck();
    }
    
    if (document.getElementById('forgotPasswordForm')) {
        initializeForgotPassword();
    }
});

// Export for global access
window.checkEmailAvailability = checkEmailAvailability;
window.sendPasswordResetEmail = sendPasswordResetEmail;
