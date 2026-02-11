// The Verdict - Result Page JavaScript
// "The Confidence Engine" - Decision-First UX

// Mock result data
const mockResultData = {
    verdict: 'safe', // 'safe', 'warning', 'danger'
    headline: '출시 가능합니다',
    reason: '검색된 4,247개 특허 중 침해 가능성이 있는 청구항이 발견되지 않았습니다.',
    confidence: 94,
    productName: '스마트 온도 조절 머그컵',
    analysisDate: '2024년 2월 10일 14:32',
    patentCount: '4,247건',
    patents: [
        {
            number: 'KR10-2021-0123456',
            title: '스마트 보온 용기 및 제어 방법',
            description: '배터리 기반 자동 온도 유지 기능을 가진 용기 및 그 제어 방법에 관한 특허',
            similarity: 'low',
            applicant: '삼성전자',
            filingDate: '2021.10.15'
        },
        {
            number: 'KR10-2020-0098765',
            title: '무선 충전 기능을 갖는 스마트 컵',
            description: '무선 충전 패드를 이용한 스마트 컵 충전 시스템',
            similarity: 'low',
            applicant: 'LG전자',
            filingDate: '2020.08.22'
        },
        {
            number: 'KR10-2022-0045678',
            title: '세라믹 히팅 소자를 이용한 보온 기술',
            description: '세라믹 본체 내장형 가열 소자를 활용한 온도 유지 기술',
            similarity: 'low',
            applicant: '쿠쿠전자',
            filingDate: '2022.03.10'
        }
    ],
    mappings: [
        { product: '세라믹 본체', patent: '플라스틱 외관', mapped: false, risk: 'low' },
        { product: '내장 가열 소자', patent: '전기 히터', mapped: true, risk: 'low' },
        { product: '온도 센서', patent: '온도 감지 장치', mapped: true, risk: 'low' },
        { product: '리튬 배터리', patent: '배터리 팩', mapped: true, risk: 'low' },
        { product: '무선 충전 호환', patent: '유선 충전만 지원', mapped: false, risk: 'low' }
    ],
    ftoSuggestions: [
        {
            title: '만료 특허 활용',
            description: '2015년 만료된 KR10-2005-0012345 특허의 기술을 자유롭게 활용 가능합니다.',
            benefit: '라이선스 비용 없음'
        },
        {
            title: '대체 재료 사용',
            description: '세라믹 대신 스테인리스 본체를 사용하여 기존 특허 청구범위를 회피할 수 있습니다.',
            benefit: '특허 침해 위험 감소'
        },
        {
            title: '다른 온도 제어 방식',
            description: 'PID 제어 대신 간단한 ON/OFF 제어 방식으로 차별화 가능합니다.',
            benefit: '제조 원가 절감'
        },
        {
            title: '국외 특허 활용',
            description: '한국 미등록 해외 특허 기술을 국내에서 자유롭게 실시 가능합니다.',
            benefit: '기술 차별화 가능'
        }
    ]
};

// Alternative data sets for different verdicts
const verdictData = {
    safe: {
        headline: '출시 가능합니다',
        reason: '검색된 4,247개 특허 중 침해 가능성이 있는 청구항이 발견되지 않았습니다.',
        icon: `<circle cx="60" cy="60" r="40" stroke="white" stroke-width="6" fill="none"/>
               <path d="M40 60L52 72L80 44" stroke="white" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>`
    },
    warning: {
        headline: '전문가 검토를 권장합니다',
        reason: '일부 특허 청구항과 유사한 구성요소가 발견되었습니다. 변리사의 상세 검토가 필요합니다.',
        icon: `<path d="M60 35V60M60 75H60.05" stroke="white" stroke-width="6" stroke-linecap="round"/>
               <path d="M45 15L15 90H105L75 15A15 15 0 0045 15Z" stroke="white" stroke-width="6" fill="none"/>`
    },
    danger: {
        headline: '출시를 재검토하세요',
        reason: '특허 청구항과 직접적으로 일치하는 구성요소가 발견되었습니다. 즉시 법률 자문이 필요합니다.',
        icon: `<circle cx="60" cy="60" r="15" fill="white"/>
               <circle cx="60" cy="60" r="30" stroke="white" stroke-width="6" fill="none"/>
               <circle cx="60" cy="60" r="40" stroke="white" stroke-width="4" stroke-dasharray="6 6" fill="none"/>`
    }
};

// Initialize verdict page
function initializeVerdict() {
    // Get verdict type from URL or use mock data
    const urlParams = new URLSearchParams(window.location.search);
    const verdictType = urlParams.get('verdict') || mockResultData.verdict;
    
    // Set verdict data
    const data = verdictType === 'safe' ? mockResultData : 
                 verdictType === 'warning' ? { ...mockResultData, verdict: 'warning' } :
                 { ...mockResultData, verdict: 'danger' };
    
    renderVerdict(data);
}

// Render verdict
function renderVerdict(data) {
    const verdictInfo = verdictData[data.verdict];
    
    // Set orb state
    const orbContainer = document.getElementById('orbContainer');
    orbContainer.className = `orb-container ${data.verdict}`;
    
    // Set orb icon
    document.getElementById('orbIcon').innerHTML = verdictInfo.icon;
    
    // Set verdict message
    document.getElementById('verdictHeadline').textContent = verdictInfo.headline;
    document.getElementById('verdictReason').textContent = verdictInfo.reason;
    
    // Set confidence (animate)
    const confidence = data.confidence || 94;
    animateConfidence(confidence, data.verdict);
    
    // Set summary data
    document.getElementById('productName').textContent = data.productName;
    document.getElementById('analysisDate').textContent = data.analysisDate;
    document.getElementById('patentCount').textContent = data.patentCount;
    
    // Render patents
    renderPatents(data.patents);
    
    // Render mappings
    renderMappings(data.mappings);
    
    // Render FTO suggestions
    renderFTOSuggestions(data.ftoSuggestions);
}

// Animate confidence bar
function animateConfidence(targetValue, verdict) {
    const fill = document.getElementById('confidenceFill');
    const valueDisplay = document.getElementById('confidenceValue');
    
    // Set color based on verdict
    const colors = {
        safe: 'linear-gradient(90deg, var(--color-safe) 0%, #356B2E 100%)',
        warning: 'linear-gradient(90deg, var(--color-warning) 0%, #D4B530 100%)',
        danger: 'linear-gradient(90deg, var(--color-danger) 0%, #C14539 100%)'
    };
    
    fill.style.background = colors[verdict];
    
    // Animate from 0 to target
    let current = 0;
    const increment = targetValue / 60; // 60 frames for smooth animation
    
    const animation = setInterval(() => {
        current += increment;
        if (current >= targetValue) {
            current = targetValue;
            clearInterval(animation);
        }
        
        fill.style.width = current + '%';
        valueDisplay.textContent = Math.round(current) + '%';
        
        // Set color
        if (verdict === 'safe') valueDisplay.style.color = 'var(--color-safe)';
        else if (verdict === 'warning') valueDisplay.style.color = 'var(--color-warning)';
        else valueDisplay.style.color = 'var(--color-danger)';
    }, 16); // ~60fps
}

// Reveal evidence section (Progressive Disclosure)
function revealEvidence() {
    const section = document.getElementById('evidenceSection');
    section.style.display = 'block';
    
    // Smooth scroll to evidence
    setTimeout(() => {
        section.scrollIntoView({ 
            behavior: 'smooth',
            block: 'start'
        });
    }, 100);
    
    // Hide reveal button
    document.getElementById('revealBtn').style.display = 'none';
}

// Render patents list
function renderPatents(patents) {
    const container = document.getElementById('patentsList');
    
    container.innerHTML = patents.map(patent => `
        <div class="patent-item">
            <div class="patent-header">
                <span class="patent-number">${patent.number}</span>
                <span class="similarity-badge ${patent.similarity}">
                    유사도: ${getSimilarityText(patent.similarity)}
                </span>
            </div>
            <h3 class="patent-title">${patent.title}</h3>
            <p class="patent-description">${patent.description}</p>
            <div class="patent-meta">
                <span>출원인: ${patent.applicant}</span>
                <span>출원일: ${patent.filingDate}</span>
            </div>
        </div>
    `).join('');
}

function getSimilarityText(level) {
    return {
        low: '낮음',
        medium: '보통',
        high: '높음'
    }[level] || '알 수 없음';
}

// Render component mappings
function renderMappings(mappings) {
    const tbody = document.getElementById('mappingTableBody');
    
    tbody.innerHTML = mappings.map(mapping => `
        <tr>
            <td><strong>${mapping.product}</strong></td>
            <td>${mapping.patent}</td>
            <td>
                <span class="mapping-status ${mapping.mapped ? 'mapped' : 'not-mapped'}">
                    ${mapping.mapped ? '✓ 매핑됨' : '✗ 미매핑'}
                </span>
            </td>
            <td>
                <span class="risk-badge ${mapping.risk}">
                    ${getRiskText(mapping.risk)}
                </span>
            </td>
        </tr>
    `).join('');
}

function getRiskText(level) {
    return {
        low: '낮음',
        medium: '보통',
        high: '높음'
    }[level] || '알 수 없음';
}

// Render FTO suggestions
function renderFTOSuggestions(suggestions) {
    const container = document.getElementById('ftoSuggestions');
    
    container.innerHTML = suggestions.map(suggestion => `
        <div class="fto-card">
            <div class="fto-icon">
                <svg width="48" height="48" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M24 8L28 20L40 24L28 28L24 40L20 28L8 24L20 20L24 8Z" stroke="currentColor" stroke-width="3" stroke-linejoin="round"/>
                </svg>
            </div>
            <h3 class="fto-title">${suggestion.title}</h3>
            <p class="fto-description">${suggestion.description}</p>
            <div class="fto-benefit">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M5 8L7 10L11 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
                ${suggestion.benefit}
            </div>
        </div>
    `).join('');
}

// Download PDF
function downloadPDF() {
    Toast.info('PDF 다운로드 기능은 준비 중입니다.');
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    initializeVerdict();
});

// Export functions
window.revealEvidence = revealEvidence;
window.downloadPDF = downloadPDF;
