"""
Authentication Dependencies
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.security import verify_token
from typing import Optional

security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """获取当前用户"""
    token = credentials.credentials
    payload = verify_token(token)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="认证令牌无效",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return payload

def get_optional_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """获取可选用户（用于可选认证）"""
    if not credentials:
        return None
    
    token = credentials.credentials
    payload = verify_token(token)
    return payload
