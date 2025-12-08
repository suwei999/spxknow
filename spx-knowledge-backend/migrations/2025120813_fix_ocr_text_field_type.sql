-- ============================================
-- 修复 document_images 表 ocr_text 字段类型
-- 问题：TEXT 类型最大只能存储 65,535 字节，OCR 文本可能超过此限制
-- 解决方案：将 ocr_text 字段改为 MEDIUMTEXT（最大 16MB）
-- ============================================

ALTER TABLE `document_images` 
MODIFY COLUMN `ocr_text` MEDIUMTEXT COMMENT 'OCR识别文本';

