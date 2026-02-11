// Combined Results Page JavaScript (Multimodal)

// Mock data combining FTO + Design analysis
const mockCombinedResults = {
    // FTO Analysis Data
    fto: {
        verdict: 'safe', // 'safe', 'warning', 'danger'
        headline: '출시 가능합니다',
        reason: '검색된 4,247개 특허 중 침해 가능성이 있는 청구항이 발견되지 않았습니다.',
        patentCount: '4,247건',
        patents: [
            {
                number: 'KR10-2021-0123456',
                title: '스마트 보온 용기 및 제어 방법',
                description: '배터리 기반 자동 온도 유지 기능',
                similarity: 'low',
                applicant: '삼성전자',
                filingDate: '2021.10.15'
            },
            {
                number: 'KR10-2020-0098765',
                title: '무선 충전 기능을 갖는 스마트 컵',
                description: '무선 충전 패드를 이용한 시스템',
                similarity: 'low',
                applicant: 'LG전자',
                filingDate: '2020.08.22'
            },
            {
                number: 'KR10-2022-0045678',
                title: '세라믹 히팅 소자를 이용한 보온 기술',
                description: '세라믹 본체 내장형 가열 소자',
                similarity: 'low',
                applicant: '쿠쿠전자',
                filingDate: '2022.03.10'
            }
        ],
        mappings: [
            { product: '세라믹 본체', patent: '플라스틱 외관', mapped: false, risk: 'low' },
            { product: '내장 가열 소자', patent: '전기 히터', mapped: true, risk: 'low' },
            { product: '온도 센서', patent: '온도 감지 장치', mapped: true, risk: 'low' },
            { product: '리튬 배터리', patent: '배터리 팩', mapped: true, risk: 'low' }
        ],
        ftoSuggestions: [
            {
                title: '만료 특허 활용',
                description: '2015년 만료된 특허 기술을 자유롭게 활용 가능',
                benefit: '라이선스 비용 없음'
            },
            {
                title: '대체 재료 사용',
                description: '세라믹 대신 스테인리스 본체로 회피 가능',
                benefit: '특허 침해 위험 감소'
            },
            {
                title: '다른 온도 제어 방식',
                description: 'PID 제어 대신 ON/OFF 제어로 차별화',
                benefit: '제조 원가 절감'
            },
            {
                title: '국외 특허 활용',
                description: '한국 미등록 해외 특허를 국내에서 자유 실시',
                benefit: '기술 차별화 가능'
            }
        ]
    },
    
    // Design Analysis Data
    design: {
        verdict: 'warning', // 'safe', 'warning', 'danger'
        totalCount: 12,
        highSimilarity: 3,
        lowSimilarity: 9,
        results: [
            {
                id: 1,
                patent_number: 'KR30-2021-0012345',
                title: '스마트폰 케이스 디자인',
                image_url: 'https://via.placeholder.com/400x300/3B82F6/FFFFFF?text=Design+1',
                similarity_score: 0.94,
                similarity_level: 'high',
                status: 'similar',
                applicant: '삼성전자',
                filing_date: '2021-03-15'
            },
            {
                id: 2,
                patent_number: 'KR30-2020-0098765',
                title: '노트북 외관 디자인',
                image_url: 'https://via.placeholder.com/400x300/10B981/FFFFFF?text=Design+2',
                similarity_score: 0.31,
                similarity_level: 'low',
                status: 'not_similar',
                applicant: 'LG전자',
                filing_date: '2020-08-22'
            },
            {
                id: 3,
                patent_number: 'KR30-2022-0045678',
                title: '태블릿 PC 디자인',
                image_url: 'https://via.placeholder.com/400x300/F59E0B/FFFFFF?text=Design+3',
                similarity_score: 0.68,
                similarity_level: 'medium',
                status: 'similar',
                applicant: '애플코리아',
                filing_date: '2022-03-10'
            },
            {
                id: 4,
                patent_number: 'KR30-2021-0067890',
                title: '무선 이어폰 케이스',
                image_url: 'https://via.placeholder.com/400x300/EF4444/FFFFFF?text=Design+4',
                similarity_score: 0.89,
                similarity_level: 'high',
                status: 'similar',
                applicant: '삼성전자',
                filing_date: '2021-11-20'
            },
            {
                id: 5,
                patent_number: 'KR30-2020-0023456',
                title: '스마트워치 디스플레이',
                image_url: 'https://via.placeholder.com/400x300/10B981/FFFFFF?text=Design+5',
                similarity_score: 0.25,
                similarity_level: 'low',
                status: 'not_similar',
                applicant: '구글코리아',
                filing_date: '2020-05-15'
            },
            {
                id: 6,
                patent_number: 'KR30-2022-0012789',
                title: '게이밍 키보드 디자인',
                image_url: 'https://via.placeholder.com/400x300/10B981/FFFFFF?text=Design+6',
                similarity_score: 0.42,
                similarity_level: 'low',
                status: 'not_similar',
                applicant: '로지텍',
                filing_date: '2022-01-30'
            }
        ]
    }
};

// Initialize page
document.addEventListener('DOMContentLoaded', () => {
    loadCombinedResults();
});

// Load combined results
function loadCombinedResults() {
    const data = mockCombinedResults;
    
    // Render overall risk assessment
    renderOverallRisk(data.fto.verdict, data.design.verdict);
    
    // Render FTO content
    renderFTOContent(data.fto);
    
    // Render Design content
    renderDesignContent(data.design);
}

// Render overall risk assessment
function renderOverallRisk(ftoVerdict, designVerdict) {
    // FTO Risk Icon
    const ftoRiskIcon = document.getElementById('ftoRiskIcon');
    const ftoRiskText = document.getElementById('ftoRiskText');
    const ftoPatentCount = document.getElementById('ftoPatentCount');
    
    const ftoColors = {
        safe: { bg: 'bg-green-500', text: '안전', icon: '✓' },
        warning: { bg: 'bg-yellow-500', text: '경고', icon: '⚠' },
        danger: { bg: 'bg-red-500', text: '위험', icon: '✗' }
    };
    
    const ftoConfig = ftoColors[ftoVerdict];
    ftoRiskIcon.className = `w-20 h-20 rounded-full flex items-center justify-center ${ftoConfig.bg} text-white text-3xl font-black`;
    ftoRiskIcon.textContent = ftoConfig.icon;
    ftoRiskText.textContent = ftoConfig.text;
    ftoRiskText.className = `text-2xl font-black ${ftoVerdict === 'safe' ? 'text-green-600' : ftoVerdict === 'warning' ? 'text-yellow-600' : 'text-red-600'}`;
    
    // Design Risk Icon
    const designRiskIcon = document.getElementById('designRiskIcon');
    const designRiskText = document.getElementById('designRiskText');
    const designImageCount = document.getElementById('designImageCount');
    
    const designConfig = ftoColors[designVerdict];
    designRiskIcon.className = `w-20 h-20 rounded-full flex items-center justify-center ${designConfig.bg} text-white text-3xl font-black`;
    designRiskIcon.textContent = designConfig.icon;
    designRiskText.textContent = designConfig.text;
    designRiskText.className = `text-2xl font-black ${designVerdict === 'safe' ? 'text-green-600' : designVerdict === 'warning' ? 'text-yellow-600' : 'text-red-600'}`;
    
    // Overall risk judgment
    const overallRisk = document.getElementById('overallRisk');
    const overallRiskText = document.getElementById('overallRiskText');
    
    let overallVerdict, overallMessage, overallBorder;
    
    if (ftoVerdict === 'danger' || designVerdict === 'danger') {
        overallVerdict = 'danger';
        overallMessage = '특허 또는 디자인 침해 위험이 높습니다. 즉시 전문가 상담을 받으시기 바랍니다.';
        overallBorder = 'border-red-400';
    } else if (ftoVerdict === 'warning' || designVerdict === 'warning') {
        overallVerdict = 'warning';
        overallMessage = '일부 침해 가능성이 발견되었습니다. 변리사의 상세 검토를 권장합니다.';
        overallBorder = 'border-yellow-400';
    } else {
        overallVerdict = 'safe';
        overallMessage = '전반적으로 침해 위험이 낮습니다. 다만, 최종 판단은 전문가와 상의하시기 바랍니다.';
        overallBorder = 'border-green-400';
    }
    
    overallRisk.className = `mt-6 p-6 bg-slate-50 rounded-xl border-2 ${overallBorder}`;
    overallRiskText.textContent = overallMessage;
}

// Render FTO content
function renderFTOContent(ftoData) {
    // Patents list
    const patentsList = document.getElementById('ftoPatentsList');
    patentsList.innerHTML = ftoData.patents.map(patent => `
        <div class="p-4 bg-slate-50 rounded-lg border border-slate-200">
            <div class="flex justify-between items-start mb-2">
                <span class="font-bold text-slate-900">${patent.number}</span>
                <span class="px-3 py-1 ${getSimilarityBadgeClass(patent.similarity)} rounded-full text-xs font-bold">
                    ${getSimilarityText(patent.similarity)}
                </span>
            </div>
            <h4 class="font-bold text-slate-900 mb-1">${patent.title}</h4>
            <p class="text-sm text-slate-600 mb-2">${patent.description}</p>
            <div class="flex justify-between text-xs text-slate-500">
                <span>출원인: ${patent.applicant}</span>
                <span>${patent.filingDate}</span>
            </div>
        </div>
    `).join('');
    
    // Component mapping table
    const mappingTableBody = document.getElementById('mappingTableBody');
    mappingTableBody.innerHTML = ftoData.mappings.map(mapping => `
        <tr class="border-b border-slate-100">
            <td class="px-4 py-3">${mapping.product}</td>
            <td class="px-4 py-3">${mapping.patent}</td>
            <td class="px-4 py-3 text-center">
                <span class="px-3 py-1 ${mapping.mapped ? 'bg-blue-100 text-blue-700' : 'bg-slate-100 text-slate-600'} rounded-full text-xs font-bold">
                    ${mapping.mapped ? '✓ 매핑됨' : '✗ 미매핑'}
                </span>
            </td>
            <td class="px-4 py-3 text-center">
                <span class="px-3 py-1 ${getRiskBadgeClass(mapping.risk)} rounded-full text-xs font-bold">
                    ${getRiskText(mapping.risk)}
                </span>
            </td>
        </tr>
    `).join('');
    
    // FTO suggestions
    const suggestionsList = document.getElementById('ftoSuggestionsList');
    suggestionsList.innerHTML = ftoData.ftoSuggestions.map(suggestion => `
        <div class="p-6 bg-blue-50 rounded-xl border border-blue-200">
            <h4 class="font-bold text-slate-900 mb-2 flex items-center gap-2">
                <i class="fas fa-lightbulb text-blue-600"></i>
                ${suggestion.title}
            </h4>
            <p class="text-sm text-slate-600 mb-3">${suggestion.description}</p>
            <div class="flex items-center gap-2 text-xs text-green-700 bg-green-100 px-3 py-1 rounded-full inline-block">
                <i class="fas fa-check-circle"></i>
                ${suggestion.benefit}
            </div>
        </div>
    `).join('');
}

// Render Design content
function renderDesignContent(designData) {
    const grid = document.getElementById('designImageGrid');
    
    grid.innerHTML = designData.results.map(item => {
        const similarityColor = getSimilarityColorClass(item.similarity_level);
        const statusBadge = item.status === 'similar' 
            ? '<span class="inline-flex items-center px-3 py-1 bg-red-100 text-red-700 rounded-full text-sm font-bold"><i class="fas fa-exclamation-triangle mr-1"></i>유사</span>'
            : '<span class="inline-flex items-center px-3 py-1 bg-green-100 text-green-700 rounded-full text-sm font-bold"><i class="fas fa-check-circle mr-1"></i>비유사</span>';
        
        return `
            <div class="bg-white rounded-xl border-2 ${item.similarity_level === 'high' ? 'border-red-400' : 'border-slate-200'} overflow-hidden">
                <div class="relative bg-slate-100">
                    <img 
                        src="${item.image_url}" 
                        alt="${item.title}" 
                        class="w-full h-48 object-cover"
                    />
                    <div class="absolute top-3 left-3">
                        <div class="px-3 py-1 ${similarityColor} rounded-full text-sm font-bold backdrop-blur-sm">
                            ${Math.round(item.similarity_score * 100)}%
                        </div>
                    </div>
                    <div class="absolute top-3 right-3">
                        ${statusBadge}
                    </div>
                </div>
                <div class="p-5">
                    <div class="text-xs text-slate-500 font-bold mb-1">${item.patent_number}</div>
                    <h3 class="font-bold text-slate-900 mb-3">${item.title}</h3>
                    <div class="flex justify-between text-sm text-slate-500">
                        <span>${item.applicant}</span>
                        <span>${item.filing_date}</span>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

// Tab switching
function switchTab(tabName) {
    // Update tab buttons
    const tabs = document.querySelectorAll('.tab-btn');
    tabs.forEach(tab => {
        tab.classList.remove('active', 'text-slate-900', 'border-blue-600');
        tab.classList.add('text-slate-500', 'border-transparent');
    });
    
    const activeTab = document.getElementById(`tab-${tabName}`);
    activeTab.classList.add('active', 'text-slate-900', 'border-blue-600');
    activeTab.classList.remove('text-slate-500', 'border-transparent');
    
    // Update content
    const contents = document.querySelectorAll('.tab-content');
    contents.forEach(content => content.classList.add('hidden'));
    
    document.getElementById(`content-${tabName}`).classList.remove('hidden');
}

// Helper functions
function getSimilarityBadgeClass(level) {
    const classes = {
        high: 'bg-red-100 text-red-700',
        medium: 'bg-yellow-100 text-yellow-700',
        low: 'bg-green-100 text-green-700'
    };
    return classes[level] || 'bg-slate-100 text-slate-700';
}

function getSimilarityText(level) {
    const texts = {
        high: '높음',
        medium: '보통',
        low: '낮음'
    };
    return texts[level] || '알 수 없음';
}

function getSimilarityColorClass(level) {
    const colors = {
        high: 'bg-red-500 text-white',
        medium: 'bg-yellow-500 text-white',
        low: 'bg-green-500 text-white'
    };
    return colors[level] || 'bg-slate-500 text-white';
}

function getRiskBadgeClass(risk) {
    const classes = {
        high: 'bg-red-100 text-red-700',
        medium: 'bg-yellow-100 text-yellow-700',
        low: 'bg-green-100 text-green-700'
    };
    return classes[risk] || 'bg-slate-100 text-slate-700';
}

function getRiskText(risk) {
    const texts = {
        high: '높음',
        medium: '보통',
        low: '낮음'
    };
    return texts[risk] || '알 수 없음';
}

// Download report
function downloadReport() {
    Toast.info('종합 보고서 다운로드 기능은 준비 중입니다.');
}

// Export for global access
window.switchTab = switchTab;
window.downloadReport = downloadReport;
