"""
FastAPI Application Entry Point
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.api.v1.router import api_router
from app.api.v1.routes import websocket as ws_routes
from app.core.exceptions import setup_exception_handlers
from app.core.logging import logger
from app.config.settings import settings
from app.middleware.logging import logging_middleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理 - 启动时检查中间件连接"""
    # 启动时检查
    logger.info("正在检查中间件连接...")
    logger.info(f"配置文件位置: {settings.HOST}:{settings.PORT}")
    
    # 检查 MySQL
    try:
        logger.info(f"连接 MySQL: {settings.DATABASE_URL.replace(settings.MYSQL_PASSWORD, '***')}")
        from app.config.database import engine
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        logger.info("✅ MySQL 连接正常")
    except Exception as e:
        logger.error(f"❌ MySQL 连接失败: {e}")
    
    # 检查 Redis
    try:
        logger.info(f"连接 Redis: {settings.REDIS_URL}")
        from app.config.redis import redis_client
        redis_client.ping()
        logger.info("✅ Redis 连接正常")
    except Exception as e:
        logger.error(f"❌ Redis 连接失败: {e}")
    
    # 检查 MinIO
    try:
        logger.info(f"连接 MinIO: {settings.MINIO_ENDPOINT} (用户: {settings.MINIO_ROOT_USER})")
        from app.config.minio import minio_client
        minio_client.list_buckets()
        logger.info("✅ MinIO 连接正常")
    except Exception as e:
        logger.error(f"❌ MinIO 连接失败: {e}")
    
    # 检查 OpenSearch
    try:
        logger.info(f"连接 OpenSearch: {settings.OPENSEARCH_URL} (SSL: {settings.OPENSEARCH_USE_SSL})")
        from app.config.opensearch import opensearch_client
        opensearch_client.cluster.health()
        logger.info("✅ OpenSearch 连接正常")
    except Exception as e:
        logger.error(f"❌ OpenSearch 连接失败: {e}")
    
    logger.info("🚀 服务器启动完成")
    yield
    logger.info("👋 服务器关闭")


app = FastAPI(
    title="SPX Knowledge Base API",
    description="知识库系统后端API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
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

# 请求日志中间件（记录每个请求的开始、结束、状态码与耗时）
app.middleware("http")(logging_middleware)

# 注册API路由 - 按照设计文档要求使用 /api 前缀
app.include_router(api_router, prefix="/api")

# 兼容前端 WebSocket 直接连接 /ws/... 的路径（不走 /api 前缀）
app.include_router(ws_routes.router, prefix="/ws")

# 设置异常处理器
setup_exception_handlers(app)

@app.get("/")
async def root():
    """根路径"""
    return {"message": "SPX Knowledge Base API", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    """健康检查 - 检查所有中间件连接状态"""
    health_status = {
        "status": "healthy",
        "version": "1.0.0",
        "services": {}
    }
    
    # 检查 MySQL
    try:
        from app.config.database import engine
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        health_status["services"]["mysql"] = {"status": "healthy"}
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["services"]["mysql"] = {"status": "error", "message": str(e)}
    
    # 检查 Redis
    try:
        from app.config.redis import redis_client
        redis_client.ping()
        health_status["services"]["redis"] = {"status": "healthy"}
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["services"]["redis"] = {"status": "error", "message": str(e)}
    
    # 检查 MinIO
    try:
        from app.config.minio import minio_client
        minio_client.list_buckets()
        health_status["services"]["minio"] = {"status": "healthy"}
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["services"]["minio"] = {"status": "error", "message": str(e)}
    
    # 检查 OpenSearch
    try:
        from app.config.opensearch import opensearch_client
        opensearch_client.cluster.health()
        health_status["services"]["opensearch"] = {"status": "healthy"}
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["services"]["opensearch"] = {"status": "error", "message": str(e)}
    
    return health_status
