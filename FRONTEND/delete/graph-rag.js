// Graph RAG Visualization JavaScript

// Mock data for demonstration
const mockGraphData = {
    nodes: [
        // User Technology
        { id: 'user-1', type: 'user', label: '스마트 머그컵', description: '세라믹 본체 + 내장 가열 소자', group: 1 },
        
        // Patents
        { id: 'patent-1', type: 'patent', label: 'KR10-2021-0123456', description: '스마트 보온 용기 및 제어 방법', group: 2 },
        { id: 'patent-2', type: 'patent', label: 'KR10-2020-0098765', description: '무선 충전 기능을 갖는 스마트 컵', group: 2 },
        { id: 'patent-3', type: 'patent', label: 'KR10-2022-0045678', description: '세라믹 히팅 소자를 이용한 보온 기술', group: 2 },
        
        // Components
        { id: 'comp-1', type: 'component', label: '세라믹 본체', description: '제품의 주요 구성: 세라믹 소재', group: 3 },
        { id: 'comp-2', type: 'component', label: '내장 가열 소자', description: '전기 히팅 엘리먼트', group: 3 },
        { id: 'comp-3', type: 'component', label: '온도 센서', description: 'NTC 서미스터 기반', group: 3 },
        { id: 'comp-4', type: 'component', label: '배터리', description: '리튬이온 배터리 팩', group: 3 },
        
        // Infringement Points
        { id: 'inf-1', type: 'infringement', label: '침해 포인트 1', description: '온도 제어 알고리즘 유사', risk: 'medium', group: 4 },
        { id: 'inf-2', type: 'infringement', label: '침해 포인트 2', description: '가열 소자 배치 구조 유사', risk: 'high', group: 4 }
    ],
    links: [
        // User to Components
        { source: 'user-1', target: 'comp-1', type: 'contains', risk: 'low' },
        { source: 'user-1', target: 'comp-2', type: 'contains', risk: 'low' },
        { source: 'user-1', target: 'comp-3', type: 'contains', risk: 'low' },
        { source: 'user-1', target: 'comp-4', type: 'contains', risk: 'low' },
        
        // Components to Patents
        { source: 'comp-2', target: 'patent-1', type: 'similar', risk: 'medium' },
        { source: 'comp-2', target: 'patent-3', type: 'similar', risk: 'high' },
        { source: 'comp-3', target: 'patent-1', type: 'similar', risk: 'low' },
        { source: 'comp-4', target: 'patent-2', type: 'similar', risk: 'low' },
        
        // Patents to Infringement Points
        { source: 'patent-1', target: 'inf-1', type: 'infringes', risk: 'medium' },
        { source: 'patent-3', target: 'inf-2', type: 'infringes', risk: 'high' }
    ]
};

// Graph dimensions
const width = document.getElementById('graph-container').clientWidth;
const height = document.getElementById('graph-container').clientHeight;

// Create SVG
const svg = d3.select('#graph-container');

// Create zoom behavior
const zoom = d3.zoom()
    .scaleExtent([0.1, 4])
    .on('zoom', (event) => {
        g.attr('transform', event.transform);
    });

svg.call(zoom);

// Create container group
const g = svg.append('g');

// Create force simulation
const simulation = d3.forceSimulation()
    .force('link', d3.forceLink().id(d => d.id).distance(150))
    .force('charge', d3.forceManyBody().strength(-400))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collision', d3.forceCollide().radius(50));

// Store current zoom transform
let currentTransform = d3.zoomIdentity;

// Initialize graph
function initializeGraph(data) {
    // Clear existing elements
    g.selectAll('*').remove();
    
    // Create links
    const link = g.append('g')
        .selectAll('line')
        .data(data.links)
        .join('line')
        .attr('class', d => `link link-${d.risk}-risk`)
        .attr('stroke-width', d => d.risk === 'high' ? 3 : d.risk === 'medium' ? 2 : 1);
    
    // Create nodes
    const node = g.append('g')
        .selectAll('g')
        .data(data.nodes)
        .join('g')
        .attr('class', 'node')
        .call(drag(simulation));
    
    // Add circles to nodes
    node.append('circle')
        .attr('r', d => {
            if (d.type === 'user') return 20;
            if (d.type === 'patent') return 16;
            if (d.type === 'infringement') return 14;
            return 12;
        })
        .attr('class', d => `node-${d.type}`)
        .attr('stroke-width', 2);
    
    // Add labels to nodes
    node.append('text')
        .attr('class', 'node-label')
        .attr('dy', d => {
            if (d.type === 'user') return 30;
            if (d.type === 'patent') return 26;
            if (d.type === 'infringement') return 24;
            return 22;
        })
        .text(d => d.label);
    
    // Add icons to nodes
    node.append('text')
        .attr('class', 'node-icon')
        .attr('text-anchor', 'middle')
        .attr('dy', 5)
        .style('font-family', 'Font Awesome 6 Free')
        .style('font-weight', 900)
        .style('fill', '#fff')
        .style('font-size', d => {
            if (d.type === 'user') return '16px';
            if (d.type === 'patent') return '12px';
            return '10px';
        })
        .text(d => {
            if (d.type === 'user') return '\uf007'; // user icon
            if (d.type === 'patent') return '\uf1c2'; // file icon
            if (d.type === 'component') return '\uf0ad'; // wrench icon
            if (d.type === 'infringement') return '\uf071'; // warning icon
            return '';
        });
    
    // Add click event to nodes
    node.on('click', (event, d) => {
        event.stopPropagation();
        showDetailPanel(d);
    });
    
    // Update simulation
    simulation
        .nodes(data.nodes)
        .on('tick', () => {
            link
                .attr('x1', d => d.source.x)
                .attr('y1', d => d.source.y)
                .attr('x2', d => d.target.x)
                .attr('y2', d => d.target.y);
            
            node.attr('transform', d => `translate(${d.x},${d.y})`);
        });
    
    simulation.force('link').links(data.links);
    
    // Update stats
    updateStats(data);
}

// Drag behavior
function drag(simulation) {
    function dragstarted(event) {
        if (!event.active) simulation.alphaTarget(0.3).restart();
        event.subject.fx = event.subject.x;
        event.subject.fy = event.subject.y;
    }
    
    function dragged(event) {
        event.subject.fx = event.x;
        event.subject.fy = event.y;
    }
    
    function dragended(event) {
        if (!event.active) simulation.alphaTarget(0);
        event.subject.fx = null;
        event.subject.fy = null;
    }
    
    return d3.drag()
        .on('start', dragstarted)
        .on('drag', dragged)
        .on('end', dragended);
}

// Show detail panel
function showDetailPanel(node) {
    const panel = document.getElementById('detail-panel');
    const content = document.getElementById('detail-content');
    
    const typeNames = {
        user: '사용자 기술',
        patent: '특허',
        component: '구성요소',
        infringement: '침해 포인트'
    };
    
    const typeColors = {
        user: 'text-blue-400',
        patent: 'text-red-400',
        component: 'text-purple-400',
        infringement: 'text-yellow-400'
    };
    
    const riskBadge = node.risk ? `
        <span class="px-3 py-1 ${node.risk === 'high' ? 'bg-red-500/20 text-red-400' : node.risk === 'medium' ? 'bg-yellow-500/20 text-yellow-400' : 'bg-green-500/20 text-green-400'} rounded-full text-xs font-bold">
            ${node.risk === 'high' ? '높음' : node.risk === 'medium' ? '보통' : '낮음'}
        </span>
    ` : '';
    
    content.innerHTML = `
        <div class="mb-4">
            <div class="flex items-center gap-2 mb-3">
                <span class="px-3 py-1 bg-slate-800 ${typeColors[node.type]} rounded-lg text-xs font-bold">
                    ${typeNames[node.type]}
                </span>
                ${riskBadge}
            </div>
            <h3 class="text-white font-bold text-lg mb-2">${node.label}</h3>
            <p class="text-slate-400 text-sm leading-relaxed">${node.description}</p>
        </div>
        
        <div class="border-t border-slate-800 pt-4">
            <div class="space-y-3">
                ${node.type === 'patent' ? `
                    <div>
                        <div class="text-slate-500 text-xs mb-1">특허번호</div>
                        <div class="text-white text-sm font-mono">${node.label}</div>
                    </div>
                    <div>
                        <div class="text-slate-500 text-xs mb-1">연관 구성요소</div>
                        <div class="text-white text-sm">${getConnectedComponents(node.id).length}개</div>
                    </div>
                ` : ''}
                
                ${node.type === 'component' ? `
                    <div>
                        <div class="text-slate-500 text-xs mb-1">유사 특허</div>
                        <div class="text-white text-sm">${getConnectedPatents(node.id).length}개</div>
                    </div>
                ` : ''}
                
                ${node.type === 'infringement' ? `
                    <div class="bg-red-500/10 border border-red-500/20 rounded-lg p-3">
                        <div class="text-red-400 text-xs font-bold mb-1">⚠️ 침해 위험도</div>
                        <div class="text-white text-sm">${node.risk === 'high' ? '높음 - 즉시 검토 필요' : '보통 - 주의 필요'}</div>
                    </div>
                ` : ''}
            </div>
        </div>
        
        <div class="mt-4 pt-4 border-t border-slate-800">
            <button onclick="focusNode('${node.id}')" class="w-full py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-bold transition">
                <i class="fas fa-crosshairs mr-2"></i>노드 중심으로
            </button>
        </div>
    `;
    
    panel.classList.add('active');
}

// Close detail panel
function closeDetailPanel() {
    document.getElementById('detail-panel').classList.remove('active');
}

// Helper functions
function getConnectedComponents(patentId) {
    return mockGraphData.links.filter(l => l.target === patentId && l.source.startsWith('comp-'));
}

function getConnectedPatents(componentId) {
    return mockGraphData.links.filter(l => l.source === componentId && l.target.startsWith('patent-'));
}

// Focus on specific node
function focusNode(nodeId) {
    const node = mockGraphData.nodes.find(n => n.id === nodeId);
    if (node) {
        const scale = 1.5;
        const x = width / 2 - node.x * scale;
        const y = height / 2 - node.y * scale;
        
        svg.transition()
            .duration(750)
            .call(zoom.transform, d3.zoomIdentity.translate(x, y).scale(scale));
    }
}

// Update stats
function updateStats(data) {
    document.getElementById('totalNodes').textContent = data.nodes.length;
    document.getElementById('patentCount').textContent = data.nodes.filter(n => n.type === 'patent').length;
    document.getElementById('infringementCount').textContent = data.nodes.filter(n => n.type === 'infringement').length;
    document.getElementById('linkCount').textContent = data.links.length;
}

// Zoom controls
function zoomIn() {
    svg.transition().duration(300).call(zoom.scaleBy, 1.3);
}

function zoomOut() {
    svg.transition().duration(300).call(zoom.scaleBy, 0.7);
}

function resetZoom() {
    svg.transition().duration(500).call(zoom.transform, d3.zoomIdentity);
}

// Reset graph
function resetGraph() {
    simulation.alpha(1).restart();
    Toast.success('그래프가 초기화되었습니다.');
}

// Export graph
function exportGraph() {
    Toast.info('그래프 내보내기 기능은 준비 중입니다.');
    // In production, export as PNG or SVG
}

// Close panel on click outside
svg.on('click', () => {
    closeDetailPanel();
});

// Initialize on load
document.addEventListener('DOMContentLoaded', () => {
    initializeGraph(mockGraphData);
    Toast.success('Graph RAG 분석이 로드되었습니다.');
});

// Window resize handler
window.addEventListener('resize', () => {
    const newWidth = document.getElementById('graph-container').clientWidth;
    const newHeight = document.getElementById('graph-container').clientHeight;
    
    svg.attr('width', newWidth).attr('height', newHeight);
    simulation.force('center', d3.forceCenter(newWidth / 2, newHeight / 2));
    simulation.alpha(0.3).restart();
});
