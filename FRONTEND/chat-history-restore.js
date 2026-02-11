// Chat History Restore Feature
// 이 코드를 analysis-complete.js에 추가

// Load analysis session (채팅 이력 복원)
async function loadAnalysisSession(sessionId) {
    try {
        Toast.info(`세션 ${sessionId}를 불러오는 중...`);
        
        // Show loading state
        updateAgentStatus('loading');
        
        // Mock API call (실제로는 API 호출)
        const sessionData = await fetchSessionData(sessionId);
        
        if (!sessionData) {
            Toast.error('세션을 찾을 수 없습니다.');
            return;
        }
        
        // Clear current messages
        const messagesWrapper = document.getElementById('messagesWrapper');
        if (messagesWrapper) {
            messagesWrapper.innerHTML = '';
        }
        
        // Restore context
        currentAnalysisId = sessionData.id;
        analysisContext = sessionData.context || {};
        
        // Restore messages
        sessionData.messages.forEach(msg => {
            if (msg.role === 'user') {
                addAnalysisMessage('user', msg.content, msg.files || []);
            } else {
                addAnalysisMessage('assistant', msg.content);
            }
        });
        
        // Restore workflow state if exists
        if (sessionData.workflowState) {
            restoreWorkflowState(sessionData.workflowState);
        }
        
        // Update session list active state
        document.querySelectorAll('.session-card').forEach(card => {
            card.classList.remove('active');
        });
        const activeCard = document.querySelector(`[data-session-id="${sessionId}"]`);
        if (activeCard) {
            activeCard.classList.add('active');
        }
        
        Toast.success('세션이 복원되었습니다!');
        updateAgentStatus('ready');
        
        // Scroll to bottom
        scrollToBottom();
        
    } catch (error) {
        console.error('Session load error:', error);
        Toast.error('세션 복원 중 오류가 발생했습니다.');
        updateAgentStatus('error');
    }
}

// Fetch session data (Mock - 실제로는 API 호출)
async function fetchSessionData(sessionId) {
    // Simulate API delay
    await sleep(800);
    
    // Mock session data
    const mockSessions = {
        'session-001': {
            id: 'session-001',
            type: 'fto',
            productName: '스마트 머그컵 FTO 분석',
            risk: 'safe',
            context: {
                product_name: '스마트 보온 머그컵',
                product_type: '전자제품',
                country: '대한민국',
                features: ['자동 온도 유지', '무선 충전', '터치 센서'],
                components: ['세라믹 본체', '내장 가열 소자', '온도 센서', '배터리']
            },
            messages: [
                {
                    role: 'user',
                    content: '스마트 보온 머그컵을 개발 중입니다. 세라믹 본체에 내장 가열 소자를 넣고 자동으로 온도를 유지하는 기능이 있습니다.',
                    files: []
                },
                {
                    role: 'assistant',
                    content: '스마트 보온 머그컵 분석을 시작합니다. 추가 정보가 필요합니다.\n\n다음 정보를 입력해주세요:\n- 출시 예정 국가\n- 주요 기능 설명\n- 핵심 구성요소'
                },
                {
                    role: 'user',
                    content: '대한민국에서 출시 예정이며, 주요 기능은 자동 온도 유지, 무선 충전, 터치 센서 제어입니다. 핵심 구성요소는 세라믹 본체, 내장 가열 소자, NTC 온도 센서, 리튬이온 배터리입니다.'
                },
                {
                    role: 'assistant',
                    content: '정보가 충분합니다. 분석을 시작합니다...'
                }
            ],
            workflowState: {
                currentStep: 'complete',
                progress: 100
            },
            timestamp: new Date()
        },
        'session-002': {
            id: 'session-002',
            type: 'design',
            productName: '주전자 충전 패드 디자인',
            risk: 'warning',
            context: {
                product_name: '무선 충전 패드',
                product_type: '가전제품'
            },
            messages: [
                {
                    role: 'user',
                    content: '무선 충전 패드 디자인을 확인해주세요.',
                    files: [{ name: 'design-sketch.jpg', type: 'image/jpeg' }]
                },
                {
                    role: 'assistant',
                    content: '디자인 이미지 분석을 시작합니다...'
                }
            ],
            workflowState: {
                currentStep: 'analyze',
                progress: 60
            },
            timestamp: new Date(Date.now() - 86400000)
        },
        'session-003': {
            id: 'session-003',
            type: 'multimodal',
            productName: '세라믹 히터 멀티모달 분석',
            risk: 'safe',
            context: {
                product_name: '세라믹 히터',
                product_type: '난방기기'
            },
            messages: [
                {
                    role: 'user',
                    content: '세라믹 히터 제품 분석 부탁드립니다.',
                    files: [{ name: 'heater-design.png', type: 'image/png' }]
                }
            ],
            workflowState: {
                currentStep: 'extract',
                progress: 20
            },
            timestamp: new Date(Date.now() - 172800000)
        }
    };
    
    return mockSessions[sessionId] || null;
}

// Restore workflow state
function restoreWorkflowState(workflowState) {
    if (!workflowState) return;
    
    const workflowProgress = document.getElementById('workflowProgress');
    if (workflowProgress) {
        workflowProgress.style.display = 'block';
    }
    
    // Update current step
    if (workflowState.currentStep) {
        updateWorkflowStep(workflowState.currentStep);
    }
    
    // Show progress if not complete
    if (workflowState.progress < 100) {
        updateAgentStatus('processing');
    }
}

// Save current session (Auto-save)
async function saveCurrentSession() {
    if (!currentAnalysisId) {
        currentAnalysisId = 'session-' + Date.now();
    }
    
    const sessionData = {
        id: currentAnalysisId,
        type: getAnalysisType(),
        productName: analysisContext.product_name || '제품명 없음',
        risk: 'safe', // Should be determined by analysis
        context: analysisContext,
        messages: extractMessages(),
        workflowState: {
            currentStep: getCurrentWorkflowStep(),
            progress: getCurrentProgress()
        },
        timestamp: new Date()
    };
    
    // Save to localStorage (임시)
    try {
        const sessions = JSON.parse(localStorage.getItem('analysis_sessions') || '[]');
        const existingIndex = sessions.findIndex(s => s.id === currentAnalysisId);
        
        if (existingIndex >= 0) {
            sessions[existingIndex] = sessionData;
        } else {
            sessions.unshift(sessionData);
        }
        
        // Keep only last 20 sessions
        if (sessions.length > 20) {
            sessions.splice(20);
        }
        
        localStorage.setItem('analysis_sessions', JSON.stringify(sessions));
        
        // Update session list
        loadSessionList();
        
    } catch (error) {
        console.error('Session save error:', error);
    }
}

// Extract messages from DOM
function extractMessages() {
    const messages = [];
    const messageElements = document.querySelectorAll('.message');
    
    messageElements.forEach(el => {
        const isUser = el.classList.contains('user');
        const content = el.querySelector('.message-content')?.textContent?.trim() || '';
        
        messages.push({
            role: isUser ? 'user' : 'assistant',
            content: content,
            files: []
        });
    });
    
    return messages;
}

// Get current workflow step
function getCurrentWorkflowStep() {
    const steps = ['extract', 'search', 'analyze', 'judge', 'alternative', 'complete'];
    const activeStep = document.querySelector('.workflow-step.active');
    
    if (activeStep) {
        return activeStep.dataset.step || 'extract';
    }
    
    return 'extract';
}

// Get current progress
function getCurrentProgress() {
    // Calculate based on completed steps
    const steps = document.querySelectorAll('.workflow-step');
    const completedSteps = Array.from(steps).filter(s => s.classList.contains('completed')).length;
    
    return Math.round((completedSteps / steps.length) * 100);
}

// Load session list from localStorage
function loadSessionList() {
    try {
        const sessions = JSON.parse(localStorage.getItem('analysis_sessions') || '[]');
        updateSessionList(sessions);
    } catch (error) {
        console.error('Failed to load sessions:', error);
    }
}

// Auto-save on important events
function enableAutoSave() {
    // Save after each message
    const originalAddMessage = addAnalysisMessage;
    window.addAnalysisMessage = function(...args) {
        originalAddMessage.apply(this, args);
        setTimeout(() => saveCurrentSession(), 500);
    };
    
    // Save on workflow step change
    const originalUpdateStep = updateWorkflowStep;
    window.updateWorkflowStep = function(...args) {
        originalUpdateStep.apply(this, args);
        setTimeout(() => saveCurrentSession(), 500);
    };
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    loadSessionList();
    enableAutoSave();
});

// Export for global access
window.loadAnalysisSession = loadAnalysisSession;
window.saveCurrentSession = saveCurrentSession;
