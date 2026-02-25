// Design Results Page JavaScript

// localStorage에서 실제 분석 결과를 읽거나, 없으면 빈 상태로 표시
let designResultsData = null;

// Initialize page
document.addEventListener('DOMContentLoaded', () => {
    loadDesignResults();
});

// Load design results
function loadDesignResults() {
    // localStorage에서 디자인 분석 결과 읽기
    const stored = localStorage.getItem('designAnalysisResult');
    if (stored) {
        try {
            const apiResult = JSON.parse(stored);
            designResultsData = convertApiResultToPageFormat(apiResult);
        } catch (e) {
            console.error('디자인 분석 결과 파싱 실패:', e);
        }
    }

    if (!designResultsData) {
        // 데이터 없으면 안내 메시지
        const grid = document.getElementById('imageGrid');
        if (grid) {
            grid.innerHTML = `
                <div style="grid-column: 1 / -1; text-align: center; padding: 60px 20px; color: #64748b;">
                    <h3>분석 결과가 없습니다</h3>
                    <p style="margin-top: 8px;">분석 페이지에서 이미지를 업로드하여 디자인 분석을 먼저 수행해주세요.</p>
                    <a href="design-chat.html" style="display:inline-block; margin-top:16px; padding:10px 24px; background:#FF6B35; color:white; border-radius:8px; text-decoration:none;">디자인 분석 시작</a>
                </div>
            `;
        }
        return;
    }

    const data = designResultsData;

    // Update summary
    const totalEl = document.getElementById('totalCount');
    const highEl = document.getElementById('highSimilarityCount');
    const lowEl = document.getElementById('lowSimilarityCount');
    if (totalEl) totalEl.textContent = `${data.total_count}건`;
    if (highEl) highEl.textContent = `${data.high_similarity}건`;
    if (lowEl) lowEl.textContent = `${data.low_similarity}건`;

    // Render image grid
    renderImageGrid(data.results);

    // Render human validation inputs
    renderHumanValidation(data.results);
}

// API 응답 형식 → 페이지 표시 형식으로 변환
function convertApiResultToPageFormat(apiResult) {
    const designs = apiResult.similar_designs || [];
    const results = designs.map((d, i) => {
        const score = 1 - d.distance; // distance → similarity (0~1)
        const level = score >= 0.7 ? 'high' : score >= 0.4 ? 'medium' : 'low';
        return {
            id: d.index || (i + 1),
            patent_number: d.application_number || 'N/A',
            title: d.article_name || 'N/A',
            image_url: d.image_base64 ? `data:image/jpeg;base64,${d.image_base64}` : '',
            similarity_score: Math.max(0, Math.min(1, score)),
            similarity_level: level,
            status: score >= 0.5 ? 'similar' : 'not_similar',
            applicant: d.admst_stat || 'N/A',
            filing_date: d.last_disposition_date || '',
        };
    });

    const highCount = results.filter(r => r.similarity_level === 'high').length;
    return {
        total_count: results.length,
        high_similarity: highCount,
        low_similarity: results.length - highCount,
        input_analysis: apiResult.input_analysis || '',
        results: results,
    };
}

// Render image grid
function renderImageGrid(results) {
    const grid = document.getElementById('imageGrid');
    
    grid.innerHTML = results.map(item => {
        const similarityColor = getSimilarityColor(item.similarity_level);
        const similarityText = getSimilarityText(item.similarity_level);
        const statusBadge = item.status === 'similar' 
            ? '<span class="inline-flex items-center px-3 py-1 bg-red-100 text-red-700 rounded-full text-sm font-bold"><i class="fas fa-exclamation-triangle mr-1"></i>유사</span>'
            : '<span class="inline-flex items-center px-3 py-1 bg-green-100 text-green-700 rounded-full text-sm font-bold"><i class="fas fa-check-circle mr-1"></i>비유사</span>';
        
        return `
            <div class="design-card bg-white rounded-xl border-2 ${item.similarity_level === 'high' ? 'border-red-400 shadow-lg shadow-red-100' : 'border-slate-200'} overflow-hidden transition-all hover:shadow-xl group">
                <!-- 이미지 -->
                <div class="relative overflow-hidden bg-slate-100">
                    <img 
                        src="${item.image_url}" 
                        alt="${item.title}" 
                        class="w-full h-48 object-cover transition-transform group-hover:scale-110"
                        onerror="this.src='https://via.placeholder.com/400x300/E5E7EB/9CA3AF?text=No+Image'"
                    />
                    
                    <!-- 유사도 배지 -->
                    <div class="absolute top-3 left-3">
                        <div class="px-3 py-1 ${similarityColor} rounded-full text-sm font-bold backdrop-blur-sm">
                            ${Math.round(item.similarity_score * 100)}% 유사
                        </div>
                    </div>
                    
                    <!-- 상태 배지 -->
                    <div class="absolute top-3 right-3">
                        ${statusBadge}
                    </div>
                </div>
                
                <!-- 정보 -->
                <div class="p-5">
                    <div class="text-xs text-slate-500 font-bold mb-1">${item.patent_number}</div>
                    <h3 class="font-bold text-slate-900 mb-3 text-lg">${item.title}</h3>
                    
                    <!-- 유사도 바 -->
                    <div class="mb-3">
                        <div class="flex justify-between text-xs text-slate-500 mb-1">
                            <span>유사도</span>
                            <span class="font-bold">${similarityText}</span>
                        </div>
                        <div class="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
                            <div class="h-full ${similarityColor} transition-all" style="width: ${item.similarity_score * 100}%"></div>
                        </div>
                    </div>
                    
                    <div class="flex justify-between text-sm text-slate-500">
                        <span>출원인: ${item.applicant}</span>
                        <span>${item.filing_date}</span>
                    </div>
                    
                    <!-- 상세보기 버튼 -->
                    <button 
                        onclick="viewDetails(${item.id})"
                        class="mt-4 w-full py-2 bg-slate-50 hover:bg-slate-100 text-slate-700 rounded-lg font-bold transition text-sm"
                    >
                        상세 보기
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

// Get similarity color
function getSimilarityColor(level) {
    const colors = {
        high: 'bg-red-500 text-white',
        medium: 'bg-yellow-500 text-white',
        low: 'bg-green-500 text-white'
    };
    return colors[level] || 'bg-slate-500 text-white';
}

// Get similarity text
function getSimilarityText(level) {
    const texts = {
        high: '높음',
        medium: '보통',
        low: '낮음'
    };
    return texts[level] || '알 수 없음';
}

// Render human validation inputs
function renderHumanValidation(results) {
    const container = document.getElementById('humanValidationList');
    
    // Only show first 5 for brevity
    const validationItems = results.slice(0, 5);
    
    container.innerHTML = validationItems.map(item => `
        <div class="flex items-center justify-between p-4 bg-slate-50 rounded-lg">
            <div class="flex items-center gap-4">
                <img 
                    src="${item.image_url}" 
                    alt="${item.title}"
                    class="w-20 h-20 object-cover rounded-lg border-2 border-slate-200"
                />
                <div>
                    <div class="font-bold text-slate-900">${item.patent_number}</div>
                    <div class="text-sm text-slate-500">${item.title}</div>
                    <div class="text-xs text-slate-400 mt-1">
                        AI 판단: <span class="font-bold ${item.status === 'similar' ? 'text-red-600' : 'text-green-600'}">
                            ${item.status === 'similar' ? '유사' : '비유사'}
                        </span>
                    </div>
                </div>
            </div>
            
            <div class="flex gap-2">
                <button 
                    onclick="validateHuman(${item.id}, 'similar')"
                    class="px-4 py-2 bg-red-100 text-red-700 rounded-lg font-bold hover:bg-red-200 transition text-sm"
                    id="similar-${item.id}"
                >
                    유사
                </button>
                <button 
                    onclick="validateHuman(${item.id}, 'not_similar')"
                    class="px-4 py-2 bg-green-100 text-green-700 rounded-lg font-bold hover:bg-green-200 transition text-sm"
                    id="not_similar-${item.id}"
                >
                    비유사
                </button>
            </div>
        </div>
    `).join('');
}

// Validate human judgment
const humanValidations = {};

function validateHuman(itemId, judgment) {
    humanValidations[itemId] = judgment;
    
    // Update button states
    const similarBtn = document.getElementById(`similar-${itemId}`);
    const notSimilarBtn = document.getElementById(`not_similar-${itemId}`);
    
    if (judgment === 'similar') {
        similarBtn.classList.add('ring-2', 'ring-red-500');
        notSimilarBtn.classList.remove('ring-2', 'ring-green-500');
    } else {
        notSimilarBtn.classList.add('ring-2', 'ring-green-500');
        similarBtn.classList.remove('ring-2', 'ring-red-500');
    }
    
    Toast.success('사람 검증이 기록되었습니다.');
    
    // Check for mismatches
    checkMismatches();
}

// Check for mismatches between AI and human
function checkMismatches() {
    if (!designResultsData) return;
    const mismatches = [];

    designResultsData.results.forEach(item => {
        const humanJudgment = humanValidations[item.id];
        if (humanJudgment && humanJudgment !== item.status) {
            mismatches.push({
                ...item,
                human_judgment: humanJudgment
            });
        }
    });

    if (mismatches.length > 0) {
        renderMismatches(mismatches);
    }
}

// Render mismatches
function renderMismatches(mismatches) {
    const section = document.getElementById('mismatchSection');
    const list = document.getElementById('mismatchList');
    
    section.style.display = 'block';
    
    list.innerHTML = mismatches.map(item => `
        <div class="bg-white rounded-xl p-6 border-2 border-red-300">
            <div class="flex items-start gap-6">
                <img 
                    src="${item.image_url}" 
                    alt="${item.title}"
                    class="w-32 h-24 object-cover rounded-lg border-2 border-slate-200"
                />
                <div class="flex-1">
                    <div class="flex items-center gap-3 mb-2">
                        <span class="font-bold text-slate-900 text-lg">${item.patent_number}</span>
                        <span class="text-slate-500">${item.title}</span>
                    </div>
                    
                    <div class="flex gap-6 mt-4">
                        <div>
                            <div class="text-xs text-slate-500 mb-1">AI 판단</div>
                            <div class="px-3 py-1 ${item.status === 'similar' ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'} rounded-lg font-bold inline-block">
                                ${item.status === 'similar' ? '유사' : '비유사'}
                            </div>
                        </div>
                        <div>
                            <div class="text-xs text-slate-500 mb-1">사람 판단</div>
                            <div class="px-3 py-1 ${item.human_judgment === 'similar' ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700'} rounded-lg font-bold inline-block">
                                ${item.human_judgment === 'similar' ? '유사' : '비유사'}
                            </div>
                        </div>
                    </div>
                    
                    <div class="mt-4 text-sm text-red-800 bg-red-50 p-3 rounded-lg">
                        <i class="fas fa-info-circle mr-2"></i>
                        <strong>불일치 사유:</strong> AI와 사람의 판단이 다릅니다. 이 사례를 모델 개선에 활용합니다.
                    </div>
                </div>
            </div>
        </div>
    `).join('');
}

// View details
function viewDetails(itemId) {
    if (!designResultsData) return;
    const item = designResultsData.results.find(r => r.id === itemId);
    if (item) {
        Toast.info(`${item.patent_number} 상세 정보를 불러오는 중...`);
    }
}

// Download report
function downloadReport() {
    Toast.info('PDF 다운로드 기능은 준비 중입니다.');
    // In production, generate PDF report
}