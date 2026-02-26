-- FTO 프로젝트 RDS 스키마
-- 최종 업데이트: 2026-02-26
-- 대상: AWS RDS MySQL 8.4
-- 현재 RDS 구조 반영

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ============================================
-- 1. 특허 데이터 테이블 (RAG용)
-- ============================================

-- 특허 메타데이터 + 청구항 텍스트
-- PK: apply_num (출원번호)
CREATE TABLE IF NOT EXISTS `patents` (
    `apply_num` VARCHAR(50) NOT NULL PRIMARY KEY COMMENT '출원번호 (PK)',
    `invention_title` TEXT COMMENT '발명명',
    `invention_title_eng` TEXT COMMENT '영문 발명명',
    `ipc` TEXT COMMENT 'IPC 분류코드 (쉼표 구분)',
    `register_status` VARCHAR(20) COMMENT '등록상태 (공개/등록)',
    `open_num` VARCHAR(50) COMMENT '공개번호',
    `regit_num` VARCHAR(50) COMMENT '등록번호',
    `application_date` VARCHAR(20) COMMENT '출원일',
    `open_date` VARCHAR(20) COMMENT '공개일',
    `register_date` VARCHAR(20) COMMENT '등록일',
    `applicant` TEXT COMMENT '출원인',
    `abstract` MEDIUMTEXT COMMENT '초록',
    `claim_pub` LONGTEXT COMMENT '공개 청구항 텍스트',
    `claim_regit` LONGTEXT COMMENT '등록 청구항 텍스트',
    `chunk_ids` TEXT COMMENT 'ChromaDB 청크 ID 목록 (JSON 배열)',
    `claim_groups` MEDIUMTEXT COMMENT '청구항 그룹 정보'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Pre-filter용 키워드 (약 1000만건)
-- 쿼리 키워드와 매칭하여 후보 특허 필터링
CREATE TABLE IF NOT EXISTS `claim_keywords` (
    `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
    `patent_id` VARCHAR(50) NOT NULL COMMENT '출원번호 (patents.apply_num 참조)',
    `chunk_id` VARCHAR(100) NOT NULL COMMENT '청구항 청크 ID (patent_id_claim_N)',
    `keyword` VARCHAR(200) NOT NULL COMMENT '키워드',
    INDEX `idx_patent_id` (`patent_id`),
    INDEX `idx_chunk_id` (`chunk_id`),
    INDEX `idx_keyword` (`keyword`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- sLLM용 구성요소 (약 26만건)
-- 청구항별 추출된 구성요소 목록
CREATE TABLE IF NOT EXISTS `claim_components` (
    `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
    `patent_id` VARCHAR(50) NOT NULL COMMENT '출원번호 (patents.apply_num 참조)',
    `chunk_id` VARCHAR(100) NOT NULL UNIQUE COMMENT '청구항 청크 ID (patent_id_claim_N)',
    `components` TEXT NOT NULL COMMENT '추출된 구성요소 목록',
    `note` VARCHAR(100) COMMENT '참조한 종속항 번호 (dep 2,3,4)',
    INDEX `idx_patent_id` (`patent_id`),
    INDEX `idx_chunk_id` (`chunk_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================
-- 2. 디자인 특허 테이블
-- ============================================

CREATE TABLE IF NOT EXISTS `design_patents` (
    `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
    `register_num` VARCHAR(50) NOT NULL UNIQUE COMMENT '등록번호',
    `title` VARCHAR(500) NOT NULL COMMENT '디자인명',
    `locarno_class` VARCHAR(20) COMMENT '로카르노 분류',
    `applicant` VARCHAR(255) COMMENT '출원인',
    `image_url` VARCHAR(1000) COMMENT '이미지 URL',
    `filing_date` DATE COMMENT '출원일',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_locarno_class` (`locarno_class`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================
-- 3. 서비스 테이블 (사용자/채팅/분석)
-- ============================================

-- 사용자
CREATE TABLE IF NOT EXISTS `users` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `email` VARCHAR(255) NOT NULL UNIQUE,
    `password` VARCHAR(255) NOT NULL,
    `name` VARCHAR(100) NOT NULL,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 채팅방
CREATE TABLE IF NOT EXISTS `chats` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT NOT NULL,
    `title` VARCHAR(255),
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_user_id` (`user_id`),
    FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 메시지
CREATE TABLE IF NOT EXISTS `messages` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `chat_id` INT NOT NULL,
    `role` ENUM('user', 'assistant') NOT NULL,
    `content` TEXT NOT NULL,
    `message_type` ENUM('text', 'image') DEFAULT 'text',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_chat_id` (`chat_id`),
    FOREIGN KEY (`chat_id`) REFERENCES `chats`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 분석 결과
CREATE TABLE IF NOT EXISTS `analyses` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `message_id` INT NOT NULL UNIQUE,
    `input_type` ENUM('text', 'image') NOT NULL,
    `risk_level` ENUM('high', 'medium', 'low'),
    `result_json` JSON,
    `model_used` VARCHAR(100),
    `processing_time_ms` INT,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (`message_id`) REFERENCES `messages`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 분석 이미지
CREATE TABLE IF NOT EXISTS `analysis_images` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `analysis_id` INT NOT NULL,
    `file_path` VARCHAR(500) NOT NULL,
    `file_name` VARCHAR(255) NOT NULL,
    `locarno_class` VARCHAR(20),
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (`analysis_id`) REFERENCES `analyses`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 분석 키워드
CREATE TABLE IF NOT EXISTS `analysis_keywords` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `analysis_id` INT NOT NULL,
    `keyword` VARCHAR(255) NOT NULL,
    `importance` FLOAT,
    FOREIGN KEY (`analysis_id`) REFERENCES `analyses`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 이미지 매칭 결과
CREATE TABLE IF NOT EXISTS `image_matches` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `analysis_id` INT NOT NULL,
    `design_patent_id` BIGINT,
    `rag_score` FLOAT,
    `model_score` FLOAT,
    `is_similar` BOOLEAN,
    `rank` INT,
    FOREIGN KEY (`analysis_id`) REFERENCES `analyses`(`id`) ON DELETE CASCADE,
    FOREIGN KEY (`design_patent_id`) REFERENCES `design_patents`(`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 청구항 매칭 결과 (chunk_id 기반)
CREATE TABLE IF NOT EXISTS `claim_matches` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `analysis_id` INT NOT NULL,
    `chunk_id` VARCHAR(100) COMMENT '매칭된 청구항 청크 ID',
    `patent_id` VARCHAR(50) COMMENT '출원번호 (patents.apply_num 참조)',
    `rag_score` FLOAT,
    `rerank_score` FLOAT,
    `match_result` ENUM('match', 'no_match', 'uncertain'),
    `rank` INT,
    FOREIGN KEY (`analysis_id`) REFERENCES `analyses`(`id`) ON DELETE CASCADE,
    INDEX `idx_chunk_id` (`chunk_id`),
    INDEX `idx_patent_id` (`patent_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET FOREIGN_KEY_CHECKS = 1;

-- ============================================
-- 데이터 연결 관계 (논리적 참조, FK 제약 없음)
-- ============================================
--
-- patents.apply_num ←── claim_keywords.patent_id
--                   ←── claim_components.patent_id
--                   ←── claim_matches.patent_id
--
-- claim_keywords.chunk_id ←→ claim_components.chunk_id
--                         ←→ ChromaDB 벡터 ID
--
-- RAG 파이프라인:
-- 1. 쿼리 → claim_keywords에서 keyword 매칭 → patent_id 목록 (Pre-filter)
-- 2. ChromaDB에서 chunk_id로 유사 청구항 검색 (Dense + BM25)
-- 3. chunk_id → claim_components에서 구성요소 조회
-- 4. patent_id → patents에서 메타데이터 조회
-- 5. sLLM으로 침해 여부 판단
