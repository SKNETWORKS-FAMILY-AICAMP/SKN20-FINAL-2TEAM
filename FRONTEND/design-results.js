// Design Results Page JavaScript

// Mock data for demonstration
const mockDesignResults = {
    query_image: '/assets/query-design.jpg',
    total_count: 12,
    high_similarity: 3,
    low_similarity: 9,
    results: [
        {
            id: 1,
            patent_number: 'KR30-2021-0012345',
            title: '스마트폰 케이스 디자인',
            image_url: 'https://via.placeholder.com/400x300/3B82F6/FFFFFF?text=Design+1',
            similarity_score: 0.94,
            similarity_level: 'high', // high, medium, low
            status: 'similar', // similar, not_similar
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
        },
        {
            id: 7,
            patent_number: 'KR30-2021-0089012',
            title: '충전 도킹 스테이션',
            image_url: 'https://via.placeholder.com/400x300/F59E0B/FFFFFF?text=Design+7',
            similarity_score: 0.72,
            similarity_level: 'medium',
            status: 'similar',
            applicant: '벨킨',
            filing_date: '2021-12-05'
        },
        {
            id: 8,
            patent_number: 'KR30-2020-0034567',
            title: 'USB 허브 디자인',
            image_url: 'https://via.placeholder.com/400x300/10B981/FFFFFF?text=Design+8',
            similarity_score: 0.19,
            similarity_level: 'low',
            status: 'not_similar',
            applicant: '앤커',
            filing_date: '2020-07-12'
        },
        {
            id: 9,
            patent_number: 'KR30-2022-0056789',
            title: '마우스 패드 디자인',
            image_url: 'https://via.placeholder.com/400x300/10B981/FFFFFF?text=Design+9',
            similarity_score: 0.38,
            similarity_level: 'low',
            status: 'not_similar',
            applicant: '레이저',
            filing_date: '2022-04-20'
        },
        {
            id: 10,
            patent_number: 'KR30-2021-0045612',
            title: '모니터 스탠드',
            image_url: 'https://via.placeholder.com/400x300/10B981/FFFFFF?text=Design+10',
            similarity_score: 0.33,
            similarity_level: 'low',
            status: 'not_similar',
            applicant: '델',
            filing_date: '2021-08-15'
        },
        {
            id: 11,
            patent_number: 'KR30-2022-0078901',
            title: '노트북 거치대',
            image_url: 'https://via.placeholder.com/400x300/10B981/FFFFFF?text=Design+11',
            similarity_score: 0.27,
            similarity_level: 'low',
            status: 'not_similar',
            applicant: 'HP',
            filing_date: '2022-06-10'
        },
        {
            id: 12,
            patent_number: 'KR30-2021-0012348',
            title: '스마트폰 거치대',
            image_url: 'https://via.placeholder.com/400x300/3B82F6/FFFFFF?text=Design+12',
            similarity_score: 0.91,
            similarity_level: 'high',
            status: 'similar',
            applicant: '소니',
            filing_date: '2021-02-28'
        }
    ],
    llm_evaluation: {
        accuracy: 87.3,
        recall: 91.2,
        f1_score: 89.1,
        processing_time: 2.3
    }
};

// Initialize page
document.addEventListener('DOMContentLoaded', () => {
    loadDesignResults();
});

// Load design results
function loadDesignResults() {
    const data = mockDesignResults;
    
    // Update summary
    document.getElementById('totalCount').textContent = `${data.total_count}건`;
    document.getElementById('highSimilarityCount').textContent = `${data.high_similarity}건`;
    document.getElementById('lowSimilarityCount').textContent = `${data.low_similarity}건`;
    
    // Render image grid
    renderImageGrid(data.results);
    
    // Render human validation inputs
    renderHumanValidation(data.results);
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
    const mismatches = [];
    
    mockDesignResults.results.forEach(item => {
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
    const item = mockDesignResults.results.find(r => r.id === itemId);
    if (item) {
        Toast.info(`${item.patent_number} 상세 정보를 불러오는 중...`);
        // In production, navigate to detail page or show modal
    }
}

// Download report
function downloadReport() {
    Toast.info('PDF 다운로드 기능은 준비 중입니다.');
    // In production, generate PDF report
}
