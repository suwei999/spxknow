-- SPX Knowledge Base MySQL 初始化SQL
-- 创建数据库

CREATE DATABASE IF NOT EXISTS `spx_knowledge` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE `spx_knowledge`;

-- ============================================
-- 1. 知识库分类表
-- ============================================
CREATE TABLE IF NOT EXISTS `knowledge_base_categories` (
    `id` INT NOT NULL AUTO_INCREMENT COMMENT '分类ID',
    `name` VARCHAR(255) NOT NULL COMMENT '分类名称',
    `description` TEXT COMMENT '分类描述',
    `parent_id` INT NULL COMMENT '父分类ID',
    `sort_order` INT DEFAULT 0 COMMENT '排序',
    `is_active` BOOLEAN DEFAULT TRUE COMMENT '是否激活',
    `level` INT DEFAULT 1 COMMENT '分类层级',
    `icon` VARCHAR(100) COMMENT '分类图标',
    `color` VARCHAR(20) COMMENT '分类颜色',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `is_deleted` BOOLEAN DEFAULT FALSE COMMENT '是否删除',
    PRIMARY KEY (`id`),
    INDEX `idx_category_parent_id` (`parent_id`),
    INDEX `idx_category_is_active` (`is_active`),
    CONSTRAINT `fk_category_parent` FOREIGN KEY (`parent_id`) REFERENCES `knowledge_base_categories` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='知识库分类表';

-- ============================================
-- 2. 知识库表
-- ============================================
CREATE TABLE IF NOT EXISTS `knowledge_bases` (
    `id` INT NOT NULL AUTO_INCREMENT COMMENT '知识库ID',
    `name` VARCHAR(255) NOT NULL COMMENT '知识库名称',
    `description` TEXT COMMENT '知识库描述',
    `category_id` INT NULL COMMENT '分类ID',
    `is_active` BOOLEAN DEFAULT TRUE COMMENT '是否激活',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `is_deleted` BOOLEAN DEFAULT FALSE COMMENT '是否删除',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_kb_name` (`name`),
    INDEX `idx_kb_category_id` (`category_id`),
    INDEX `idx_kb_is_active` (`is_active`),
    CONSTRAINT `fk_kb_category` FOREIGN KEY (`category_id`) REFERENCES `knowledge_base_categories` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='知识库表';

-- ============================================
-- 3. 文档表
-- ============================================
CREATE TABLE IF NOT EXISTS `documents` (
    `id` INT NOT NULL AUTO_INCREMENT COMMENT '文档ID',
    `original_filename` VARCHAR(255) NOT NULL COMMENT '原始文件名',
    `file_type` VARCHAR(50) COMMENT '文件类型',
    `file_size` INT COMMENT '文件大小',
    `file_hash` VARCHAR(64) COMMENT '文件哈希',
    `file_path` VARCHAR(500) COMMENT '文件路径',
    `knowledge_base_id` INT NOT NULL COMMENT '知识库ID',
    `category_id` INT NULL COMMENT '分类ID',
    `tags` JSON COMMENT '标签列表JSON',
    `metadata` JSON COMMENT '元数据JSON',
    `status` VARCHAR(50) DEFAULT 'uploaded' COMMENT '处理状态',
    `processing_progress` FLOAT DEFAULT 0.0 COMMENT '处理进度',
    `error_message` TEXT COMMENT '错误信息',
    `last_modified_at` DATETIME COMMENT '最后修改时间',
    `modification_count` INT DEFAULT 0 COMMENT '修改次数',
    `last_modified_by` VARCHAR(100) COMMENT '最后修改者',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `is_deleted` BOOLEAN DEFAULT FALSE COMMENT '是否删除',
    PRIMARY KEY (`id`),
    INDEX `idx_doc_knowledge_base_id` (`knowledge_base_id`),
    INDEX `idx_doc_category_id` (`category_id`),
    INDEX `idx_doc_status` (`status`),
    INDEX `idx_doc_file_hash` (`file_hash`),
    CONSTRAINT `fk_doc_kb` FOREIGN KEY (`knowledge_base_id`) REFERENCES `knowledge_bases` (`id`) ON DELETE RESTRICT,
    CONSTRAINT `fk_doc_category` FOREIGN KEY (`category_id`) REFERENCES `knowledge_base_categories` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='文档表';

-- ============================================
-- 4. 文档分块表
-- ============================================
CREATE TABLE IF NOT EXISTS `document_chunks` (
    `id` INT NOT NULL AUTO_INCREMENT COMMENT '分块ID',
    `document_id` INT NOT NULL COMMENT '文档ID',
    `content` TEXT NOT NULL COMMENT '分块内容',
    `chunk_index` INT NOT NULL COMMENT '分块索引',
    `chunk_type` VARCHAR(50) DEFAULT 'text' COMMENT '分块类型',
    `metadata` TEXT COMMENT '元数据JSON',
    `version` INT DEFAULT 1 COMMENT '版本号',
    `last_modified_at` DATETIME COMMENT '最后修改时间',
    `modification_count` INT DEFAULT 0 COMMENT '修改次数',
    `last_modified_by` VARCHAR(100) COMMENT '最后修改者',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `is_deleted` BOOLEAN DEFAULT FALSE COMMENT '是否删除',
    PRIMARY KEY (`id`),
    INDEX `idx_chunk_document_id` (`document_id`),
    INDEX `idx_chunk_index` (`document_id`, `chunk_index`),
    CONSTRAINT `fk_chunk_doc` FOREIGN KEY (`document_id`) REFERENCES `documents` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='文档分块表';

-- ============================================
-- 5. 分块版本表
-- ============================================
CREATE TABLE IF NOT EXISTS `chunk_versions` (
    `id` INT NOT NULL AUTO_INCREMENT COMMENT '版本ID',
    `chunk_id` INT NOT NULL COMMENT '分块ID',
    `version_number` INT NOT NULL COMMENT '版本号',
    `content` TEXT NOT NULL COMMENT '版本内容',
    `metadata` TEXT COMMENT '版本元数据JSON',
    `modified_by` VARCHAR(100) COMMENT '修改者',
    `version_comment` TEXT COMMENT '版本注释',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `is_deleted` BOOLEAN DEFAULT FALSE COMMENT '是否删除',
    PRIMARY KEY (`id`),
    INDEX `idx_chunk_ver_chunk_id` (`chunk_id`),
    INDEX `idx_chunk_ver_version` (`chunk_id`, `version_number`),
    CONSTRAINT `fk_version_chunk` FOREIGN KEY (`chunk_id`) REFERENCES `document_chunks` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='分块版本表';

-- ============================================
-- 6. 文档版本表
-- ============================================
CREATE TABLE IF NOT EXISTS `document_versions` (
    `id` INT NOT NULL AUTO_INCREMENT COMMENT '版本ID',
    `document_id` INT NOT NULL COMMENT '文档ID',
    `version_number` INT NOT NULL COMMENT '版本号',
    `version_type` VARCHAR(50) DEFAULT 'auto' COMMENT '版本类型',
    `description` TEXT COMMENT '版本描述',
    `file_path` VARCHAR(500) NOT NULL COMMENT '文件路径',
    `file_size` INT COMMENT '文件大小',
    `file_hash` VARCHAR(64) COMMENT '文件哈希',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `is_deleted` BOOLEAN DEFAULT FALSE COMMENT '是否删除',
    PRIMARY KEY (`id`),
    INDEX `idx_doc_ver_document_id` (`document_id`),
    INDEX `idx_doc_ver_version` (`document_id`, `version_number`),
    CONSTRAINT `fk_doc_ver_doc` FOREIGN KEY (`document_id`) REFERENCES `documents` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='文档版本表';

-- ============================================
-- 7. 文档图片表
-- ============================================
CREATE TABLE IF NOT EXISTS `document_images` (
    `id` INT NOT NULL AUTO_INCREMENT COMMENT '图片ID',
    `document_id` INT NOT NULL COMMENT '文档ID',
    `image_path` VARCHAR(500) NOT NULL COMMENT '图片路径',
    `thumbnail_path` VARCHAR(500) COMMENT '缩略图路径',
    `image_type` VARCHAR(50) COMMENT '图片类型',
    `file_size` INT COMMENT '图片大小',
    `width` INT COMMENT '宽度',
    `height` INT COMMENT '高度',
    `sha256_hash` VARCHAR(64) COMMENT '图片哈希',
    `ocr_text` TEXT COMMENT 'OCR识别文本',
    `metadata` TEXT COMMENT '元数据JSON',
    `vector_model` VARCHAR(50) COMMENT '向量模型',
    `vector_dim` INT COMMENT '向量维度',
    `status` VARCHAR(50) DEFAULT 'pending' COMMENT '处理状态',
    `error_message` TEXT COMMENT '错误信息',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `is_deleted` BOOLEAN DEFAULT FALSE COMMENT '是否删除',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_image_sha256` (`sha256_hash`),
    INDEX `idx_image_document_id` (`document_id`),
    INDEX `idx_image_status` (`status`),
    CONSTRAINT `fk_image_doc` FOREIGN KEY (`document_id`) REFERENCES `documents` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='文档图片表';

-- ============================================
-- 8. 问答会话表
-- ============================================
CREATE TABLE IF NOT EXISTS `qa_sessions` (
    `id` INT NOT NULL AUTO_INCREMENT COMMENT '会话ID',
    `session_id` VARCHAR(100) NOT NULL UNIQUE COMMENT '会话UUID',
    `session_name` VARCHAR(200) COMMENT '会话名称',
    `knowledge_base_id` INT NOT NULL COMMENT '知识库ID',
    `user_id` VARCHAR(100) COMMENT '用户ID',
    `query_method` VARCHAR(50) DEFAULT 'hybrid' COMMENT '查询方式',
    `search_config` JSON COMMENT '搜索配置JSON',
    `llm_config` JSON COMMENT 'LLM配置JSON',
    `question_count` INT DEFAULT 0 COMMENT '问题数量',
    `last_question` TEXT COMMENT '最后问题',
    `last_activity_time` DATETIME COMMENT '最后活动时间',
    `status` VARCHAR(20) DEFAULT 'active' COMMENT '状态：active/inactive/deleted',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `is_deleted` BOOLEAN DEFAULT FALSE COMMENT '是否删除',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_session_id` (`session_id`),
    INDEX `idx_qa_session_kb_id` (`knowledge_base_id`),
    INDEX `idx_qa_session_user_id` (`user_id`),
    INDEX `idx_qa_session_activity_time` (`last_activity_time`),
    INDEX `idx_qa_session_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='问答会话表';

-- ============================================
-- 9. 问答记录表
-- ============================================
CREATE TABLE IF NOT EXISTS `qa_questions` (
    `id` INT NOT NULL AUTO_INCREMENT COMMENT '记录ID',
    `question_id` VARCHAR(100) NOT NULL UNIQUE COMMENT '问题UUID',
    `session_id` VARCHAR(100) NOT NULL COMMENT '会话ID',
    `question_content` TEXT NOT NULL COMMENT '问题内容',
    `answer_content` TEXT COMMENT '答案内容',
    `source_info` JSON COMMENT '来源信息JSON',
    `processing_info` JSON COMMENT '处理信息JSON',
    `similarity_score` FLOAT COMMENT '相似度分数',
    `answer_quality` VARCHAR(20) COMMENT '答案质量',
    `user_feedback` JSON COMMENT '用户反馈JSON',
    `input_type` VARCHAR(50) DEFAULT 'text' COMMENT '输入类型：text/image/multimodal',
    `processing_time` FLOAT COMMENT '处理时间（秒）',
    `token_usage` INT COMMENT 'Token使用量',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `is_deleted` BOOLEAN DEFAULT FALSE COMMENT '是否删除',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_question_id` (`question_id`),
    INDEX `idx_qa_question_session_id` (`session_id`),
    INDEX `idx_qa_question_similarity` (`similarity_score`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='问答记录表';

-- ============================================
-- 10. 问答统计表
-- ============================================
CREATE TABLE IF NOT EXISTS `qa_statistics` (
    `id` INT NOT NULL AUTO_INCREMENT COMMENT '统计ID',
    `knowledge_base_id` INT NOT NULL COMMENT '知识库ID',
    `date` DATETIME NOT NULL COMMENT '统计日期',
    `total_questions` INT DEFAULT 0 COMMENT '总问题数',
    `answered_questions` INT DEFAULT 0 COMMENT '已回答数',
    `unanswered_questions` INT DEFAULT 0 COMMENT '未回答数',
    `avg_similarity_score` FLOAT COMMENT '平均相似度分数',
    `avg_response_time` FLOAT COMMENT '平均响应时间',
    `hot_questions` JSON COMMENT '热门问题JSON',
    `query_method_stats` JSON COMMENT '查询方式统计JSON',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `is_deleted` BOOLEAN DEFAULT FALSE COMMENT '是否删除',
    PRIMARY KEY (`id`),
    INDEX `idx_qa_stats_kb_id` (`knowledge_base_id`),
    INDEX `idx_qa_stats_date` (`date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='问答统计表';

-- ============================================
-- 11. Celery任务表
-- ============================================
CREATE TABLE IF NOT EXISTS `celery_tasks` (
    `id` INT NOT NULL AUTO_INCREMENT COMMENT '任务ID',
    `task_id` VARCHAR(100) NOT NULL UNIQUE COMMENT 'Celery任务ID',
    `task_name` VARCHAR(100) NOT NULL COMMENT '任务名称',
    `status` VARCHAR(50) DEFAULT 'pending' COMMENT '任务状态',
    `progress` FLOAT DEFAULT 0.0 COMMENT '任务进度',
    `result` TEXT COMMENT '任务结果',
    `error_message` TEXT COMMENT '错误信息',
    `started_at` DATETIME COMMENT '开始时间',
    `completed_at` DATETIME COMMENT '完成时间',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `is_deleted` BOOLEAN DEFAULT FALSE COMMENT '是否删除',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_task_id` (`task_id`),
    INDEX `idx_celery_task_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Celery任务表';

-- ============================================
-- 12. 系统配置表
-- ============================================
CREATE TABLE IF NOT EXISTS `system_configs` (
    `id` INT NOT NULL AUTO_INCREMENT COMMENT '配置ID',
    `key` VARCHAR(100) NOT NULL UNIQUE COMMENT '配置键',
    `value` TEXT COMMENT '配置值',
    `description` TEXT COMMENT '配置描述',
    `config_type` VARCHAR(50) DEFAULT 'string' COMMENT '配置类型',
    `is_active` BOOLEAN DEFAULT TRUE COMMENT '是否激活',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `is_deleted` BOOLEAN DEFAULT FALSE COMMENT '是否删除',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_config_key` (`key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='系统配置表';

-- ============================================
-- 13. 操作日志表
-- ============================================
CREATE TABLE IF NOT EXISTS `operation_logs` (
    `id` INT NOT NULL AUTO_INCREMENT COMMENT '日志ID',
    `operation_type` VARCHAR(50) NOT NULL COMMENT '操作类型',
    `operation_description` TEXT COMMENT '操作描述',
    `user_id` INT COMMENT '用户ID',
    `resource_type` VARCHAR(50) COMMENT '资源类型',
    `resource_id` INT COMMENT '资源ID',
    `ip_address` VARCHAR(50) COMMENT 'IP地址',
    `user_agent` TEXT COMMENT '用户代理',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `is_deleted` BOOLEAN DEFAULT FALSE COMMENT '是否删除',
    PRIMARY KEY (`id`),
    INDEX `idx_op_log_user_id` (`user_id`),
    INDEX `idx_op_log_type` (`operation_type`),
    INDEX `idx_op_log_resource` (`resource_type`, `resource_id`),
    INDEX `idx_op_log_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='操作日志表';

-- ============================================
-- 初始化完成
-- ============================================
SELECT 'SPX Knowledge Base 数据库初始化完成！' AS message;
