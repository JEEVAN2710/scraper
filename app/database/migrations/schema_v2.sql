-- =============================================================================
-- Financial AI Assistant V2 - Relational Database Schema Extensions
-- Database: financial_ai
-- Engine: InnoDB, Charset: utf8mb4, Collation: utf8mb4_unicode_ci
-- =============================================================================

USE `financial_ai`;

-- 1. Company Sources Table (V2 Feature: Track multi-source document origins)
CREATE TABLE IF NOT EXISTS `company_sources` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `company_id` INT NOT NULL,
    `source_type` ENUM('screener', 'company_website', 'investor_relations', 'bse', 'nse', 'custom_url') NOT NULL,
    `source_url` VARCHAR(1000) NOT NULL,
    `is_active` BOOLEAN DEFAULT TRUE,
    `config_json` JSON NULL,
    `last_polled_at` TIMESTAMP NULL,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_company_sources_company_id` (`company_id`),
    INDEX `idx_company_sources_type` (`source_type`),
    CONSTRAINT `fk_company_sources_company` FOREIGN KEY (`company_id`)
        REFERENCES `companies` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. Automations Table (V2 Feature: Scheduled & Recurring Pipelines)
CREATE TABLE IF NOT EXISTS `automations` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `company_id` INT NOT NULL,
    `source_id` INT NULL,
    `name` VARCHAR(255) NOT NULL,
    `schedule_type` ENUM('manual', 'interval', 'cron') DEFAULT 'manual',
    `schedule_expression` VARCHAR(100) NULL,
    `is_active` BOOLEAN DEFAULT TRUE,
    `max_retries` INT DEFAULT 3,
    `last_run_at` TIMESTAMP NULL,
    `next_run_at` TIMESTAMP NULL,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_automations_company_id` (`company_id`),
    INDEX `idx_automations_active_next` (`is_active`, `next_run_at`),
    CONSTRAINT `fk_automations_company` FOREIGN KEY (`company_id`)
        REFERENCES `companies` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_automations_source` FOREIGN KEY (`source_id`)
        REFERENCES `company_sources` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. Automation Runs Table (V2 Feature: Job Execution History & Metrics)
CREATE TABLE IF NOT EXISTS `automation_runs` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `automation_id` INT NOT NULL,
    `trigger_type` ENUM('manual', 'scheduled', 'retry', 'extension') DEFAULT 'manual',
    `status` ENUM('pending', 'running', 'completed', 'failed', 'cancelled') DEFAULT 'pending',
    `documents_discovered` INT DEFAULT 0,
    `documents_downloaded` INT DEFAULT 0,
    `documents_processed` INT DEFAULT 0,
    `error_message` TEXT NULL,
    `started_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    `completed_at` TIMESTAMP NULL,
    INDEX `idx_automation_runs_automation_id` (`automation_id`),
    INDEX `idx_automation_runs_status` (`status`),
    CONSTRAINT `fk_automation_runs_automation` FOREIGN KEY (`automation_id`)
        REFERENCES `automations` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4. Extraction Runs Table (V2 Feature: LLM Extraction Audit Trails)
CREATE TABLE IF NOT EXISTS `extraction_runs` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `document_id` INT NOT NULL,
    `model_name` VARCHAR(100) NOT NULL,
    `prompt_tokens` INT NULL,
    `completion_tokens` INT NULL,
    `raw_response` MEDIUMTEXT NOT NULL,
    `is_valid` BOOLEAN DEFAULT FALSE,
    `validation_errors` TEXT NULL,
    `duration_seconds` FLOAT NULL,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_extraction_runs_document_id` (`document_id`),
    CONSTRAINT `fk_extraction_runs_document` FOREIGN KEY (`document_id`)
        REFERENCES `documents` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5. Financial Metrics View (V2 Feature: Backward-compatible alias for financial_data)
CREATE OR REPLACE VIEW `financial_metrics` AS SELECT * FROM `financial_data`;

-- 6. Operational Metrics Table (V2 Feature: Flexible workspace & sector KPI matrix)
CREATE TABLE IF NOT EXISTS `operational_metrics` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `company_id` INT NOT NULL,
    `document_id` INT NULL,
    `period` VARCHAR(50) NOT NULL,
    `metric_category` VARCHAR(100) NOT NULL,
    `metric_name` VARCHAR(150) NOT NULL,
    `metric_value` VARCHAR(100) NOT NULL,
    `numeric_value` DECIMAL(20, 4) NULL,
    `unit` VARCHAR(50) NULL,
    `source_page` INT NULL,
    `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX `idx_op_company_period` (`company_id`, `period`),
    INDEX `idx_op_metric_name` (`metric_name`),
    CONSTRAINT `fk_op_metrics_company` FOREIGN KEY (`company_id`)
        REFERENCES `companies` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

