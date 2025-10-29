"""
API Router Configuration
"""

from fastapi import APIRouter
from app.api.v1.routes import (
    # 放在前面，避免与 /knowledge-bases/{kb_id} 路由冲突
    knowledge_base_categories,
    knowledge_base_tags,
    # 其他模块
    knowledge_bases,
    documents,
    chunks,
    images,
    qa,
    search,
    versions,
    document_modification,
    image_vectorization,
    document_recommendation,
    document_status,
    websocket,
)

api_router = APIRouter()

# 注册各个模块的路由
api_router.include_router(
    documents.router,
    prefix="/documents",
    tags=["文档管理"]
)

api_router.include_router(
    document_modification.router,
    prefix="/documents",
    tags=["文档修改"]
)

api_router.include_router(
    chunks.router,
    prefix="/chunks",
    tags=["文档分块"]
)

api_router.include_router(
    images.router,
    prefix="/images",
    tags=["图片管理"]
)

api_router.include_router(
    qa.router,
    prefix="/qa",
    tags=["智能问答"]
)

api_router.include_router(
    search.router,
    prefix="/search",
    tags=["搜索功能"]
)

api_router.include_router(
    versions.router,
    prefix="/versions",
    tags=["版本管理"]
)

api_router.include_router(
    image_vectorization.router,
    prefix="/image-vectorization",
    tags=["图片向量化"]
)

api_router.include_router(
    knowledge_base_categories.router,
    prefix="/knowledge-bases",
    tags=["知识库分类"]
)

api_router.include_router(
    knowledge_base_tags.router,
    prefix="/knowledge-bases",
    tags=["知识库标签"]
)

api_router.include_router(
    knowledge_bases.router,
    prefix="/knowledge-bases",
    tags=["知识库管理"]
)

api_router.include_router(
    document_recommendation.router,
    prefix="/api",
    tags=["智能推荐"]
)

api_router.include_router(
    document_status.router,
    prefix="/api",
    tags=["文档状态"]
)

api_router.include_router(
    websocket.router,
    prefix="/ws",
    tags=["WebSocket通知"]
)
