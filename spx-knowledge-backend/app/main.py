"""
FastAPI Application Entry Point
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.api.v1.router import api_router
from app.core.exceptions import setup_exception_handlers
from app.core.config import settings

app = FastAPI(
    title="SPX Knowledge Base API",
    description="知识库系统后端API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_HOSTS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 添加受信任主机中间件
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.ALLOWED_HOSTS,
)

# 注册API路由 - 按照设计文档要求使用 /api 前缀
app.include_router(api_router, prefix="/api")

# 设置异常处理器
setup_exception_handlers(app)

@app.get("/")
async def root():
    """根路径"""
    return {"message": "SPX Knowledge Base API", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy", "version": "1.0.0"}
