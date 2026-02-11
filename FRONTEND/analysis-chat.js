// Analysis Chat JavaScript - Workflow Based

let currentAnalysisId = null;
let attachedFiles = [];
let analysisContext = {
    product_name: null,
    main_features: null,
    core_components: null,
    target_country: null,
    product_type: null
};

// Workflow steps
const WORKFLOW_STEPS = ['extract', 'search', 'analyze', 'verify', 'complete'];
let currentStep = -1;

// Initialize analysis chat
function initializeAnalysisChat() {
    loadAnalysisSessions();
    setupAnalysisEventListeners();
    updateSessionType('대기 중');
    updateAgentStatus('ready');
}

// Setup event listeners
function setupAnalysisEventListeners() {
    const messageInput = document.getElementById('messageInput');
    const sendBtn = document.getElementById('sendBtn');
    const attachBtn = document.getElementById('attachBtn');
    const fileInput = document.getElementById('fileInput');
    
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
        fileInput.click();
    });
    
    // File selection
    fileInput.addEventListener('change', handleFileSelection);
}

// Handle file selection
function handleFileSelection(e) {
    const files = Array.from(e.target.files);
    
    files.forEach(file => {
        if (file.type.startsWith('image/') || file.type === 'application/pdf') {
            const reader = new FileReader();
            reader.onload = (event) => {
                attachedFiles.push({
                    file: file,
                    name: file.name,
                    type: file.type,
                    dataUrl: event.target.result
                });
                updateAttachedFilesPreview();
                document.getElementById('sendBtn').disabled = false;
            };
            reader.readAsDataURL(file);
        } else {
            Toast.error('이미지 또는 PDF 파일만 첨부 가능합니다.');
        }
    });
    
    // Reset file input
    e.target.value = '';
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
                : `<div style="display: flex; align-items: center; justify-content: center; height: 100%; background: var(--bg-tertiary);">
                    <svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <path d="M6 4H20L26 10V28H6V4Z" stroke="currentColor" stroke-width="2"/>
                    </svg>
                   </div>`
            }
            <button class="file-remove" onclick="removeAttachedFile(${index})">×</button>
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
    
    // Clear attached files
    const sentFiles = [...attachedFiles];
    attachedFiles = [];
    updateAttachedFilesPreview();
    
    // Show typing indicator
    showTypingIndicator();
    
    // Determine analysis type
    const hasImages = sentFiles.length > 0;
    const hasText = message.length > 0;
    
    try {
        // Step 1: 중앙 오케스트레이터가 질의 분석
        updateSessionType(hasImages && hasText ? '멀티모달 분석' : hasImages ? '디자인 분석' : 'FTO 분석');
        updateAgentStatus('processing');
        
        // Show orchestrator activity
        setTimeout(() => {
            removeTypingIndicator();
            addAgentActivityCard('orchestrator', '중앙 오케스트레이터', '질의 분석 중...', 20);
        }, 800);
        
        // Simulate API call
        await simulateWorkflow(message, sentFiles, hasImages, hasText);
        
    } catch (error) {
        removeTypingIndicator();
        Toast.error('분석 중 오류가 발생했습니다.');
        updateAgentStatus('ready');
    }
}

// Simulate workflow (replace with actual API calls)
async function simulateWorkflow(message, files, hasImages, hasText) {
    // Show workflow progress
    document.getElementById('workflowProgress').style.display = 'block';
    
    // Step 1: Extract keywords
    await updateWorkflowStep('extract');
    await sleep(1500);
    updateAgentProgress('orchestrator', 40, '키워드 추출 완료');
    
    // Check if information is sufficient
    const needsMoreInfo = checkInformationSufficiency(message);
    
    if (needsMoreInfo) {
        removeTypingIndicator();
        await updateWorkflowStep('extract', false); // Reset
        addInfoRequestMessage(needsMoreInfo);
        updateAgentStatus('ready');
        return;
    }
    
    // Step 2: Vector search
    await updateWorkflowStep('search');
    
    if (hasText) {
        addAgentActivityCard('text-agent', '텍스트 에이전트', 'Vector DB 검색 중...', 30);
    }
    if (hasImages) {
        addAgentActivityCard('design-agent', '디자인 에이전트', 'CLIP 임베딩 & 검색 중...', 30);
    }
    
    await sleep(2000);
    updateAgentProgress('text-agent', 60, 'Top-K 특허 검색 완료');
    
    // Step 3: Analyze with SLLM/VLM
    await updateWorkflowStep('analyze');
    updateAgentProgress('text-agent', 80, '위험도 분석 중...');
    
    await sleep(2500);
    
    // Step 4: Verify results
    await updateWorkflowStep('verify');
    updateAgentProgress('text-agent', 95, '결과 검증 중...');
    
    await sleep(1500);
    
    // Step 5: Complete
    await updateWorkflowStep('complete');
    updateAgentProgress('orchestrator', 100, '분석 완료');
    
    removeTypingIndicator();
    
    // Generate final response
    const riskLevel = Math.random() > 0.7 ? 'warning' : Math.random() > 0.4 ? 'safe' : 'danger';
    addFinalAnalysisResult(riskLevel);
    
    updateAgentStatus('complete');
}

// Check information sufficiency
function checkInformationSufficiency(message) {
    const lowerMessage = message.toLowerCase();
    
    // Extract context from message
    if (lowerMessage.includes('제품') || lowerMessage.includes('머그컵') || lowerMessage.includes('스마트')) {
        analysisContext.product_name = '제품명 확인됨';
    }
    
    // Check what's missing
    const missing = [];
    if (!analysisContext.main_features && !lowerMessage.includes('기능')) {
        missing.push('제품의 주요 기능');
    }
    if (!analysisContext.core_components && !lowerMessage.includes('구성') && !lowerMessage.includes('성분')) {
        missing.push('핵심 구성요소 또는 성분');
    }
    if (!analysisContext.target_country && !lowerMessage.includes('한국') && !lowerMessage.includes('국가')) {
        missing.push('출시 예정 국가');
    }
    
    // Randomly decide if more info is needed (for demo)
    if (missing.length > 0 && Math.random() > 0.6) {
        return missing;
    }
    
    return null;
}

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
    
    // Check if card already exists
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
                    <h4>추가 정보 필요</h4>
                </div>
                <ul class="info-request-list">
                    ${missingInfo.map(info => `<li>${info}</li>`).join('')}
                </ul>
            </div>
        </div>
    `;
    
    messagesWrapper.appendChild(messageDiv);
    scrollToBottom();
}

// Add final analysis result
function addFinalAnalysisResult(riskLevel) {
    const messagesWrapper = document.querySelector('.messages-wrapper');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant';
    
    const riskData = {
        safe: {
            title: '비침해 (안전)',
            description: '분석 결과, 검색된 특허들과의 유사성이 낮아 침해 위험이 낮은 것으로 판단됩니다.',
            icon: '<path d="M8 12L11 15L16 9" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/>'
        },
        warning: {
            title: '전문가 검토 필요',
            description: '일부 특허와 유사한 요소가 발견되었습니다. 변리사의 상세 검토를 권장합니다.',
            icon: '<path d="M12 8V12M12 16H12.01" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M10.29 3.86L1.82 18A2 2 0 003.53 21H20.47A2 2 0 0022.18 18L13.71 3.86A2 2 0 0010.29 3.86Z" stroke="currentColor" stroke-width="2"/>'
        },
        danger: {
            title: '침해 위험 (고위험)',
            description: '특허 청구항과 직접적으로 일치하는 요소가 발견되었습니다. 즉시 법률 자문을 받으시기 바랍니다.',
            icon: '<circle cx="12" cy="12" r="3" fill="currentColor"/><circle cx="12" cy="12" r="8" stroke="currentColor" stroke-width="2"/>'
        }
    };
    
    const risk = riskData[riskLevel];
    
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
                        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                            ${risk.icon}
                        </svg>
                    </div>
                    <h3 class="risk-title">${risk.title}</h3>
                </div>
                <p class="risk-description">${risk.description}</p>
                <div class="risk-action">
                    <button class="btn-primary" onclick="window.location.href='results.html?id=DEMO-${Date.now()}'">
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
                    : `<div class="message-image"><div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 150px; background: var(--bg-tertiary);">
                        <svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <path d="M6 4H20L26 10V28H6V4Z" stroke="currentColor" stroke-width="2"/>
                        </svg>
                        <p style="margin-top: 8px; font-size: 0.75rem;">${f.name}</p>
                      </div></div>`
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
        complete: '완료'
    };
    
    statusElement.textContent = statusText[status] || status;
}

// Start new analysis
function startNewAnalysis() {
    currentAnalysisId = null;
    currentStep = -1;
    attachedFiles = [];
    analysisContext = {};
    
    document.getElementById('workflowProgress').style.display = 'none';
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
                <h4>분석 프로세스</h4>
                <div class="workflow-steps">
                    <div class="workflow-step">
                        <div class="workflow-number">1</div>
                        <div class="workflow-content">
                            <strong>정보 수집</strong>
                            <p>제품 설명 및 이미지 입력</p>
                        </div>
                    </div>
                    <div class="workflow-step">
                        <div class="workflow-number">2</div>
                        <div class="workflow-content">
                            <strong>AI 분석</strong>
                            <p>텍스트/디자인 에이전트 실행</p>
                        </div>
                    </div>
                    <div class="workflow-step">
                        <div class="workflow-number">3</div>
                        <div class="workflow-content">
                            <strong>결과 생성</strong>
                            <p>위험도 판단 및 근거 제시</p>
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
                    텍스트 + 이미지
                </button>
            </div>
        </div>
    `;
    
    updateSessionType('대기 중');
    updateAgentStatus('ready');
    
    Toast.success('새 분석을 시작합니다.');
}

// Load analysis sessions
function loadAnalysisSessions() {
    const sessionsContainer = document.getElementById('chatSessions');
    
    const sessions = [
        { id: 'ana-1', title: '스마트 머그컵 FTO 분석', date: '오늘', type: 'fto' },
        { id: 'ana-2', title: '무선 충전 패드 디자인', date: '어제', type: 'design' },
        { id: 'ana-3', title: '세라믹 히터 멀티모달', date: '2024.02.08', type: 'multi' }
    ];
    
    sessionsContainer.innerHTML = sessions.map(session => `
        <div class="session-item" onclick="loadAnalysisSession('${session.id}')">
            <div class="session-title">${session.title}</div>
            <div class="session-meta">${session.date}</div>
        </div>
    `).join('');
}

// Utility functions
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function sendSuggestedPrompt(text) {
    document.getElementById('messageInput').value = text;
    document.getElementById('sendBtn').disabled = false;
}

function loadAnalysisSession(id) {
    Toast.info('세션을 불러오는 중...');
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initializeAnalysisChat();
});
