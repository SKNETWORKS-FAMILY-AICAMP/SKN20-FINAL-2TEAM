// Chat Interface JavaScript

let currentSessionId = null;
let chatContext = {
    product: null,
    country: null,
    type: null
};

// Initialize chat
function initializeChat() {
    loadChatSessions();
    setupEventListeners();
    
    // Auto-resize textarea
    const messageInput = document.getElementById('messageInput');
    messageInput.addEventListener('input', autoResizeTextarea);
}

// Setup event listeners
function setupEventListeners() {
    const messageInput = document.getElementById('messageInput');
    const sendBtn = document.getElementById('sendBtn');
    const newChatBtn = document.getElementById('newChatBtn');
    
    // Input validation
    messageInput.addEventListener('input', () => {
        sendBtn.disabled = !messageInput.value.trim();
    });
    
    // Send message on button click
    sendBtn.addEventListener('click', sendMessage);
    
    // Send message on Enter (Shift+Enter for new line)
    messageInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (!sendBtn.disabled) {
                sendMessage();
            }
        }
    });
    
    // New chat
    newChatBtn?.addEventListener('click', startNewChat);
}

// Auto-resize textarea
function autoResizeTextarea(e) {
    const textarea = e.target;
    textarea.style.height = 'auto';
    textarea.style.height = textarea.scrollHeight + 'px';
}

// Load chat sessions from localStorage
function loadChatSessions() {
    const sessionsContainer = document.getElementById('chatSessions');
    
    // Mock sessions for demonstration
    const sessions = [
        {
            id: 'session-1',
            title: '스마트 온도 조절 머그컵',
            date: '오늘',
            type: 'fto'
        },
        {
            id: 'session-2',
            title: '무선 충전 패드',
            date: '어제',
            type: 'design'
        },
        {
            id: 'session-3',
            title: '세라믹 히터 분석',
            date: '2024.02.07',
            type: 'fto'
        }
    ];
    
    sessionsContainer.innerHTML = sessions.map(session => `
        <div class="session-item ${session.id === currentSessionId ? 'active' : ''}" 
             onclick="loadSession('${session.id}')">
            <div class="session-title">${session.title}</div>
            <div class="session-meta">${session.date} · ${session.type === 'fto' ? 'FTO' : '디자인'}</div>
        </div>
    `).join('');
}

// Load specific session
function loadSession(sessionId) {
    currentSessionId = sessionId;
    loadChatSessions(); // Refresh to show active state
    
    // In production, load messages from API
    Toast.info('세션을 불러오는 중...');
}

// Start new chat
function startNewChat() {
    currentSessionId = null;
    
    const messagesWrapper = document.querySelector('.messages-wrapper');
    messagesWrapper.innerHTML = `
        <div class="welcome-message">
            <div class="welcome-icon">
                <svg width="64" height="64" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <rect x="8" y="8" width="48" height="48" rx="4" stroke="currentColor" stroke-width="3"/>
                    <path d="M24 32L30 38L40 28" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
            </div>
            <h2>FTOGuard AI 분석 시작</h2>
            <p>제품 정보를 입력하시면 특허 침해 리스크를 분석해드립니다.</p>
            
            <div class="suggested-prompts">
                <button class="prompt-chip" onclick="sendSuggestedPrompt('제품명과 주요 기능을 알려주세요')">
                    제품 정보 입력하기
                </button>
                <button class="prompt-chip" onclick="sendSuggestedPrompt('이미 제품 설명이 있습니다. 분석을 시작해주세요.')">
                    즉시 분석 시작
                </button>
            </div>
        </div>
    `;
    
    // Reset context
    chatContext = { product: null, country: null, type: null };
    updateContextBar();
    
    Toast.success('새 채팅을 시작합니다.');
}

// Send suggested prompt
function sendSuggestedPrompt(prompt) {
    const messageInput = document.getElementById('messageInput');
    messageInput.value = prompt;
    messageInput.dispatchEvent(new Event('input'));
    sendMessage();
}

// Send message
async function sendMessage() {
    const messageInput = document.getElementById('messageInput');
    const message = messageInput.value.trim();
    
    if (!message) return;
    
    // Clear input
    messageInput.value = '';
    messageInput.style.height = 'auto';
    document.getElementById('sendBtn').disabled = true;
    
    // Hide welcome message if present
    const welcomeMessage = document.querySelector('.welcome-message');
    if (welcomeMessage) {
        welcomeMessage.remove();
    }
    
    // Add user message
    addMessage('user', message);
    
    // Show typing indicator
    showTypingIndicator();
    
    try {
        // Get analysis type
        const analysisType = document.getElementById('analysisTypeSelect').value;
        
        // API call
        const response = await apiClient.post('/chat/message', {
            session_id: currentSessionId,
            message: message,
            analysis_type: analysisType,
            context: chatContext
        });
        
        // Remove typing indicator
        removeTypingIndicator();
        
        // Add assistant message
        addMessage('assistant', response.message);
        
        // Update context if provided
        if (response.context) {
            chatContext = { ...chatContext, ...response.context };
            updateContextBar();
        }
        
        // Update session ID if new
        if (response.session_id) {
            currentSessionId = response.session_id;
        }
        
        // If analysis complete, show results link
        if (response.analysis_complete) {
            addAnalysisCompleteCard(response.analysis_id);
        }
        
    } catch (error) {
        removeTypingIndicator();
        
        // Mock response for demonstration
        setTimeout(() => {
            const mockResponse = generateMockResponse(message);
            addMessage('assistant', mockResponse);
        }, 1000);
    }
}

// Generate mock response
function generateMockResponse(userMessage) {
    const lowerMessage = userMessage.toLowerCase();
    
    if (lowerMessage.includes('제품명') || lowerMessage.includes('제품 정보')) {
        chatContext.product = '스마트 온도 조절 머그컵';
        updateContextBar();
        return '제품명이 "스마트 온도 조절 머그컵"인 것을 확인했습니다. 출시 예정 국가와 제품의 주요 기능을 알려주시겠어요?';
    }
    
    if (lowerMessage.includes('한국') || lowerMessage.includes('대한민국')) {
        chatContext.country = '대한민국';
        updateContextBar();
        return '한국 시장을 타겟으로 하시는군요. 제품의 핵심 기능이나 구성 요소에 대해 좀 더 자세히 설명해주시겠어요?';
    }
    
    if (lowerMessage.includes('배터리') || lowerMessage.includes('온도')) {
        chatContext.type = '가전제품';
        updateContextBar();
        return '네, 충분한 정보를 받았습니다. 지금부터 특허 데이터베이스를 검색하고 리스크를 분석하겠습니다.\n\n분석이 완료되면 상세한 결과를 보여드리겠습니다.';
    }
    
    return '질문을 잘 이해했습니다. 추가로 어떤 정보가 필요하신가요?';
}

// Add message to chat
function addMessage(role, content) {
    const messagesWrapper = document.querySelector('.messages-wrapper');
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;
    
    const avatarIcon = role === 'user' 
        ? '<svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M10 10C12.7614 10 15 7.76142 15 5C15 2.23858 12.7614 0 10 0C7.23858 0 5 2.23858 5 5C5 7.76142 7.23858 10 10 10ZM10 12.5C6.66667 12.5 0 14.1667 0 17.5V20H20V17.5C20 14.1667 13.3333 12.5 10 12.5Z" fill="currentColor"/></svg>'
        : '<svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg"><rect x="2" y="2" width="16" height="16" rx="2" stroke="currentColor" stroke-width="2"/><path d="M7 10L9 12L13 8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    
    const time = new Date().toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
    
    messageDiv.innerHTML = `
        <div class="message-avatar">${avatarIcon}</div>
        <div class="message-content">
            <div class="message-bubble">${escapeHtml(content)}</div>
            <div class="message-time">${time}</div>
        </div>
    `;
    
    messagesWrapper.appendChild(messageDiv);
    scrollToBottom();
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

// Add analysis complete card
function addAnalysisCompleteCard(analysisId) {
    const messagesWrapper = document.querySelector('.messages-wrapper');
    const cardDiv = document.createElement('div');
    cardDiv.className = 'message assistant';
    
    cardDiv.innerHTML = `
        <div class="message-avatar">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
                <rect x="2" y="2" width="16" height="16" rx="2" stroke="currentColor" stroke-width="2"/>
                <path d="M7 10L9 12L13 8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        </div>
        <div class="message-content">
            <div class="analysis-step-card">
                <div class="step-header">
                    <div class="step-icon">
                        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/>
                            <path d="M8 12L11 15L16 9" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                        </svg>
                    </div>
                    <h4 class="step-title">분석 완료!</h4>
                </div>
                <div class="step-content">
                    <p>특허 침해 리스크 분석이 완료되었습니다. 상세한 결과를 확인하시겠습니까?</p>
                    <button class="btn-primary-large" style="margin-top: 1rem;" onclick="window.location.href='results.html?id=${analysisId}'">
                        결과 보기
                    </button>
                </div>
            </div>
        </div>
    `;
    
    messagesWrapper.appendChild(cardDiv);
    scrollToBottom();
}

// Update context bar
function updateContextBar() {
    document.getElementById('contextProduct').textContent = chatContext.product || '-';
    document.getElementById('contextCountry').textContent = chatContext.country || '-';
    document.getElementById('contextType').textContent = chatContext.type || '-';
}

// Scroll to bottom
function scrollToBottom() {
    const container = document.getElementById('messagesContainer');
    container.scrollTop = container.scrollHeight;
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

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initializeChat();
});
