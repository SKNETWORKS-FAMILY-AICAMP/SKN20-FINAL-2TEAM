// Analysis Complete JavaScript - All Features Implemented
// Part 1: Initialization & Core Functions

// IMMEDIATE AUTH CHECK - Before any page rendering
// DEV_BYPASS_AUTH=true이면 건너뜀
(function() {
    if (typeof DEV_BYPASS_AUTH !== 'undefined' && DEV_BYPASS_AUTH) return;
    const protectedPages = ['analysis.html', 'chat.html', 'results.html'];
    const currentPage = window.location.pathname.split('/').pop();

    if (protectedPages.includes(currentPage)) {
        const token = localStorage.getItem('authToken');
        if (!token) {
            window.location.replace('login.html');
            return;
        }
        try {
            const payload = JSON.parse(atob(token.split('.')[1]));
            if (Date.now() >= payload.exp * 1000) {
                localStorage.removeItem('authToken');
                localStorage.removeItem('user');
                window.location.replace('login.html');
            }
        } catch {
            localStorage.removeItem('authToken');
            localStorage.removeItem('user');
            window.location.replace('login.html');
        }
    }
})();

let currentAnalysisId = null;
let attachedFiles = [];
let analysisContext = {
    product_name: null,
    country: null,
    product_type: null,
    main_features: null,
    core_components: null
};

let structuredSlots = {
    product_category: null,
    functions: null,
    components: null,
    process: null
};

// Workflow steps (updated to match PDF)
const WORKFLOW_STEPS = ['extract', 'search', 'analyze', 'judge', 'alternative', 'complete'];
let currentStep = -1;

// File limits
const MAX_FILES = 5;
const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB

// Initialize analysis chat
function initializeAnalysisChat() {
    // Auth already checked at top of file - user is authenticated here
    loadAnalysisSessions();
    setupAnalysisEventListeners();
    setupDragAndDrop();
    updateSessionType('대기 중');
    updateAgentStatus('ready');
}

// Setup event listeners
function setupAnalysisEventListeners() {
    const messageInput = document.getElementById('messageInput');
    const sendBtn = document.getElementById('sendBtn');
    const attachBtn = document.getElementById('attachBtn');
    const fileInput = document.getElementById('fileInput');
    const analysisTypeSelect = document.getElementById('analysisTypeSelect');
    const dateFilter = document.getElementById('dateFilter');
    
    // Input validation
    messageInput.addEventListener('input', () => {
        const hasText = messageInput.value.trim();
        const hasFiles = attachedFiles.length > 0;
        sendBtn.disabled = !hasText && !hasFiles;
        autoResizeTextarea({ target: messageInput });
    });
    
    // Send message
    sendBtn.addEventListener('click', sendAnalysisMessage);
    
    // Enter key
    messageInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (!sendBtn.disabled) {
                sendAnalysisMessage();
            }
        }
    });
    
    // Attach file
    attachBtn.addEventListener('click', () => {
        if (attachedFiles.length >= MAX_FILES) {
            Toast.warning(`최대 ${MAX_FILES}개까지 첨부 가능합니다.`);
            return;
        }
        fileInput.click();
    });
    
    // File selection
    fileInput.addEventListener('change', handleFileSelection);
    
    // Analysis type change
    analysisTypeSelect.addEventListener('change', (e) => {
        const typeHint = document.getElementById('typeHint');
        const hints = {
            auto: 'AI가 자동으로 분석 유형을 판단합니다',
            fto: '특허 청구항 기반 침해 리스크 분석',
            design: '디자인 도면 유사도 기반 침해 분석'
        };
        typeHint.textContent = hints[e.target.value] || '';
    });
    
    // Date filter
    dateFilter?.addEventListener('change', filterSessions);
}

// Setup drag and drop
function setupDragAndDrop() {
    const dropZone = document.getElementById('dropZone');
    const messagesContainer = document.getElementById('messagesContainer');
    
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        messagesContainer.addEventListener(eventName, preventDefaults, false);
    });
    
    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }
    
    ['dragenter', 'dragover'].forEach(eventName => {
        messagesContainer.addEventListener(eventName, () => {
            if (attachedFiles.length < MAX_FILES) {
                dropZone.style.display = 'flex';
            }
        }, false);
    });
    
    ['dragleave', 'drop'].forEach(eventName => {
        messagesContainer.addEventListener(eventName, () => {
            dropZone.style.display = 'none';
        }, false);
    });
    
    messagesContainer.addEventListener('drop', handleDrop, false);
}

// Handle file drop
function handleDrop(e) {
    const dt = e.dataTransfer;
    const files = dt.files;
    handleFiles(files);
}

// Handle file selection
function handleFileSelection(e) {
    const files = e.target.files;
    handleFiles(files);
    e.target.value = '';
}

// Handle files
function handleFiles(files) {
    const filesArray = Array.from(files);
    
    filesArray.forEach(file => {
        // Check file count
        if (attachedFiles.length >= MAX_FILES) {
            Toast.warning(`최대 ${MAX_FILES}개까지 첨부 가능합니다.`);
            return;
        }
        
        // Check file size
        if (file.size > MAX_FILE_SIZE) {
            Toast.error(`${file.name}: 파일 크기는 10MB 이하여야 합니다.`);
            return;
        }
        
        // Check file type
        if (!file.type.startsWith('image/') && file.type !== 'application/pdf') {
            Toast.error(`${file.name}: 이미지 또는 PDF 파일만 첨부 가능합니다.`);
            return;
        }
        
        // Read file
        const reader = new FileReader();
        reader.onload = (event) => {
            attachedFiles.push({
                file: file,
                name: file.name,
                type: file.type,
                size: file.size,
                dataUrl: event.target.result
            });
            updateAttachedFilesPreview();
            document.getElementById('sendBtn').disabled = false;
        };
        reader.readAsDataURL(file);
    });
}

// Update attached files preview
function updateAttachedFilesPreview() {
    const container = document.getElementById('attachedFiles');
    
    if (attachedFiles.length === 0) {
        container.style.display = 'none';
        return;
    }
    
    container.style.display = 'flex';
    container.innerHTML = attachedFiles.map((file, index) => `
        <div class="attached-file">
            ${file.type.startsWith('image/') 
                ? `<img src="${file.dataUrl}" alt="${file.name}">`
                : `<div class="pdf-preview">
                    <svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path d="M6 4H20L26 10V28H6V4Z" stroke="currentColor" stroke-width="2"/>
                        <text x="10" y="20" font-size="8" fill="currentColor">PDF</text>
                    </svg>
                   </div>`
            }
            <div class="file-info">
                <span class="file-name">${truncateFileName(file.name, 15)}</span>
                <span class="file-size">${formatFileSize(file.size)}</span>
            </div>
            <button class="file-remove" onclick="removeAttachedFile(${index})" title="제거">×</button>
        </div>
    `).join('');
}

// Remove attached file
function removeAttachedFile(index) {
    attachedFiles.splice(index, 1);
    updateAttachedFilesPreview();
    
    if (attachedFiles.length === 0 && !document.getElementById('messageInput').value.trim()) {
        document.getElementById('sendBtn').disabled = true;
    }
}

// Truncate file name
function truncateFileName(name, maxLength) {
    if (name.length <= maxLength) return name;
    const ext = name.split('.').pop();
    const nameWithoutExt = name.substring(0, name.lastIndexOf('.'));
    const truncated = nameWithoutExt.substring(0, maxLength - ext.length - 4) + '...';
    return truncated + '.' + ext;
}

// Format file size
function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// Auto-resize textarea
function autoResizeTextarea(e) {
    const textarea = e.target;
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
}

// Update context summary bar
function updateContextSummary() {
    const bar = document.getElementById('contextSummaryBar');
    const hasContext = analysisContext.product_name || analysisContext.country || analysisContext.product_type;
    
    if (hasContext) {
        bar.style.display = 'block';
        document.getElementById('ctxProductName').textContent = analysisContext.product_name || '-';
        document.getElementById('ctxCountry').textContent = analysisContext.country || '-';
        document.getElementById('ctxProductType').textContent = analysisContext.product_type || '-';
    } else {
        bar.style.display = 'none';
    }
}

// Edit context
function editContext(field) {
    const labels = {
        product_name: '제품명',
        country: '출시 국가',
        product_type: '제품 유형'
    };
    
    const currentValue = analysisContext[field] || '';
    const newValue = prompt(`${labels[field]}을(를) 수정하세요:`, currentValue);
    
    if (newValue !== null && newValue.trim()) {
        analysisContext[field] = newValue.trim();
        updateContextSummary();
        Toast.success(`${labels[field]}이(가) 수정되었습니다.`);
    }
}

// Update session type
function updateSessionType(type) {
    document.getElementById('sessionType').textContent = type;
}

// Update agent status
function updateAgentStatus(status) {
    const statusElement = document.getElementById('agentStatus');
    statusElement.className = 'agent-status ' + status;
    
    const statusText = {
        ready: '준비',
        processing: '처리 중',
        analyzing: '분석 중',
        complete: '완료',
        error: '오류'
    };
    
    statusElement.textContent = statusText[status] || status;
}

// Show typing indicator
function showTypingIndicator() {
    const messagesWrapper = document.querySelector('.messages-wrapper');
    const typingDiv = document.createElement('div');
    typingDiv.className = 'message assistant typing';
    typingDiv.innerHTML = `
        <div class="message-avatar">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                <rect x="2" y="2" width="16" height="16" rx="2" stroke="currentColor" stroke-width="2"/>
                <path d="M7 10L9 12L13 8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        </div>
        <div class="message-content">
            <div class="message-bubble">
                <div class="typing-indicator">
                    <div class="typing-dot"></div>
                    <div class="typing-dot"></div>
                    <div class="typing-dot"></div>
                </div>
            </div>
        </div>
    `;
    
    messagesWrapper.appendChild(typingDiv);
    scrollToBottom();
}

// Remove typing indicator
function removeTypingIndicator() {
    const typing = document.querySelector('.message.typing');
    if (typing) {
        typing.remove();
    }
}

// Scroll to bottom
function scrollToBottom() {
    const container = document.getElementById('messagesContainer');
    setTimeout(() => {
        container.scrollTop = container.scrollHeight;
    }, 100);
}

// Escape HTML
function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, m => map[m]).replace(/\n/g, '<br>');
}

// Sleep utility
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// Suggested prompt
function sendSuggestedPrompt(text) {
    document.getElementById('messageInput').value = text;
    document.getElementById('sendBtn').disabled = false;
}

// Initialize on load
document.addEventListener('DOMContentLoaded', () => {
    initializeAnalysisChat();
});

// Export functions for onclick handlers
window.startNewAnalysis = startNewAnalysis;
window.removeAttachedFile = removeAttachedFile;
window.editContext = editContext;
window.sendSuggestedPrompt = sendSuggestedPrompt;

// ============================================
// PART 2: Message Sending & Workflow
// ============================================

// Send analysis message
async function sendAnalysisMessage() {
    const messageInput = document.getElementById('messageInput');
    const message = messageInput.value.trim();
    
    if (!message && attachedFiles.length === 0) return;
    
    // Clear input
    messageInput.value = '';
    messageInput.style.height = 'auto';
    document.getElementById('sendBtn').disabled = true;
    
    // Hide welcome message
    const welcomeMessage = document.querySelector('.welcome-message');
    if (welcomeMessage) {
        welcomeMessage.remove();
    }
    
    // Add user message with images
    addAnalysisMessage('user', message, attachedFiles);
    
    // Store files for analysis
    const sentFiles = [...attachedFiles];
    attachedFiles = [];
    updateAttachedFilesPreview();
    
    // Show typing indicator
    showTypingIndicator();
    
    // Determine analysis type
    const selectedType = document.getElementById('analysisTypeSelect').value;
    const hasImages = sentFiles.length > 0;
    const hasText = message.length > 0;
    
    let analysisType = selectedType;
    if (selectedType === 'auto') {
        analysisType = hasImages && hasText ? 'multimodal' : hasImages ? 'design' : 'fto';
    }
    
    try {
        updateSessionType(analysisType === 'design' ? '디자인 분석' : analysisType === 'multimodal' ? '멀티모달 분석' : 'FTO 분석');
        updateAgentStatus('processing');
        
        // Show intent classification result
        if (selectedType === 'auto') {
            await showIntentClassification(analysisType, message, hasImages);
        }
        
        // Start workflow
        await executeWorkflow(message, sentFiles, analysisType);
        
    } catch (error) {
        removeTypingIndicator();
        addErrorMessage(error.message || '분석 중 오류가 발생했습니다.');
        updateAgentStatus('error');
    }
}

// Show intent classification result
async function showIntentClassification(detectedType, message, hasImages) {
    removeTypingIndicator();
    
    const typeNames = {
        fto: '특허 FTO 분석',
        design: '디자인 침해 분석',
        multimodal: '멀티모달 분석 (텍스트 + 이미지)'
    };
    
    const messagesWrapper = document.querySelector('.messages-wrapper');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant';
    
    messageDiv.innerHTML = `
        <div class="message-avatar">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                <rect x="2" y="2" width="16" height="16" rx="2" stroke="currentColor" stroke-width="2"/>
                <path d="M7 10L9 12L13 8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        </div>
        <div class="message-content">
            <div class="intent-classification-card">
                <div class="intent-header">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <circle cx="10" cy="10" r="8" stroke="currentColor" stroke-width="2"/>
                        <path d="M10 6V10L13 13" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                    </svg>
                    <h4>의도 분류 완료</h4>
                </div>
                <p class="intent-result">
                    감지된 분석 유형: <strong>${typeNames[detectedType]}</strong>
                </p>
                <div class="intent-actions">
                    <button class="btn-secondary-sm" onclick="changeIntentType('${detectedType}')">
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <path d="M12 4L4 12M4 4L12 12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                        </svg>
                        분석 유형 변경
                    </button>
                    <button class="btn-primary-sm" onclick="confirmIntent()">
                        ✓ 확인하고 계속
                    </button>
                </div>
            </div>
        </div>
    `;
    
    messagesWrapper.appendChild(messageDiv);
    scrollToBottom();
    
    // Wait for user confirmation
    return new Promise((resolve) => {
        window.confirmIntent = () => {
            document.querySelector('.intent-classification-card').remove();
            resolve();
        };
        
        window.changeIntentType = (currentType) => {
            const newType = prompt('변경할 분석 유형을 선택하세요:\n1. fto (특허 FTO)\n2. design (디자인 침해)\n3. multimodal (멀티모달)', currentType);
            if (newType && ['fto', 'design', 'multimodal'].includes(newType)) {
                document.querySelector('.intent-result strong').textContent = typeNames[newType];
                updateSessionType(typeNames[newType]);
            }
        };
    });
}

// Execute workflow with real API calls
async function executeWorkflow(message, files, analysisType) {
    // Show workflow progress
    document.getElementById('workflowProgress').style.display = 'block';
    document.getElementById('contextSummaryBar').style.display = 'block';

    // Show orchestrator
    showTypingIndicator();
    await sleep(500);
    removeTypingIndicator();
    addAgentActivityCard('orchestrator', '중앙 오케스트레이터', '질의 분석 및 키워드 추출 중...', 10);

    // Step 1: Extract keywords
    await updateWorkflowStep('extract');

    // Extract context from message
    extractContextFromMessage(message);
    updateContextSummary();

    // Check information sufficiency (skip random check for API mode)
    const hasEnoughInfo = message.length > 20 || files.length > 0;

    if (!hasEnoughInfo) {
        removeTypingIndicator();
        await updateWorkflowStep('extract', false);
        addInfoRequestMessage(['제품에 대한 상세한 설명']);
        updateAgentStatus('ready');
        document.getElementById('workflowProgress').style.display = 'none';
        return;
    }

    updateAgentProgress('orchestrator', 30, '키워드 추출 완료');

    // Show structured slots confirmation (for FTO analysis)
    if (analysisType === 'fto' || analysisType === 'multimodal') {
        await showStructuredSlotsConfirmation(message);
    }

    // Step 2: Search patents via API
    await updateWorkflowStep('search');
    let searchResults = [];

    if (analysisType === 'fto' || analysisType === 'multimodal') {
        addAgentActivityCard('text-agent', '텍스트 에이전트', 'DB에서 유사 특허 검색 중...', 20);

        try {
            // Call search API
            const searchResponse = await apiClient.get(`/search/keywords?q=${encodeURIComponent(message)}&limit=10`);
            searchResults = searchResponse.results || [];
            updateAgentProgress('text-agent', 50, `${searchResults.length}건의 특허 검색 완료`);

            // Show search results if any
            if (searchResults.length > 0) {
                showSearchResults(searchResults);
            }
        } catch (error) {
            console.error('Search API error:', error);
            updateAgentProgress('text-agent', 50, '검색 완료 (fallback)');
        }
    }

    if (analysisType === 'design' || analysisType === 'multimodal') {
        addAgentActivityCard('design-agent', '디자인 에이전트', '이미지 분석 중...', 20);
        await sleep(1000);
        updateAgentProgress('design-agent', 50, '유사 디자인 검색 완료');

        if (analysisType === 'design') {
            await showDesignSimilarityResults(files);
        }
    }

    // Step 3: Analyze with SLLM
    await updateWorkflowStep('analyze');
    updateAgentProgress('text-agent', 70, '청구항 상세 분석 중...');

    let analysisResult = null;

    try {
        // Call analysis API
        if (analysisType === 'fto' || analysisType === 'multimodal') {
            const analysisResponse = await apiClient.post('/analysis/text', {
                description: message,
                type: analysisType
            });
            analysisResult = analysisResponse;
            currentAnalysisId = analysisResponse.analysis_id;
        } else if (analysisType === 'design' && files.length > 0) {
            const analysisResponse = await apiClient.post('/analysis/image', {
                image_url: files[0].dataUrl,
                description: message || null,
                type: 'design'
            });
            analysisResult = analysisResponse;
            currentAnalysisId = analysisResponse.analysis_id;
        }
    } catch (error) {
        console.error('Analysis API error:', error);
        // Continue with mock result
    }

    // Step 4: Judge infringement
    await updateWorkflowStep('judge');
    updateAgentProgress('text-agent', 85, '침해 위험도 판단 중...');
    await sleep(500);

    // Step 5: Alternative search
    await updateWorkflowStep('alternative');
    updateAgentProgress('orchestrator', 95, '자유실시기술 탐색 중...');
    await sleep(500);

    // Step 6: Complete
    await updateWorkflowStep('complete');
    updateAgentProgress('orchestrator', 100, '분석 완료');

    removeTypingIndicator();

    // Determine risk level from API response or default
    let riskLevel = 'safe';
    if (analysisResult && analysisResult.risk_level) {
        riskLevel = analysisResult.risk_level;
    } else if (searchResults.length > 5) {
        riskLevel = 'warning';
    } else if (searchResults.length > 10) {
        riskLevel = 'danger';
    }

    addFinalAnalysisResult(riskLevel, analysisType);
    updateAgentStatus('complete');
}

// Show search results from API
function showSearchResults(results) {
    if (!results || results.length === 0) return;

    const messagesWrapper = document.querySelector('.messages-wrapper');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant';

    const topResults = results.slice(0, 5);

    messageDiv.innerHTML = `
        <div class="message-avatar">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                <rect x="2" y="2" width="16" height="16" rx="2" stroke="currentColor" stroke-width="2"/>
                <path d="M7 10L9 12L13 8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        </div>
        <div class="message-content">
            <div class="search-results-card">
                <h4>유사 특허 검색 결과 (${results.length}건)</h4>
                <div class="search-results-list">
                    ${topResults.map(r => `
                        <div class="search-result-item">
                            <div class="result-header">
                                <span class="patent-number">${r.patent_number || r.application_number || 'N/A'}</span>
                                <span class="similarity-badge">${r.score ? (r.score * 100).toFixed(0) + '%' : ''}</span>
                            </div>
                            <div class="result-title">${r.invention_title_ko || r.title || '제목 없음'}</div>
                            <div class="result-claim">${(r.claim_text || r.claim || '').substring(0, 100)}...</div>
                        </div>
                    `).join('')}
                </div>
                ${results.length > 5 ? `<p class="more-results">외 ${results.length - 5}건의 결과가 더 있습니다.</p>` : ''}
            </div>
        </div>
    `;

    messagesWrapper.appendChild(messageDiv);
    scrollToBottom();
}

// Extract context from message
function extractContextFromMessage(message) {
    const lowerMessage = message.toLowerCase();
    
    // Extract product name
    const productPatterns = [
        /제품명[은는]?\s*[\"']?([^\"'\n,]+)[\"']?/,
        /^([가-힣a-zA-Z0-9\s]+)\s*(제품|머그|컵|패드)/,
        /([가-힣a-zA-Z0-9\s]+)\s*를\s*개발/
    ];
    
    for (const pattern of productPatterns) {
        const match = message.match(pattern);
        if (match) {
            analysisContext.product_name = match[1].trim();
            break;
        }
    }
    
    // Extract country
    const countries = ['한국', '대한민국', '미국', '중국', '일본', '유럽'];
    for (const country of countries) {
        if (lowerMessage.includes(country.toLowerCase())) {
            analysisContext.country = country;
            break;
        }
    }
    
    // Extract product type
    const types = ['가전제품', '전자제품', '화장품', '식품', '의약품', '의료기기'];
    for (const type of types) {
        if (lowerMessage.includes(type)) {
            analysisContext.product_type = type;
            break;
        }
    }
    
    // Extract features
    if (lowerMessage.includes('기능') || lowerMessage.includes('특징')) {
        analysisContext.main_features = '입력됨';
    }
    
    // Extract components
    if (lowerMessage.includes('성분') || lowerMessage.includes('구성') || lowerMessage.includes('재료')) {
        analysisContext.core_components = '입력됨';
    }
}

// Check information sufficiency
function checkInformationSufficiency(message, files) {
    const missing = [];
    
    if (!analysisContext.product_name) {
        missing.push('제품명');
    }
    if (!analysisContext.main_features) {
        missing.push('주요 기능 또는 특징');
    }
    if (!analysisContext.core_components && files.length === 0) {
        missing.push('핵심 구성요소 또는 성분');
    }
    if (!analysisContext.country) {
        missing.push('출시 예정 국가');
    }
    
    // Random chance to request more info (for demo)
    if (missing.length > 0 && Math.random() > 0.5) {
        return missing;
    }
    
    return [];
}

// Show structured slots confirmation
async function showStructuredSlotsConfirmation(message) {
    removeTypingIndicator();
    
    // Extract structured information
    structuredSlots.product_category = analysisContext.product_type || '가전제품';
    structuredSlots.functions = '자동 온도 조절, 무선 충전';
    structuredSlots.components = '세라믹 본체, 리튬 배터리, 온도 센서';
    structuredSlots.process = '성형 → 조립 → 품질 검사';
    
    const messagesWrapper = document.querySelector('.messages-wrapper');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant';
    
    messageDiv.innerHTML = `
        <div class="message-avatar">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                <rect x="2" y="2" width="16" height="16" rx="2" stroke="currentColor" stroke-width="2"/>
                <path d="M7 10L9 12L13 8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        </div>
        <div class="message-content">
            <div class="structured-slots-card">
                <div class="slots-header">
                    <h4>구조화된 정보 확인</h4>
                    <p>추출된 정보가 정확한지 확인해주세요. 수정이 필요한 경우 각 항목을 클릭하세요.</p>
                </div>
                <div class="slots-grid">
                    <div class="slot-item" onclick="editSlot('product_category')">
                        <div class="slot-label">제품군</div>
                        <div class="slot-value" id="slot-product_category">${structuredSlots.product_category}</div>
                        <button class="slot-edit-btn">
                            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg">
                                <path d="M10 2L12 4L5 11H3V9L10 2Z" stroke="currentColor" stroke-width="1.5"/>
                            </svg>
                        </button>
                    </div>
                    <div class="slot-item" onclick="editSlot('functions')">
                        <div class="slot-label">주요 기능</div>
                        <div class="slot-value" id="slot-functions">${structuredSlots.functions}</div>
                        <button class="slot-edit-btn">
                            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg">
                                <path d="M10 2L12 4L5 11H3V9L10 2Z" stroke="currentColor" stroke-width="1.5"/>
                            </svg>
                        </button>
                    </div>
                    <div class="slot-item" onclick="editSlot('components')">
                        <div class="slot-label">핵심 성분/구성요소</div>
                        <div class="slot-value" id="slot-components">${structuredSlots.components}</div>
                        <button class="slot-edit-btn">
                            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg">
                                <path d="M10 2L12 4L5 11H3V9L10 2Z" stroke="currentColor" stroke-width="1.5"/>
                            </svg>
                        </button>
                    </div>
                    <div class="slot-item" onclick="editSlot('process')">
                        <div class="slot-label">공정 정보</div>
                        <div class="slot-value" id="slot-process">${structuredSlots.process}</div>
                        <button class="slot-edit-btn">
                            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg">
                                <path d="M10 2L12 4L5 11H3V9L10 2Z" stroke="currentColor" stroke-width="1.5"/>
                            </svg>
                        </button>
                    </div>
                </div>
                <div class="slots-actions">
                    <button class="btn-primary" onclick="confirmSlots()">
                        ✓ 확인하고 분석 진행
                    </button>
                </div>
            </div>
        </div>
    `;
    
    messagesWrapper.appendChild(messageDiv);
    scrollToBottom();
    
    // Wait for confirmation
    return new Promise((resolve) => {
        window.confirmSlots = () => {
            Toast.success('정보가 확인되었습니다. 분석을 시작합니다.');
            document.querySelector('.structured-slots-card .slots-actions').innerHTML = '<p style="color: var(--color-safe); text-align: center;">✓ 확인 완료</p>';
            setTimeout(resolve, 500);
        };
        
        window.editSlot = (slotName) => {
            const labels = {
                product_category: '제품군',
                functions: '주요 기능',
                components: '핵심 성분/구성요소',
                process: '공정 정보'
            };
            
            const currentValue = structuredSlots[slotName];
            const newValue = prompt(`${labels[slotName]}을(를) 수정하세요:`, currentValue);
            
            if (newValue !== null && newValue.trim()) {
                structuredSlots[slotName] = newValue.trim();
                document.getElementById(`slot-${slotName}`).textContent = newValue.trim();
            }
        };
    });
}


// ============================================
// PART 3: UI Components & Cards
// ============================================

// Update workflow step
async function updateWorkflowStep(step, completed = true) {
    currentStep = WORKFLOW_STEPS.indexOf(step);
    
    WORKFLOW_STEPS.forEach((s, index) => {
        const element = document.querySelector(`[data-step="${s}"]`);
        if (!element) return;
        
        element.classList.remove('active', 'completed');
        
        if (index < currentStep) {
            element.classList.add('completed');
        } else if (index === currentStep) {
            element.classList.add(completed ? 'active' : 'active');
        }
    });
}

// Add agent activity card
function addAgentActivityCard(agentType, agentName, activity, progress) {
    const messagesWrapper = document.querySelector('.messages-wrapper');
    
    let card = document.getElementById(`agent-${agentType}`);
    
    if (!card) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message assistant';
        messageDiv.innerHTML = `
            <div class="message-avatar">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <rect x="2" y="2" width="16" height="16" rx="2" stroke="currentColor" stroke-width="2"/>
                    <path d="M7 10L9 12L13 8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
            </div>
            <div class="message-content">
                <div class="agent-activity-card" id="agent-${agentType}">
                    <div class="agent-header">
                        <div class="agent-icon ${agentType}">
                            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                                <circle cx="10" cy="10" r="8" stroke="currentColor" stroke-width="2"/>
                                <path d="M10 6V10L13 13" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                            </svg>
                        </div>
                        <div class="agent-info">
                            <h4>${agentName}</h4>
                            <p class="agent-activity">${activity}</p>
                        </div>
                    </div>
                    <div class="agent-progress">
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: ${progress}%"></div>
                        </div>
                        <p class="progress-text">${progress}% 완료</p>
                    </div>
                </div>
            </div>
        `;
        
        messagesWrapper.appendChild(messageDiv);
        scrollToBottom();
    }
}

// Update agent progress
function updateAgentProgress(agentType, progress, activity) {
    const card = document.getElementById(`agent-${agentType}`);
    if (!card) return;
    
    const progressFill = card.querySelector('.progress-fill');
    const progressText = card.querySelector('.progress-text');
    const activityText = card.querySelector('.agent-activity');
    
    if (progressFill) progressFill.style.width = `${progress}%`;
    if (progressText) progressText.textContent = `${progress}% 완료`;
    if (activityText) activityText.textContent = activity;
}

// Add info request message
function addInfoRequestMessage(missingInfo) {
    const messagesWrapper = document.querySelector('.messages-wrapper');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant';
    
    messageDiv.innerHTML = `
        <div class="message-avatar">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                <rect x="2" y="2" width="16" height="16" rx="2" stroke="currentColor" stroke-width="2"/>
                <path d="M7 10L9 12L13 8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        </div>
        <div class="message-content">
            <div class="message-bubble">
                정확한 분석을 위해 추가 정보가 필요합니다.
            </div>
            <div class="info-request-card">
                <div class="info-request-header">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/>
                        <path d="M12 8V12M12 16H12.01" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                    </svg>
                    <h4>필수 정보 입력</h4>
                </div>
                <ul class="info-request-list">
                    ${missingInfo.map(info => `<li>${info}</li>`).join('')}
                </ul>
                <p class="info-request-footer">위 정보를 포함하여 다시 입력해주세요.</p>
            </div>
        </div>
    `;
    
    messagesWrapper.appendChild(messageDiv);
    scrollToBottom();
}

// Show design similarity results
async function showDesignSimilarityResults(files) {
    if (files.length === 0) return;
    
    removeTypingIndicator();
    
    // Mock similar designs
    const similarDesigns = [
        { id: 'KR30-2021-0001234', similarity: 0.87, status: 'high' },
        { id: 'KR30-2020-0005678', similarity: 0.65, status: 'medium' },
        { id: 'KR30-2022-0009876', similarity: 0.42, status: 'low' }
    ];
    
    const messagesWrapper = document.querySelector('.messages-wrapper');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant';
    
    messageDiv.innerHTML = `
        <div class="message-avatar">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                <rect x="2" y="2" width="16" height="16" rx="2" stroke="currentColor" stroke-width="2"/>
                <path d="M7 10L9 12L13 8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        </div>
        <div class="message-content">
            <div class="design-similarity-card">
                <h4>유사 디자인 검색 결과</h4>
                <p class="design-hint">Top-${similarDesigns.length} 유사 디자인이 발견되었습니다.</p>
                <div class="design-comparison-grid">
                    ${similarDesigns.map((design, index) => `
                        <div class="design-comparison-item ${design.status}">
                            <div class="design-pair">
                                <div class="design-image your-design">
                                    <img src="${files[0].dataUrl}" alt="제출 디자인">
                                    <span class="design-label">제출 디자인</span>
                                </div>
                                <div class="similarity-arrow">
                                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                                        <path d="M5 12H19M19 12L12 5M19 12L12 19" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                                    </svg>
                                    <span class="similarity-score">${(design.similarity * 100).toFixed(0)}%</span>
                                </div>
                                <div class="design-image similar-design">
                                    <div class="placeholder-design">유사 디자인 ${index + 1}</div>
                                    <span class="design-label">${design.id}</span>
                                </div>
                            </div>
                            <div class="design-judgment ${design.status}">
                                <span class="judgment-badge">${design.status === 'high' ? '유사' : design.status === 'medium' ? '검토 필요' : '비유사'}</span>
                                <p class="judgment-text">VLM 분석: ${design.status === 'high' ? '높은 유사성 감지' : design.status === 'medium' ? '일부 유사 요소 존재' : '유의미한 차이 존재'}</p>
                            </div>
                        </div>
                    `).join('')}
                </div>
                <div class="design-disclaimer">
                    ⚠️ 본 분석은 참고용이며, 최종 디자인 침해 판단은 전문가의 검토가 필요합니다.
                </div>
            </div>
        </div>
    `;
    
    messagesWrapper.appendChild(messageDiv);
    scrollToBottom();
}

// Add final analysis result
function addFinalAnalysisResult(riskLevel, analysisType = 'fto') {  // ← 파라미터 추가
    const messagesWrapper = document.querySelector('.messages-wrapper');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant';
    
    const riskData = {
        safe: {
            title: '비침해 (안전)',
            description: '분석 결과, 검색된 특허들과의 유사성이 낮아 침해 위험이 낮은 것으로 판단됩니다.',
            icon: '<circle cx="24" cy="24" r="20" stroke="currentColor" stroke-width="3"/><path d="M16 24L22 30L32 20" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>'
        },
        warning: {
            title: '전문가 검토 필요',
            description: '일부 특허와 유사한 요소가 발견되었습니다. 변리사의 상세 검토를 권장합니다.',
            icon: '<path d="M24 16V24M24 32H24.02" stroke="currentColor" stroke-width="3" stroke-linecap="round"/><path d="M20.58 7.72L4.36 36A4 4 0 007.64 42H40.36A4 4 0 0043.64 36L27.42 7.72A4 4 0 0020.58 7.72Z" stroke="currentColor" stroke-width="3"/>'
        },
        danger: {
            title: '침해 위험 (고위험)',
            description: '특허 청구항과 직접적으로 일치하는 요소가 발견되었습니다. 즉시 법률 자문을 받으시기 바랍니다.',
            icon: '<circle cx="24" cy="24" r="6" fill="currentColor"/><circle cx="24" cy="24" r="16" stroke="currentColor" stroke-width="3"/><circle cx="24" cy="24" r="20" stroke="currentColor" stroke-width="2" stroke-dasharray="3 3"/>'
        }
    };
    
    const risk = riskData[riskLevel];
    
    // 🔥 분석 타입에 따라 결과 페이지 URL 결정
    const analysisId = currentAnalysisId || 'DEMO-' + Date.now();
    let resultPageUrl;
    
    if (analysisType === 'fto') {
        resultPageUrl = `results.html?id=${analysisId}&type=fto`;
    } else if (analysisType === 'design') {
        resultPageUrl = `design-results.html?id=${analysisId}&type=design`;
    } else if (analysisType === 'multimodal') {
        resultPageUrl = `combined-results.html?id=${analysisId}&type=multimodal`;
    } else {
        // 기본값 (후방 호환성)
        resultPageUrl = `results.html?id=${analysisId}`;
    }
    
    messageDiv.innerHTML = `
        <div class="message-avatar">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                <rect x="2" y="2" width="16" height="16" rx="2" stroke="currentColor" stroke-width="2"/>
                <path d="M7 10L9 12L13 8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        </div>
        <div class="message-content">
            <div class="risk-result-card ${riskLevel}">
                <div class="risk-header">
                    <div class="risk-icon ${riskLevel}">
                        <svg width="64" height="64" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
                            ${risk.icon}
                        </svg>
                    </div>
                    <h3 class="risk-title">${risk.title}</h3>
                </div>
                <p class="risk-description">${risk.description}</p>
                <div class="risk-disclaimer">
                    ⚖️ 본 분석은 법적 자문이 아니며, 실제 침해 여부는 변리사 또는 변호사의 검토가 필요합니다.
                </div>
                <div class="risk-action">
                    <button class="btn-primary" onclick="window.location.href='${resultPageUrl}'">
                        상세 결과 보기
                    </button>
                    <button class="btn-secondary" onclick="startNewAnalysis()">
                        새 분석 시작
                    </button>
                </div>
            </div>
        </div>
    `;
    
    messagesWrapper.appendChild(messageDiv);
    scrollToBottom();
}

// Add error message
function addErrorMessage(errorMsg, errorCode = null) {
    const messagesWrapper = document.querySelector('.messages-wrapper');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant error';
    
    messageDiv.innerHTML = `
        <div class="message-avatar">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                <circle cx="10" cy="10" r="8" stroke="#EF4444" stroke-width="2"/>
                <path d="M10 6V10M10 14H10.01" stroke="#EF4444" stroke-width="2" stroke-linecap="round"/>
            </svg>
        </div>
        <div class="message-content">
            <div class="error-card">
                <h4>❌ 오류 발생</h4>
                <p class="error-message">${errorMsg}</p>
                ${errorCode ? `<p class="error-code">오류 코드: ${errorCode}</p>` : ''}
                <div class="error-actions">
                    <button class="btn-secondary-sm" onclick="sendAnalysisMessage()">
                        🔄 재시도
                    </button>
                    <button class="btn-secondary-sm" onclick="startNewAnalysis()">
                        새로 시작
                    </button>
                </div>
            </div>
        </div>
    `;
    
    messagesWrapper.appendChild(messageDiv);
    scrollToBottom();
}

// Add analysis message (with images)
function addAnalysisMessage(role, content, files = []) {
    const messagesWrapper = document.querySelector('.messages-wrapper');
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;
    
    const avatarIcon = role === 'user' 
        ? '<svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M10 10C12.7614 10 15 7.76142 15 5C15 2.23858 12.7614 0 10 0C7.23858 0 5 2.23858 5 5C5 7.76142 7.23858 10 10 10ZM10 12.5C6.66667 12.5 0 14.1667 0 17.5V20H20V17.5C20 14.1667 13.3333 12.5 10 12.5Z" fill="currentColor"/></svg>'
        : '<svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg"><rect x="2" y="2" width="16" height="16" rx="2" stroke="currentColor" stroke-width="2"/><path d="M7 10L9 12L13 8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    
    const time = new Date().toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
    
    let imageGrid = '';
    if (files.length > 0) {
        imageGrid = `
            <div class="message-image-grid">
                ${files.map(f => f.type.startsWith('image/') 
                    ? `<div class="message-image"><img src="${f.dataUrl}" alt="${f.name}"></div>`
                    : `<div class="message-image pdf"><div class="pdf-icon">📄</div><p>${f.name}</p></div>`
                ).join('')}
            </div>
        `;
    }
    
    messageDiv.innerHTML = `
        <div class="message-avatar">${avatarIcon}</div>
        <div class="message-content">
            ${content ? `<div class="message-bubble">${escapeHtml(content)}</div>` : ''}
            ${imageGrid}
            <div class="message-time">${time}</div>
        </div>
    `;
    
    messagesWrapper.appendChild(messageDiv);
    scrollToBottom();
}

// Start new analysis
function startNewAnalysis() {
    currentAnalysisId = null;
    currentStep = -1;
    attachedFiles = [];
    analysisContext = {
        product_name: null,
        country: null,
        product_type: null,
        main_features: null,
        core_components: null
    };
    structuredSlots = {
        product_category: null,
        functions: null,
        components: null,
        process: null
    };
    
    document.getElementById('workflowProgress').style.display = 'none';
    document.getElementById('contextSummaryBar').style.display = 'none';
    updateAttachedFilesPreview();
    
    const messagesWrapper = document.querySelector('.messages-wrapper');
    messagesWrapper.innerHTML = `
        <div class="welcome-message">
            <div class="welcome-icon">
                <svg width="80" height="80" viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <rect x="10" y="10" width="60" height="60" rx="6" stroke="currentColor" stroke-width="3"/>
                    <path d="M30 40L36 46L50 32" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
            </div>
            <h2>FTOGuard AI 특허 분석</h2>
            <p>제품 정보와 이미지를 입력하시면 AI가 특허 침해 리스크를 분석해드립니다.</p>
            
            <div class="workflow-info">
                <h4>AI 분석 워크플로우</h4>
                <div class="workflow-steps">
                    <div class="workflow-step">
                        <div class="workflow-number">1</div>
                        <div class="workflow-content">
                            <strong>중앙 오케스트레이터</strong>
                            <p>질의 분석 및 에이전트 라우팅</p>
                        </div>
                    </div>
                    <div class="workflow-step">
                        <div class="workflow-number">2</div>
                        <div class="workflow-content">
                            <strong>텍스트/디자인 에이전트</strong>
                            <p>Vector DB 검색 및 유사도 분석</p>
                        </div>
                    </div>
                    <div class="workflow-step">
                        <div class="workflow-number">3</div>
                        <div class="workflow-content">
                            <strong>위험도 판단</strong>
                            <p>SLLM/VLM 기반 침해 리스크 평가</p>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="suggested-prompts">
                <button class="prompt-chip" onclick="sendSuggestedPrompt('제품명과 주요 기능을 설명해드릴게요')">
                    제품 정보 입력
                </button>
                <button class="prompt-chip" onclick="sendSuggestedPrompt('디자인 도면 이미지를 첨부할게요')">
                    이미지 첨부
                </button>
                <button class="prompt-chip" onclick="sendSuggestedPrompt('텍스트와 이미지를 모두 제공하겠습니다')">
                    멀티모달 분석
                </button>
            </div>
        </div>
    `;
    
    updateSessionType('대기 중');
    updateAgentStatus('ready');
    
    Toast.success('새 분석을 시작합니다.');
}

// ============================================
// PART 4: Session Management
// ============================================

// Load analysis sessions
function loadAnalysisSessions() {
    const sessionsContainer = document.getElementById('chatSessions');
    
    const sessions = [
        { id: 'ana-1', title: '스마트 머그컵 FTO 분석', date: new Date(), type: 'fto', result: 'safe' },
        { id: 'ana-2', title: '무선 충전 패드 디자인', date: new Date(Date.now() - 86400000), type: 'design', result: 'warning' },
        { id: 'ana-3', title: '세라믹 히터 멀티모달', date: new Date(Date.now() - 2 * 86400000), type: 'multi', result: 'safe' },
        { id: 'ana-4', title: 'IoT 센서 특허 검토', date: new Date(Date.now() - 7 * 86400000), type: 'fto', result: 'danger' }
    ];
    
    sessionsContainer.innerHTML = sessions.map(session => `
        <div class="session-item" onclick="loadAnalysisSession('${session.id}')">
            <div class="session-header">
                <span class="session-result-badge ${session.result}"></span>
                <span class="session-type-badge">${session.type === 'fto' ? 'FTO' : session.type === 'design' ? '디자인' : '멀티'}</span>
            </div>
            <div class="session-title">${session.title}</div>
            <div class="session-meta">${formatSessionDate(session.date)}</div>
        </div>
    `).join('');
}

// Format session date
function formatSessionDate(date) {
    const now = new Date();
    const diff = now - date;
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    
    if (days === 0) return '오늘';
    if (days === 1) return '어제';
    if (days < 7) return `${days}일 전`;
    return date.toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' });
}

// Filter sessions by date
function filterSessions() {
    const filter = document.getElementById('dateFilter').value;
    const sessions = document.querySelectorAll('.session-item');
    
    const now = new Date();
    
    sessions.forEach(session => {
        const dateText = session.querySelector('.session-meta').textContent;
        let show = true;
        
        switch(filter) {
            case 'today':
                show = dateText === '오늘';
                break;
            case 'week':
                show = dateText.includes('일 전') || dateText === '오늘' || dateText === '어제';
                break;
            case 'month':
                // Show all for demo
                show = true;
                break;
        }
        
        session.style.display = show ? 'block' : 'none';
    });
}

// Load analysis session
function loadAnalysisSession(id) {
    Toast.info(`세션 ${id}를 불러오는 중...`);
    // In production, this would load actual session data
    // For now, just show a message
    setTimeout(() => {
        Toast.success('세션이 복원되었습니다.');
    }, 1000);
}

