"""
File Validation Service
根据文档处理流程设计实现文件验证和安全扫描功能
"""

import hashlib
import os
import filetype
from typing import Dict, Any, Optional, List
from datetime import datetime
from fastapi import UploadFile
from app.core.logging import logger
from app.config.settings import settings
from app.core.exceptions import CustomException, ErrorCode
from app.services.clamav_service import ClamAVService

class FileValidationService:
    """文件验证服务 - 严格按照设计文档实现"""
    
    # 设计文档要求的支持格式
    SUPPORTED_FORMATS = {
        'application/pdf': 'PDF',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'DOCX',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'PPTX',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'XLSX',
        'text/plain': 'TXT',
        'text/markdown': 'MD',
        'text/html': 'HTML',
        'text/csv': 'CSV',
        'application/json': 'JSON',
        'application/xml': 'XML',
        'text/xml': 'XML'
    }
    
    # 设计文档要求的文件大小限制
    MAX_FILE_SIZE = settings.MAX_FILE_SIZE
    
    def __init__(self):
        self.clamav = ClamAVService()  # 初始化ClamAV服务
    
    def validate_file_format(self, file: UploadFile) -> Dict[str, Any]:
        """文件格式验证 - 根据设计文档实现"""
        try:
            logger.info(f"开始验证文件格式: {file.filename}")
            
            # 检查文件扩展名
            file_extension = os.path.splitext(file.filename)[1].lower()
            logger.debug(f"文件扩展名: {file_extension}")
            
            # 检查MIME类型
            if file.content_type not in self.SUPPORTED_FORMATS:
                logger.error(f"不支持的文件格式: {file.content_type}")
                raise CustomException(
                    code=ErrorCode.VALIDATION_ERROR,
                    message=f"不支持的文件格式: {file.content_type}。支持的格式: {', '.join(self.SUPPORTED_FORMATS.values())}"
                )
            
            # 验证文件头魔数（防止文件扩展名伪造）
            file_content = file.file.read(settings.FILE_HEADER_READ_SIZE)  # 读取前N字节
            file.file.seek(0)  # 重置文件指针
            
            # 使用 filetype 检测真实文件类型
            kind = filetype.guess(file_content)
            detected_mime = kind.mime if kind else file.content_type
            logger.debug(f"检测到的MIME类型: {detected_mime}")
            
            # 兼容 OOXML 容器：docx/xlsx/pptx 实际魔数常识别为 application/zip
            if detected_mime == 'application/zip' and file.content_type in (
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                'application/vnd.openxmlformats-officedocument.presentationml.presentation',
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            ):
                detected_mime = file.content_type
            
            if detected_mime not in self.SUPPORTED_FORMATS:
                logger.error(f"文件头魔数验证失败: {detected_mime}")
                raise CustomException(
                    code=ErrorCode.VALIDATION_ERROR,
                    message=f"文件头魔数验证失败，检测到: {detected_mime}"
                )
            
            result = {
                "valid": True,
                "file_type": self.SUPPORTED_FORMATS[file.content_type],
                "mime_type": file.content_type,
                "extension": file_extension,
                "detected_mime": detected_mime
            }
            
            logger.info(f"文件格式验证通过: {file.filename}")
            return result
            
        except CustomException:
            raise
        except Exception as e:
            logger.error(f"文件格式验证错误: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.VALIDATION_ERROR,
                message=f"文件格式验证失败: {str(e)}"
            )
    
    def validate_file_size(self, file: UploadFile) -> Dict[str, Any]:
        """文件大小验证 - 根据设计文档实现"""
        try:
            logger.info(f"开始验证文件大小: {file.filename}")
            
            # 获取文件大小
            file.file.seek(0, 2)  # 移动到文件末尾
            file_size = file.file.tell()
            file.file.seek(0)  # 重置文件指针
            
            logger.debug(f"文件大小: {file_size} bytes")
            
            if file_size > self.MAX_FILE_SIZE:
                logger.error(f"文件过大: {file_size} > {self.MAX_FILE_SIZE}")
                raise CustomException(
                    code=ErrorCode.VALIDATION_ERROR,
                    message=f"文件大小超过限制。当前: {file_size / (1024*1024):.2f}MB，限制: {self.MAX_FILE_SIZE / (1024*1024)}MB"
                )
            
            if file_size == 0:
                logger.error("文件为空")
                raise CustomException(
                    code=ErrorCode.VALIDATION_ERROR,
                    message="文件不能为空"
                )
            
            result = {
                "valid": True,
                "file_size": file_size,
                "file_size_mb": file_size / (1024 * 1024)
            }
            
            logger.info(f"文件大小验证通过: {file_size} bytes")
            return result
            
        except CustomException:
            raise
        except Exception as e:
            logger.error(f"文件大小验证错误: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.VALIDATION_ERROR,
                message=f"文件大小验证失败: {str(e)}"
            )
    
    def scan_file_security(self, file: UploadFile) -> Dict[str, Any]:
        """安全扫描 - 根据设计文档实现ClamAV病毒检测"""
        try:
            logger.info(f"开始安全扫描: {file.filename}")
            
            # 读取文件内容
            file.file.seek(0)
            file_content = file.file.read()
            file.file.seek(0)
            
            # 1. ClamAV病毒扫描（如果启用）
            virus_scan_result = None
            if self.clamav.is_available():
                logger.info("执行ClamAV病毒扫描")
                virus_scan_result = self.clamav.scan_stream(file_content)
                
                # 如果发现病毒，直接返回错误
                if virus_scan_result.get('status') == 'infected':
                    threats = virus_scan_result.get('threats', [])
                    logger.error(f"❌ 发现病毒: {threats}")
                    raise CustomException(
                        code=ErrorCode.VALIDATION_ERROR,
                        message=f"文件包含病毒: {', '.join(threats)}"
                    )
            
            # 2. 恶意脚本检测
            logger.info("执行恶意脚本检测")
            script_scan_result = self._detect_malicious_scripts(file_content, file.content_type)
            
            # 如果发现可疑脚本
            if not script_scan_result.get('safe'):
                keywords = script_scan_result.get('found_keywords', [])
                logger.warning(f"⚠️ 检测到可疑脚本: {keywords}")
                # 不直接拒绝，记录警告
                script_scan_result['severity'] = 'warning'
            
            # 构建结果
            result = {
                "valid": True,
                "virus_scan": virus_scan_result,
                "script_scan": script_scan_result,
                "scan_status": "clean" if script_scan_result.get('safe') else "warning",
                "scan_method": "clamav_and_pattern" if virus_scan_result else "pattern_only",
                "threats_found": []
            }
            
            logger.info(f"✅ 安全扫描通过: {file.filename}")
            return result
            
        except CustomException:
            raise
        except Exception as e:
            logger.error(f"安全扫描错误: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.VALIDATION_ERROR,
                message=f"安全扫描失败: {str(e)}"
            )
    
    def _detect_malicious_scripts(self, content: bytes, content_type: str) -> Dict[str, Any]:
        """检测恶意脚本"""
        found_keywords = []
        content_lower = content.lower()
        
        # 可疑关键字列表
        suspicious_keywords = [
            # JavaScript/Web恶意代码
            b'javascript:', b'eval(', b'exec(', b'atob(',
            b'document.write', b'innerhtml',
            # PowerShell
            b'powershell', b'invoke-expression', b'downloadstring',
            # WScript/VBScript  
            b'wscript.shell', b'creatobject', b'activexobject',
            b'shell.exec', b'shell.run',
            # Office宏
            b'automation', b'shell32', b'wscript',
            # 系统调用
            b'system(', b'cmd.exe', b'/bin/sh', b'/bin/bash',
            # 编码混淆
            b'fromchar', b'unescape', b'decodeuricomponent',
            # SQL注入
            b'union select', b'drop table', b';--'
        ]
        
        for keyword in suspicious_keywords:
            if keyword in content_lower:
                found_keywords.append(keyword.decode('utf-8', errors='ignore'))
        
        return {
            "safe": len(found_keywords) == 0,
            "found_keywords": found_keywords,
            "content_type": content_type
        }
    
    def calculate_file_hash(self, file: UploadFile) -> Dict[str, Any]:
        """计算文件哈希 - 根据设计文档实现MD5/SHA256校验"""
        try:
            logger.info(f"开始计算文件哈希: {file.filename}")
            
            file_content = file.file.read()
            file.file.seek(0)
            
            # 计算MD5哈希
            md5_hash = hashlib.md5(file_content).hexdigest()
            
            # 计算SHA256哈希
            sha256_hash = hashlib.sha256(file_content).hexdigest()
            
            result = {
                "md5_hash": md5_hash,
                "sha256_hash": sha256_hash,
                "file_size": len(file_content)
            }
            
            logger.info(f"文件哈希计算完成: MD5={md5_hash[:8]}..., SHA256={sha256_hash[:8]}...")
            return result
            
        except Exception as e:
            logger.error(f"文件哈希计算错误: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.VALIDATION_ERROR,
                message=f"文件哈希计算失败: {str(e)}"
            )
    
    def validate_file(self, file: UploadFile) -> Dict[str, Any]:
        """完整文件验证 - 根据设计文档实现所有验证步骤"""
        try:
            logger.info(f"开始完整文件验证: {file.filename}")
            
            # 1. 文件格式验证
            format_result = self.validate_file_format(file)
            
            # 2. 文件大小验证
            size_result = self.validate_file_size(file)
            
            # 3. 安全扫描
            security_result = self.scan_file_security(file)
            
            # 4. 文件哈希计算
            hash_result = self.calculate_file_hash(file)
            
            # 综合结果
            result = {
                "valid": True,
                "filename": file.filename,
                "format_validation": format_result,
                "size_validation": size_result,
                "security_scan": security_result,
                "hash_calculation": hash_result,
                "validation_timestamp": datetime.utcnow().isoformat() + "Z"
            }
            
            logger.info(f"文件验证完成: {file.filename}")
            return result
            
        except CustomException:
            raise
        except Exception as e:
            logger.error(f"文件验证错误: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.VALIDATION_ERROR,
                message=f"文件验证失败: {str(e)}"
            )
