-- =============================================================================
-- Financial AI Assistant - Relational Database Schema
-- Database: financial_ai
-- Engine: InnoDB, Charset: utf8mb4, Collation: utf8mb4_unicode_ci
-- =============================================================================

-- Database Initialization
CREATE DATABASE IF NOT EXISTS `financial_ai` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `financial_ai`;

-- 1. Companies Table
CREATE TABLE IF NOT EXISTS `companies` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `name` VARCHAR(255) NOT NULL,
    `ticker` VARCHAR(50) NULL,
    `website` VARCHAR(500) NULL,
    `about` TEXT NULL,
    `sector` VARCHAR(255) NULL,
    `ratios_json` JSON NULL,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY `uk_companies_ticker` (`ticker`),
    INDEX `idx_companies_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. Documents Table
CREATE TABLE IF NOT EXISTS `documents` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `company_id` INT NOT NULL,
    `file_name` VARCHAR(500) NOT NULL,
    `file_url` VARCHAR(1000) NULL,
    `local_path` VARCHAR(1000) NOT NULL,
    `file_hash` VARCHAR(64) NOT NULL,
    `document_type` VARCHAR(100) DEFAULT 'annual_report',
    `report_period` VARCHAR(50) NULL,
    `report_date` DATE NULL,
    `downloaded_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `processed_at` TIMESTAMP NULL,
    `processing_status` ENUM('downloaded', 'extracting', 'extracted', 'chunked', 'analyzing', 'processed', 'failed') DEFAULT 'downloaded',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY `uk_documents_file_hash` (`file_hash`),
    INDEX `idx_documents_company_id` (`company_id`),
    INDEX `idx_documents_status` (`processing_status`),
    INDEX `idx_documents_period` (`report_period`),
    CONSTRAINT `fk_documents_company` FOREIGN KEY (`company_id`)
        REFERENCES `companies` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. Financial Data Table
CREATE TABLE IF NOT EXISTS `financial_data` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `document_id` INT NOT NULL,
    `company_id` INT NOT NULL,
    `period` VARCHAR(50) NULL,
    `revenue` DECIMAL(20, 4) NULL,
    `revenue_growth` DECIMAL(10, 4) NULL,
    `net_profit` DECIMAL(20, 4) NULL,
    `profit_growth` DECIMAL(10, 4) NULL,
    `operating_profit` DECIMAL(20, 4) NULL,
    `operating_margin` DECIMAL(10, 4) NULL,
    `eps` DECIMAL(10, 4) NULL,
    `total_assets` DECIMAL(20, 4) NULL,
    `total_liabilities` DECIMAL(20, 4) NULL,
    `cash_flow` DECIMAL(20, 4) NULL,
    `currency` VARCHAR(10) DEFAULT 'USD',
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_financial_data_company_id` (`company_id`),
    INDEX `idx_financial_data_document_id` (`document_id`),
    INDEX `idx_financial_data_period` (`period`),
    CONSTRAINT `fk_financial_data_document` FOREIGN KEY (`document_id`)
        REFERENCES `documents` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_financial_data_company` FOREIGN KEY (`company_id`)
        REFERENCES `companies` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4. Risk Factors Table
CREATE TABLE IF NOT EXISTS `risk_factors` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `document_id` INT NOT NULL,
    `company_id` INT NOT NULL,
    `risk` VARCHAR(255) NOT NULL,
    `description` TEXT NULL,
    `page_number` INT NULL,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_risk_factors_document_id` (`document_id`),
    INDEX `idx_risk_factors_company_id` (`company_id`),
    CONSTRAINT `fk_risk_factors_document` FOREIGN KEY (`document_id`)
        REFERENCES `documents` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_risk_factors_company` FOREIGN KEY (`company_id`)
        REFERENCES `companies` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5. Document Chunks Table
CREATE TABLE IF NOT EXISTS `document_chunks` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `document_id` INT NOT NULL,
    `chunk_index` INT NOT NULL,
    `page_start` INT NOT NULL,
    `page_end` INT NOT NULL,
    `content` MEDIUMTEXT NOT NULL,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_document_chunks_document_id` (`document_id`),
    INDEX `idx_document_chunks_index` (`document_id`, `chunk_index`),
    CONSTRAINT `fk_document_chunks_document` FOREIGN KEY (`document_id`)
        REFERENCES `documents` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 6. Processing Logs Table
CREATE TABLE IF NOT EXISTS `processing_logs` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `document_id` INT NULL,
    `stage` VARCHAR(100) NOT NULL,
    `status` ENUM('started', 'success', 'warning', 'failed') NOT NULL,
    `message` TEXT NULL,
    `error_details` MEDIUMTEXT NULL,
    `started_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `completed_at` TIMESTAMP NULL,
    INDEX `idx_processing_logs_document_id` (`document_id`),
    INDEX `idx_processing_logs_stage_status` (`stage`, `status`),
    CONSTRAINT `fk_processing_logs_document` FOREIGN KEY (`document_id`)
        REFERENCES `documents` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
