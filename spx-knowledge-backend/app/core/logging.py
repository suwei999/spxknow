"""
Logging Configuration
"""

import logging
import sys
from pathlib import Path
from typing import Optional

from app.config.settings import settings


def setup_logging(
    log_level: Optional[str] = None,
    log_file: Optional[str] = None,
    log_format: Optional[str] = None
):
    """
    配置日志系统
    
    Args:
        log_level: 日志级别（DEBUG, INFO, WARNING, ERROR, CRITICAL）
        log_file: 日志文件路径
        log_format: 日志格式
    """
    # 使用配置或默认值
    level = log_level or settings.LOG_LEVEL
    log_path = log_file or settings.LOG_FILE
    fmt = log_format or settings.LOG_FORMAT
    
    # 转换日志级别
    level_map = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL
    }
    numeric_level = level_map.get(level.upper(), logging.INFO)
    
    # 配置根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # 清除现有的处理器
    root_logger.handlers = []
    
    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_formatter = logging.Formatter(fmt)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # 文件处理器
    if log_path:
        try:
            log_file_path = Path(log_path)
            log_file_path.parent.mkdir(parents=True, exist_ok=True)
            
            file_handler = logging.FileHandler(log_path, encoding='utf-8')
            file_handler.setLevel(numeric_level)
            file_formatter = logging.Formatter(fmt)
            file_handler.setFormatter(file_formatter)
            root_logger.addHandler(file_handler)
        except Exception as e:
            root_logger.warning(f"无法创建日志文件 {log_path}: {e}")
    
    # 配置第三方库的日志级别
    logging.getLogger('uvicorn').setLevel(logging.INFO)
    logging.getLogger('uvicorn.access').setLevel(logging.WARNING)
    logging.getLogger('fastapi').setLevel(logging.INFO)
    logging.getLogger('sqlalchemy').setLevel(logging.WARNING)
    logging.getLogger('opensearch').setLevel(logging.WARNING)
    logging.getLogger('minio').setLevel(logging.WARNING)
    logging.getLogger('celery').setLevel(logging.INFO)


# 初始化日志
setup_logging()

# 创建全局日志记录器
logger = logging.getLogger('spx-knowledge-backend')

