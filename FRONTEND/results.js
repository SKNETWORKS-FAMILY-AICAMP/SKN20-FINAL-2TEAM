// Results Page JavaScript

// Get URL parameters
function getAnalysisId() {
    const params = new URLSearchParams(window.location.search);
    return params.get('id');
}

// Transform RAG result_json to frontend rendering format
function transformRagResult(apiData) {
    const resultJson = apiData.result_json || {};
    const ftoResult = resultJson.fto_result || {};
    const searchResults = resultJson.search_results || [];
    const patentAnalyses = ftoResult.patent_analyses || [];
    const ftoOpinion = ftoResult.fto_opinion || '';

    // risk_level mapping: high→danger, medium→warning, low→safe
    const riskMap = { high: 'danger', medium: 'warning', low: 'safe' };
    const apiRisk = apiData.risk_level || 'low';
    const riskLevel = riskMap[apiRisk] || 'safe';

    // risk_description from fto_opinion
    const riskDescription = ftoOpinion || '분석이 완료되었습니다.';

    // patents from search_results
    const patents = searchResults.slice(0, 10).map(sr => {
        const meta = sr.metadata || {};
        return {
            number: meta.apply_num || sr.patent_id || 'N/A',
            title: meta.invention_title || '제목 없음',
            description: (meta.abstract || '').substring(0, 200),
            similarity: sr.score > 0.03 ? 'high' : sr.score > 0.015 ? 'medium' : 'low',
            applicant: meta.applicant || 'N/A',
            filing_date: meta.application_date || 'N/A',
        };
    });

    // mappings from patent_analyses[].comparisons
    const mappings = [];
    for (const pa of patentAnalyses) {
        for (const comp of (pa.comparisons || [])) {
            mappings.push({
                product_component: comp.user_element || comp.patent_element || '-',
                patent_component: comp.patent_element || '-',
                mapped: (comp.correspondence || '').includes('대응') && !(comp.correspondence || '').includes('미대응'),
                risk: (comp.correspondence || '').includes('미대응') ? 'medium' :
                      (comp.correspondence || '').includes('대응') ? 'low' : 'medium',
            });
        }
    }

    // Generate alternatives based on analysis
    const alternatives = [
        {
            title: '구성요소 변경',
            description: '미대응 구성요소를 활용하여 특허 청구범위를 회피할 수 있습니다.',
            benefit: '특허 침해 위험 감소'
        },
        {
            title: '전문가 상담',
            description: '변리사와 상담하여 구체적인 회피 설계 방안을 마련하세요.',
            benefit: '법적 안정성 확보'
        },
    ];

    return {
        analysis_id: apiData.analysis_id || getAnalysisId(),
        type: '특허 FTO 분석',
        date: apiData.created_at ? new Date(apiData.created_at).toLocaleDateString('ko-KR') : new Date().toLocaleDateString('ko-KR'),
        product_title: (resultJson.query || '제품').substring(0, 50),
        risk_level: riskLevel,
        risk_description: riskDescription,
        patents: patents,
        mappings: mappings.length > 0 ? mappings : [{
            product_component: '-',
            patent_component: '-',
            mapped: false,
            risk: 'low',
        }],
        alternatives: alternatives,
    };
}

// Load analysis data
async function loadAnalysisData() {
    const analysisId = getAnalysisId();

    if (!analysisId) {
        if (typeof Toast !== 'undefined') Toast.warning('분석 ID가 없습니다.');
        return;
    }

    try {
        const data = await apiClient.get('/analysis/' + analysisId);
        const transformed = transformRagResult(data);
        renderAnalysisData(transformed);
    } catch (error) {
        console.error('Failed to load analysis:', error);
        if (typeof Toast !== 'undefined') Toast.error('분석 결과를 불러오는데 실패했습니다.');
    }
}

// Render analysis data
function renderAnalysisData(data) {
    // Meta information
    const analysisType = document.getElementById('analysisType');
    const analysisDate = document.getElementById('analysisDate');
    const analysisTitle = document.getElementById('analysisTitle');

    if (analysisType) analysisType.textContent = data.type;
    if (analysisDate) analysisDate.textContent = data.date;
    if (analysisTitle) analysisTitle.textContent = `${data.product_title} 분석 결과`;

    // Risk summary
    const riskIcon = document.getElementById('riskIcon');
    const riskLevel = document.getElementById('riskLevel');
    const riskDescription = document.getElementById('riskDescription');

    if (riskIcon) riskIcon.className = `risk-icon-large ${data.risk_level}`;

    const riskLevels = {
        safe: '비침해 (안전)',
        warning: '전문가 검토 필요',
        danger: '침해 위험 (고위험)'
    };

    if (riskLevel) riskLevel.textContent = riskLevels[data.risk_level];
    if (riskDescription) riskDescription.textContent = data.risk_description;

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
    if (!grid || !patents.length) return;

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
    if (!tbody || !mappings.length) return;

    tbody.innerHTML = mappings.map(mapping => `
        <tr>
            <td>${mapping.product_component}</td>
            <td>${mapping.patent_component}</td>
            <td>
                <span class="mapping-status ${mapping.mapped ? 'mapped' : 'not-mapped'}">
                    ${mapping.mapped ? '\u2713 매핑됨' : '\u2717 미매핑'}
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
    if (!grid || !alternatives.length) return;

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
    if (typeof Toast !== 'undefined') Toast.info('PDF 다운로드 기능은 준비 중입니다.');
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadAnalysisData();
});
