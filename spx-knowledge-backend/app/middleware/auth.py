"""
Authentication Middleware
"""

from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from app.core.security import verify_token
from app.config.settings import settings
import logging

logger = logging.getLogger(__name__)

async def auth_middleware(request: Request, call_next):
    """认证中间件"""
    # 跳过认证的路径
    skip_paths = ["/", "/health", "/docs", "/redoc", "/openapi.json"]
    
    if request.url.path in skip_paths:
        return await call_next(request)
    
    # 获取Authorization头
    authorization = request.headers.get("Authorization")
    
    if not authorization:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": "缺少认证令牌"}
        )
    
    # 检查Bearer格式
    if not authorization.startswith("Bearer "):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": "认证令牌格式错误"}
        )
    
    # 提取令牌
    token = authorization.split(" ")[1]
    
    # 验证令牌
    payload = verify_token(token)
    if not payload:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": "认证令牌无效"}
        )
    
    # 将用户信息添加到请求中
    request.state.user = payload
    
    return await call_next(request)
