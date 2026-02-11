// Analysis Complete - Routing Logic Addition
// 이 코드를 기존 analysis-complete.js의 addFinalAnalysisResult 함수에 추가

// Modified addFinalAnalysisResult function with routing
function addFinalAnalysisResult(riskLevel, analysisType = 'fto') {
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
    
    // 🔥 Determine result page URL based on analysis type
    const analysisId = currentAnalysisId || 'DEMO-' + Date.now();
    let resultPageUrl;
    
    if (analysisType === 'fto') {
        resultPageUrl = `results.html?id=${analysisId}&type=fto`;
    } else if (analysisType === 'design') {
        resultPageUrl = `design-results.html?id=${analysisId}&type=design`;
    } else if (analysisType === 'multimodal') {
        resultPageUrl = `combined-results.html?id=${analysisId}&type=multimodal`;
    } else {
        // Default fallback
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

// Modified executeWorkflow function - update the final result call
async function executeWorkflow(message, files, analysisType) {
    // ... existing code ...
    
    // Step 6: Complete
    await updateWorkflowStep('complete');
    updateAgentProgress('orchestrator', 100, '분석 완료');
    
    removeTypingIndicator();
    
    // Generate final result with analysis type
    const riskLevel = Math.random() > 0.7 ? 'warning' : Math.random() > 0.4 ? 'safe' : 'danger';
    
    // 🔥 Pass analysisType to addFinalAnalysisResult
    addFinalAnalysisResult(riskLevel, analysisType);
    
    updateAgentStatus('complete');
}

// API Response Handler (for production)
async function handleAnalysisComplete(response) {
    const { 
        analysis_id, 
        analysis_type, 
        has_text, 
        has_image,
        risk_level 
    } = response;
    
    // Store analysis ID
    currentAnalysisId = analysis_id;
    
    // Determine analysis type if not explicitly provided
    let finalAnalysisType = analysis_type;
    
    if (!finalAnalysisType) {
        if (has_text && has_image) {
            finalAnalysisType = 'multimodal';
        } else if (has_image) {
            finalAnalysisType = 'design';
        } else {
            finalAnalysisType = 'fto';
        }
    }
    
    // Show final result with appropriate routing
    addFinalAnalysisResult(risk_level || 'safe', finalAnalysisType);
    
    Toast.success('분석이 완료되었습니다!');
}
