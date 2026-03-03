-- 디자인 세션 테이블 (S3 + RDS 멀티턴 지원)
-- FTOGuard 디자인 분석 세션 관리용

-- 1. design_sessions: 세션 메타데이터
CREATE TABLE IF NOT EXISTS design_sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    thread_id VARCHAR(100) NOT NULL UNIQUE,
    user_id INT,
    status ENUM('analyzing','waiting_selection','comparing','completed','error') DEFAULT 'analyzing',
    input_analysis TEXT,
    comparison_results_json JSON,
    selected_index INT,
    final_report TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_thread_id (thread_id),
    INDEX idx_status (status),
    INDEX idx_user_id (user_id)
);

-- 2. design_session_images: S3 이미지 URL 저장
CREATE TABLE IF NOT EXISTS design_session_images (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id INT NOT NULL,
    image_type ENUM('user_upload','similar_design') NOT NULL,
    s3_key VARCHAR(500) NOT NULL,
    s3_url VARCHAR(1000) NOT NULL,
    original_filename VARCHAR(255),
    file_size INT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_session_id (session_id),
    FOREIGN KEY (session_id) REFERENCES design_sessions(id) ON DELETE CASCADE
);

-- 3. design_session_messages: 멀티턴 대화 히스토리
CREATE TABLE IF NOT EXISTS design_session_messages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id INT NOT NULL,
    role ENUM('user','assistant') NOT NULL,
    content TEXT NOT NULL,
    image_id INT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_session_id (session_id),
    INDEX idx_created_at (created_at),
    FOREIGN KEY (session_id) REFERENCES design_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (image_id) REFERENCES design_session_images(id) ON DELETE SET NULL
);

-- 실행 확인
SELECT 'design_session_tables.sql 실행 완료' AS status;
