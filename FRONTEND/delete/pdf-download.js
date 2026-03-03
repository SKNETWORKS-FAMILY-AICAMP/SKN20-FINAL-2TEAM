// PDF Download Feature using jsPDF
// results.html, design-results.html, combined-results.html에서 사용

// jsPDF 라이브러리는 HTML에 다음과 같이 추가:
// <script src="https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js"></script>
// <script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>

// Download FTO Report as PDF
async function downloadFTOReport() {
    try {
        Toast.info('PDF 생성 중...');
        
        // Get jsPDF instance
        const { jsPDF } = window.jspdf;
        const doc = new jsPDF('p', 'mm', 'a4');
        
        // Page settings
        const pageWidth = 210; // A4 width in mm
        const pageHeight = 297; // A4 height in mm
        const margin = 20;
        const contentWidth = pageWidth - (margin * 2);
        let currentY = margin;
        
        // Helper function to add new page
        const addNewPage = () => {
            doc.addPage();
            currentY = margin;
        };
        
        // Helper function to check if new page needed
        const checkNewPage = (height) => {
            if (currentY + height > pageHeight - margin) {
                addNewPage();
                return true;
            }
            return false;
        };
        
        // Add Korean font support (NanumGothic)
        // Note: In production, you need to include Korean font file
        doc.setFont('helvetica');
        
        // === PAGE 1: Cover ===
        // Logo/Header
        doc.setFontSize(24);
        doc.setTextColor(37, 99, 235); // Blue
        doc.text('FTOGuard', margin, currentY);
        currentY += 10;
        
        doc.setFontSize(32);
        doc.setTextColor(0, 0, 0);
        doc.text('FTO Analysis Report', margin, currentY);
        currentY += 15;
        
        // Verdict
        const verdict = document.querySelector('.verdict-headline')?.textContent || 'Analysis Complete';
        doc.setFontSize(20);
        doc.setTextColor(100, 100, 100);
        doc.text(verdict, margin, currentY);
        currentY += 20;
        
        // Date
        doc.setFontSize(12);
        doc.setTextColor(150, 150, 150);
        doc.text(`Report Date: ${new Date().toLocaleDateString()}`, margin, currentY);
        currentY += 10;
        
        doc.text(`Analysis ID: ${currentAnalysisId || 'N/A'}`, margin, currentY);
        currentY += 30;
        
        // Disclaimer
        doc.setFontSize(10);
        doc.setTextColor(200, 0, 0);
        doc.text('DISCLAIMER:', margin, currentY);
        currentY += 6;
        
        doc.setTextColor(100, 100, 100);
        const disclaimerText = 'This analysis is for reference purposes only and does not constitute legal advice. Please consult with a patent attorney for official legal guidance.';
        const splitDisclaimer = doc.splitTextToSize(disclaimerText, contentWidth);
        doc.text(splitDisclaimer, margin, currentY);
        currentY += (splitDisclaimer.length * 5) + 10;
        
        // === PAGE 2: Summary ===
        addNewPage();
        
        doc.setFontSize(18);
        doc.setTextColor(0, 0, 0);
        doc.text('Executive Summary', margin, currentY);
        currentY += 10;
        
        // Risk Level
        doc.setFontSize(14);
        doc.text('Risk Assessment:', margin, currentY);
        currentY += 8;
        
        const riskLevel = document.querySelector('.verdict-badge')?.textContent || 'Medium';
        doc.setFontSize(12);
        doc.text(`Risk Level: ${riskLevel}`, margin + 5, currentY);
        currentY += 10;
        
        // Patent Count
        const patentCount = document.querySelectorAll('.patent-card').length;
        doc.text(`Patents Analyzed: ${patentCount}`, margin + 5, currentY);
        currentY += 10;
        
        // Confidence
        const confidence = document.querySelector('.confidence-percentage')?.textContent || '0%';
        doc.text(`Confidence: ${confidence}`, margin + 5, currentY);
        currentY += 15;
        
        // === PAGE 3: Patent List ===
        addNewPage();
        
        doc.setFontSize(18);
        doc.text('Identified Patents', margin, currentY);
        currentY += 12;
        
        const patents = document.querySelectorAll('.patent-card');
        patents.forEach((patent, index) => {
            checkNewPage(30);
            
            const number = patent.querySelector('.patent-number')?.textContent || 'N/A';
            const title = patent.querySelector('.patent-title')?.textContent || 'No Title';
            const similarity = patent.querySelector('.similarity-badge')?.textContent || '';
            
            doc.setFontSize(12);
            doc.setTextColor(0, 0, 0);
            doc.text(`${index + 1}. ${number}`, margin, currentY);
            currentY += 6;
            
            doc.setFontSize(10);
            doc.setTextColor(100, 100, 100);
            const splitTitle = doc.splitTextToSize(title, contentWidth - 10);
            doc.text(splitTitle, margin + 5, currentY);
            currentY += (splitTitle.length * 5) + 3;
            
            if (similarity) {
                doc.setTextColor(150, 150, 150);
                doc.text(`Similarity: ${similarity}`, margin + 5, currentY);
                currentY += 8;
            }
            
            currentY += 5;
        });
        
        // === PAGE 4: Component Mapping ===
        addNewPage();
        
        doc.setFontSize(18);
        doc.setTextColor(0, 0, 0);
        doc.text('Component Mapping', margin, currentY);
        currentY += 12;
        
        const mappings = document.querySelectorAll('#componentMappingTable tbody tr');
        if (mappings.length > 0) {
            // Table header
            doc.setFontSize(10);
            doc.setTextColor(100, 100, 100);
            doc.text('Product Component', margin, currentY);
            doc.text('Patent Claim', margin + 60, currentY);
            doc.text('Status', margin + 130, currentY);
            currentY += 8;
            
            // Draw line
            doc.setDrawColor(200, 200, 200);
            doc.line(margin, currentY, pageWidth - margin, currentY);
            currentY += 5;
            
            // Table rows
            mappings.forEach((row, index) => {
                checkNewPage(15);
                
                const cells = row.querySelectorAll('td');
                if (cells.length >= 3) {
                    doc.setFontSize(9);
                    doc.setTextColor(0, 0, 0);
                    
                    const component = cells[0].textContent.trim();
                    const claim = cells[1].textContent.trim();
                    const status = cells[2].textContent.trim();
                    
                    doc.text(doc.splitTextToSize(component, 50), margin, currentY);
                    doc.text(doc.splitTextToSize(claim, 60), margin + 60, currentY);
                    doc.text(status, margin + 130, currentY);
                    
                    currentY += 10;
                }
            });
        }
        
        // === PAGE 5: FTO Suggestions ===
        addNewPage();
        
        doc.setFontSize(18);
        doc.setTextColor(0, 0, 0);
        doc.text('Freedom-to-Operate Suggestions', margin, currentY);
        currentY += 12;
        
        const suggestions = document.querySelectorAll('.fto-suggestion-card');
        suggestions.forEach((suggestion, index) => {
            checkNewPage(25);
            
            const title = suggestion.querySelector('.suggestion-title')?.textContent || '';
            const description = suggestion.querySelector('.suggestion-description')?.textContent || '';
            
            doc.setFontSize(12);
            doc.setTextColor(37, 99, 235);
            doc.text(`${index + 1}. ${title}`, margin, currentY);
            currentY += 7;
            
            doc.setFontSize(10);
            doc.setTextColor(100, 100, 100);
            const splitDesc = doc.splitTextToSize(description, contentWidth - 10);
            doc.text(splitDesc, margin + 5, currentY);
            currentY += (splitDesc.length * 5) + 8;
        });
        
        // === Footer on all pages ===
        const pageCount = doc.internal.getNumberOfPages();
        for (let i = 1; i <= pageCount; i++) {
            doc.setPage(i);
            doc.setFontSize(8);
            doc.setTextColor(150, 150, 150);
            doc.text(
                `Page ${i} of ${pageCount}`,
                pageWidth / 2,
                pageHeight - 10,
                { align: 'center' }
            );
            doc.text(
                'Generated by FTOGuard - Patent Analysis Platform',
                pageWidth / 2,
                pageHeight - 5,
                { align: 'center' }
            );
        }
        
        // Save PDF
        const filename = `FTO_Report_${currentAnalysisId || Date.now()}.pdf`;
        doc.save(filename);
        
        Toast.success('PDF 다운로드 완료!');
        
    } catch (error) {
        console.error('PDF generation error:', error);
        Toast.error('PDF 생성 중 오류가 발생했습니다.');
    }
}

// Download Design Report as PDF
async function downloadDesignReport() {
    try {
        Toast.info('PDF 생성 중...');
        
        const { jsPDF } = window.jspdf;
        const doc = new jsPDF('p', 'mm', 'a4');
        
        const pageWidth = 210;
        const pageHeight = 297;
        const margin = 20;
        let currentY = margin;
        
        // Cover
        doc.setFontSize(24);
        doc.setTextColor(37, 99, 235);
        doc.text('FTOGuard', margin, currentY);
        currentY += 10;
        
        doc.setFontSize(32);
        doc.setTextColor(0, 0, 0);
        doc.text('Design Similarity Report', margin, currentY);
        currentY += 15;
        
        doc.setFontSize(12);
        doc.setTextColor(150, 150, 150);
        doc.text(`Report Date: ${new Date().toLocaleDateString()}`, margin, currentY);
        currentY += 30;
        
        // Summary
        const totalCount = document.getElementById('totalCount')?.textContent || '0';
        const highSimilarity = document.getElementById('highSimilarityCount')?.textContent || '0';
        
        doc.setFontSize(14);
        doc.setTextColor(0, 0, 0);
        doc.text('Summary', margin, currentY);
        currentY += 10;
        
        doc.setFontSize(12);
        doc.text(`Total Designs Searched: ${totalCount}`, margin + 5, currentY);
        currentY += 7;
        doc.text(`High Similarity: ${highSimilarity}`, margin + 5, currentY);
        currentY += 15;
        
        // Design list (without images - text only)
        doc.setFontSize(14);
        doc.text('Similar Designs', margin, currentY);
        currentY += 10;
        
        const designs = document.querySelectorAll('.design-card');
        designs.forEach((design, index) => {
            if (currentY > pageHeight - 40) {
                doc.addPage();
                currentY = margin;
            }
            
            const patentNumber = design.querySelector('.text-xs')?.textContent || 'N/A';
            const title = design.querySelector('.font-bold.text-slate-900')?.textContent || 'No Title';
            const similarity = design.querySelector('.px-3.py-1')?.textContent || '';
            
            doc.setFontSize(11);
            doc.setTextColor(0, 0, 0);
            doc.text(`${index + 1}. ${patentNumber}`, margin, currentY);
            currentY += 6;
            
            doc.setFontSize(10);
            doc.setTextColor(100, 100, 100);
            doc.text(title, margin + 5, currentY);
            currentY += 6;
            
            if (similarity) {
                doc.text(`Similarity: ${similarity}`, margin + 5, currentY);
                currentY += 10;
            }
        });
        
        // Footer
        const pageCount = doc.internal.getNumberOfPages();
        for (let i = 1; i <= pageCount; i++) {
            doc.setPage(i);
            doc.setFontSize(8);
            doc.setTextColor(150, 150, 150);
            doc.text(`Page ${i} of ${pageCount}`, pageWidth / 2, pageHeight - 10, { align: 'center' });
        }
        
        const filename = `Design_Report_${Date.now()}.pdf`;
        doc.save(filename);
        
        Toast.success('PDF 다운로드 완료!');
        
    } catch (error) {
        console.error('PDF generation error:', error);
        Toast.error('PDF 생성 중 오류가 발생했습니다.');
    }
}

// Download Combined Report as PDF
async function downloadCombinedReport() {
    try {
        Toast.info('종합 보고서 PDF 생성 중...');
        
        // Call both functions and combine
        // For now, just create a simple combined report
        
        const { jsPDF } = window.jspdf;
        const doc = new jsPDF('p', 'mm', 'a4');
        
        // Cover
        doc.setFontSize(28);
        doc.setTextColor(37, 99, 235);
        doc.text('Multimodal Analysis Report', 20, 30);
        
        doc.setFontSize(16);
        doc.setTextColor(100, 100, 100);
        doc.text('FTO + Design Similarity Analysis', 20, 45);
        
        doc.setFontSize(12);
        doc.setTextColor(150, 150, 150);
        doc.text(`Generated: ${new Date().toLocaleString()}`, 20, 60);
        
        // Add comprehensive disclaimer
        doc.setFontSize(10);
        doc.setTextColor(200, 0, 0);
        doc.text('FOR REFERENCE ONLY - NOT LEGAL ADVICE', 20, 80);
        
        const filename = `Combined_Report_${Date.now()}.pdf`;
        doc.save(filename);
        
        Toast.success('PDF 다운로드 완료!');
        
    } catch (error) {
        console.error('PDF generation error:', error);
        Toast.error('PDF 생성 중 오류가 발생했습니다.');
    }
}

// Global exports
window.downloadFTOReport = downloadFTOReport;
window.downloadDesignReport = downloadDesignReport;
window.downloadCombinedReport = downloadCombinedReport;

// Alias for backward compatibility
window.downloadReport = downloadFTOReport;
