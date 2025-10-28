"""
Logging Middleware
"""

from fastapi import Request
from fastapi.responses import Response
import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)

async def logging_middleware(request: Request, call_next):
    """日志中间件"""
    start_time = time.time()
    
    # 记录请求开始
    logger.info(f"请求开始: {request.method} {request.url.path}")
    
    # 处理请求
    response = await call_next(request)
    
    # 计算处理时间
    process_time = time.time() - start_time
    
    # 记录请求结束
    logger.info(
        f"请求结束: {request.method} {request.url.path} "
        f"状态码: {response.status_code} 处理时间: {process_time:.3f}s"
    )
    
    # 添加响应头
    response.headers["X-Process-Time"] = str(process_time)
    response.headers["X-Timestamp"] = datetime.now().isoformat()
    
    return response
