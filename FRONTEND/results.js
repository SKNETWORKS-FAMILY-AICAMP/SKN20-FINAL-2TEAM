// Results Page JavaScript

// Mock data for demonstration
const mockAnalysisData = {
    analysis_id: 'ANL-2024-001',
    type: '특허 FTO 분석',
    date: '2024년 2월 9일',
    product_title: '스마트 온도 조절 머그컵',
    risk_level: 'safe', // safe, warning, danger
    risk_description: '분석 결과, 검색된 특허들과 유사성이 낮아 침해 위험이 낮은 것으로 판단됩니다.',
    patents: [
        {
            number: 'KR10-2021-0123456',
            title: '스마트 보온 용기 및 제어 방법',
            description: '배터리 기반 자동 온도 유지 기능을 가진 용기 및 그 제어 방법에 관한 특허',
            similarity: 'medium',
            applicant: '삼성전자',
            filing_date: '2021.10.15'
        },
        {
            number: 'KR10-2020-0098765',
            title: '무선 충전 기능을 갖는 스마트 컵',
            description: '무선 충전 패드를 이용한 스마트 컵 충전 시스템',
            similarity: 'low',
            applicant: 'LG전자',
            filing_date: '2020.08.22'
        },
        {
            number: 'KR10-2022-0045678',
            title: '세라믹 히팅 소자를 이용한 보온 기술',
            description: '세라믹 본체 내장형 가열 소자를 활용한 온도 유지 기술',
            similarity: 'low',
            applicant: '쿠쿠전자',
            filing_date: '2022.03.10'
        }
    ],
    mappings: [
        {
            product_component: '세라믹 본체',
            patent_component: '플라스틱 외관',
            mapped: false,
            risk: 'low'
        },
        {
            product_component: '내장 가열 소자',
            patent_component: '전기 히터',
            mapped: true,
            risk: 'medium'
        },
        {
            product_component: '온도 센서',
            patent_component: '온도 감지 장치',
            mapped: true,
            risk: 'low'
        },
        {
            product_component: '리튬 배터리',
            patent_component: '배터리 팩',
            mapped: true,
            risk: 'low'
        },
        {
            product_component: '무선 충전 호환',
            patent_component: '유선 충전만 지원',
            mapped: false,
            risk: 'low'
        }
    ],
    alternatives: [
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

// Get URL parameters
function getAnalysisId() {
    const params = new URLSearchParams(window.location.search);
    return params.get('id');
}

// Load analysis data
async function loadAnalysisData() {
    const analysisId = getAnalysisId();
    
    if (!analysisId) {
        Toast.warning('분석 ID가 없습니다. 샘플 데이터를 표시합니다.');
    }
    
    try {
        // In production, this would be an API call
        // const data = await apiClient.get(`/analysis/${analysisId}`);
        
        // For now, use mock data
        const data = mockAnalysisData;
        
        renderAnalysisData(data);
        
    } catch (error) {
        console.error('Failed to load analysis:', error);
        Toast.error('분석 결과를 불러오는데 실패했습니다.');
        
        // Fallback to mock data
        renderAnalysisData(mockAnalysisData);
    }
}

// Render analysis data
function renderAnalysisData(data) {
    // Meta information
    document.getElementById('analysisType').textContent = data.type;
    document.getElementById('analysisDate').textContent = data.date;
    document.getElementById('analysisTitle').textContent = `${data.product_title} 분석 결과`;
    
    // Risk summary
    const riskIcon = document.getElementById('riskIcon');
    const riskLevel = document.getElementById('riskLevel');
    const riskDescription = document.getElementById('riskDescription');
    
    riskIcon.className = `risk-icon-large ${data.risk_level}`;
    
    const riskLevels = {
        safe: '비침해 (안전)',
        warning: '전문가 검토 필요',
        danger: '침해 위험 (고위험)'
    };
    
    riskLevel.textContent = riskLevels[data.risk_level];
    riskDescription.textContent = data.risk_description;
    
    // Patent results
    renderPatents(data.patents);
    
    // Component mappings
    renderMappings(data.mappings);
    
    // Alternatives
    renderAlternatives(data.alternatives);
}

// Render patents
function renderPatents(patents) {
    const grid = document.getElementById('patentsGrid');
    
    grid.innerHTML = patents.map(patent => `
        <div class="patent-card">
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
                <span>출원일: ${patent.filing_date}</span>
            </div>
        </div>
    `).join('');
}

function getSimilarityText(similarity) {
    const texts = {
        high: '높음',
        medium: '보통',
        low: '낮음'
    };
    return texts[similarity] || '알 수 없음';
}

// Render component mappings
function renderMappings(mappings) {
    const tbody = document.getElementById('mappingTableBody');
    
    tbody.innerHTML = mappings.map(mapping => `
        <tr>
            <td>${mapping.product_component}</td>
            <td>${mapping.patent_component}</td>
            <td>
                <span class="mapping-status ${mapping.mapped ? 'mapped' : 'not-mapped'}">
                    ${mapping.mapped ? '✓ 매핑됨' : '✗ 미매핑'}
                </span>
            </td>
            <td>
                <span class="risk-indicator ${mapping.risk}">
                    ${getRiskText(mapping.risk)}
                </span>
            </td>
        </tr>
    `).join('');
}

function getRiskText(risk) {
    const texts = {
        high: '높음',
        medium: '보통',
        low: '낮음'
    };
    return texts[risk] || '알 수 없음';
}

// Render alternatives
function renderAlternatives(alternatives) {
    const grid = document.getElementById('alternativesGrid');
    
    grid.innerHTML = alternatives.map(alt => `
        <div class="alternative-card">
            <div class="alternative-icon">
                <svg width="48" height="48" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M24 8L28 20L40 24L28 28L24 40L20 28L8 24L20 20L24 8Z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
                </svg>
            </div>
            <h4 class="alternative-title">${alt.title}</h4>
            <p class="alternative-description">${alt.description}</p>
            <div class="alternative-benefit">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M5 8L7 10L11 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
                ${alt.benefit}
            </div>
        </div>
    `).join('');
}

// Download report function
function downloadReport() {
    Toast.info('PDF 다운로드 기능은 준비 중입니다.');
    
    // In production, this would generate and download a PDF
    // Example:
    // const analysisId = getAnalysisId();
    // window.location.href = `/api/analysis/${analysisId}/download`;
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadAnalysisData();
});
