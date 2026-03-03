// Analysis Page JavaScript

// Tab switching
const tabButtons = document.querySelectorAll('.tab-btn');
const tabContents = document.querySelectorAll('.tab-content');

tabButtons.forEach(button => {
    button.addEventListener('click', () => {
        const tabName = button.dataset.tab;
        
        // Remove active class from all tabs
        tabButtons.forEach(btn => btn.classList.remove('active'));
        tabContents.forEach(content => content.classList.remove('active'));
        
        // Add active class to clicked tab
        button.classList.add('active');
        document.querySelector(`[data-content="${tabName}"]`).classList.add('active');
    });
});

// Text Analysis Form
const textAnalysisForm = document.getElementById('textAnalysisForm');
if (textAnalysisForm) {
    textAnalysisForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const description = document.getElementById('productDescription').value;
        
        if (!description.trim()) {
            Toast.error('제품 설명을 입력해주세요.');
            return;
        }
        
        try {
            // Show loading state
            const submitBtn = textAnalysisForm.querySelector('button[type="submit"]');
            const originalText = submitBtn.innerHTML;
            submitBtn.disabled = true;
            submitBtn.innerHTML = `
                <svg class="spinner" width="20" height="20" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
                    <circle cx="10" cy="10" r="8" stroke="currentColor" stroke-width="2" fill="none" opacity="0.3"/>
                    <path d="M10 2a8 8 0 0 1 8 8" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/>
                </svg>
                분석 중...
            `;
            
            // API call
            const response = await apiClient.post('/analysis/text', {
                description: description,
                type: 'fto'
            });
            
            // Store analysis ID and redirect to results
            localStorage.setItem('currentAnalysis', JSON.stringify(response));
            window.location.href = `results.html?id=${response.analysis_id}`;
            
        } catch (error) {
            Toast.error(error.message || '분석 중 오류가 발생했습니다.');
            
            // Reset button
            const submitBtn = textAnalysisForm.querySelector('button[type="submit"]');
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalText;
        }
    });
}

// Image Analysis Form
const imageAnalysisForm = document.getElementById('imageAnalysisForm');
if (imageAnalysisForm) {
    imageAnalysisForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const imageUrl = document.getElementById('imageUrl').value;
        const description = document.getElementById('imageDescription').value;
        
        if (!imageUrl.trim()) {
            Toast.error('이미지 URL을 입력해주세요.');
            return;
        }
        
        // Validate URL format
        try {
            new URL(imageUrl);
        } catch {
            Toast.error('올바른 URL 형식이 아닙니다.');
            return;
        }
        
        try {
            // Show loading state
            const submitBtn = imageAnalysisForm.querySelector('button[type="submit"]');
            const originalText = submitBtn.innerHTML;
            submitBtn.disabled = true;
            submitBtn.innerHTML = `
                <svg class="spinner" width="20" height="20" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
                    <circle cx="10" cy="10" r="8" stroke="currentColor" stroke-width="2" fill="none" opacity="0.3"/>
                    <path d="M10 2a8 8 0 0 1 8 8" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/>
                </svg>
                분석 중...
            `;
            
            // API call
            const response = await apiClient.post('/analysis/image', {
                image_url: imageUrl,
                description: description || null,
                type: 'design'
            });
            
            // Store analysis ID and redirect to results
            localStorage.setItem('currentAnalysis', JSON.stringify(response));
            window.location.href = `results.html?id=${response.analysis_id}`;
            
        } catch (error) {
            Toast.error(error.message || '분석 중 오류가 발생했습니다.');
            
            // Reset button
            const submitBtn = imageAnalysisForm.querySelector('button[type="submit"]');
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalText;
        }
    });
}

// Add spinner animation styles
const style = document.createElement('style');
style.textContent = `
    @keyframes spin {
        from { transform: rotate(0deg); }
        to { transform: rotate(360deg); }
    }
    
    .spinner {
        animation: spin 1s linear infinite;
    }
`;
document.head.appendChild(style);
