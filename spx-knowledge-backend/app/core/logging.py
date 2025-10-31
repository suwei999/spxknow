"""
Logging Configuration
"""

import logging
import sys
import json
import re
from pathlib import Path
from typing import Optional, Any, Mapping

from app.config.settings import settings


class VectorFieldFilter(logging.Filter):
    """
    屏蔽日志中的向量大字段，避免输出巨型数组导致刷屏。
    会将以下键名的值替换为占位符：content_vector, image_vector, embedding, vector。
    """

    SENSITIVE_KEYS = {"content_vector", "image_vector", "embedding", "vector"}

    def _redact_obj(self, obj: Any):
        try:
            if isinstance(obj, Mapping):
                redacted = {}
                for k, v in obj.items():
                    if k in self.SENSITIVE_KEYS:
                        dim = None
                        if isinstance(v, (list, tuple)):
                            dim = len(v)
                        elif isinstance(v, Mapping):
                            dim = v.get("dimension")
                        redacted[k] = f"<vector dim={dim if dim is not None else '?'}>"
                    else:
                        redacted[k] = self._redact_obj(v)
                return redacted
            if isinstance(obj, (list, tuple)) and len(obj) > 16 and all(
                isinstance(x, (int, float)) for x in obj[:16]
            ):
                return f"<vector dim={len(obj)}>"
            return obj
        except Exception:
            return obj

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, Mapping):
                record.msg = self._redact_obj(record.msg)
            if isinstance(record.args, tuple) and record.args:
                record.args = tuple(self._redact_obj(a) for a in record.args)
            if isinstance(record.msg, str):
                msg = record.msg
                # 尝试 JSON 方式脱敏
                if ("content_vector" in msg) or ("image_vector" in msg) or ("embedding" in msg) or (" vector" in msg):
                    try:
                        data = json.loads(msg)
                        data = self._redact_obj(data)
                        record.msg = json.dumps(data, ensure_ascii=False)
                    except Exception:
                        # 非严格JSON：使用正则替换大数组
                        pattern = re.compile(r'"(content_vector|image_vector|embedding|vector)"\s*:\s*\[(?:[^\]]|\n)*\]')
                        record.msg = pattern.sub(r'"\1": "<vector>"', msg)
        except Exception:
            pass
        return True


def _tune_external_loggers():
    # 降低第三方库噪音，防止请求/响应体（含向量）被打印
    for name in (
        "opensearchpy",
        "opensearch",
        "urllib3",
        "httpx",
        "elastic_transport",
    ):
        try:
            logging.getLogger(name).setLevel(logging.WARNING)
        except Exception:
            pass


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
    
    # 屏蔽向量字段日志
    root_logger.addFilter(VectorFieldFilter())

    # 配置第三方库的日志级别
    logging.getLogger('uvicorn').setLevel(logging.INFO)
    logging.getLogger('uvicorn.access').setLevel(logging.WARNING)
    logging.getLogger('fastapi').setLevel(logging.INFO)
    logging.getLogger('sqlalchemy').setLevel(logging.WARNING)
    logging.getLogger('opensearch').setLevel(logging.WARNING)
    logging.getLogger('minio').setLevel(logging.WARNING)
    logging.getLogger('celery').setLevel(logging.INFO)

    # 进一步降低底层依赖的详细日志
    _tune_external_loggers()


# 初始化日志
setup_logging()

# 创建全局日志记录器
logger = logging.getLogger('spx-knowledge-backend')

