"""
Image API Routes
根据文档处理流程设计实现图片搜索API接口
"""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from typing import List, Optional
from app.schemas.image import ImageResponse, ImageSearchRequest, ImageSearchResponse
from app.services.image_service import ImageService
from app.services.image_search_service import ImageSearchService
from app.dependencies.database import get_db
from sqlalchemy.orm import Session
from app.core.logging import logger
from app.config.settings import settings

router = APIRouter()

@router.get("/", response_model=List[ImageResponse])
async def get_images(
    skip: int = 0,
    limit: int = 100,
    document_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """获取图片列表"""
    try:
        logger.info(f"API请求: 获取图片列表，跳过: {skip}, 限制: {limit}, 文档ID: {document_id}")
        
        service = ImageService(db)
        images = await service.get_images(
            skip=skip, 
            limit=limit, 
            document_id=document_id
        )
        
        logger.info(f"API响应: 返回 {len(images)} 张图片")
        return images
        
    except Exception as e:
        logger.error(f"获取图片列表API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取图片列表失败: {str(e)}"
        )

@router.post("/upload")
async def upload_image(
    file: UploadFile = File(...),
    document_id: int = None,
    db: Session = Depends(get_db)
):
    """上传图片"""
    try:
        logger.info(f"API请求: 上传图片 {file.filename}, 文档ID: {document_id}")
        
        if not document_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="文档ID不能为空"
            )
        
        service = ImageService(db)
        image = await service.upload_image(file, document_id)
        
        logger.info(f"API响应: 图片上传成功，图片ID: {image.id}")
        return image
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"上传图片API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"上传图片失败: {str(e)}"
        )

# 根据设计文档要求的图片搜索API接口

@router.post("/search-by-image", response_model=List[ImageSearchResponse])
async def search_by_image(
    file: UploadFile = File(...),
    similarity_threshold: float = settings.QA_DEFAULT_SIMILARITY_THRESHOLD,
    limit: int = 10,
    knowledge_base_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """以图找图搜索 - 根据设计文档实现（已迁移到QA模块）"""
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="此API已迁移到 /api/qa/sessions/{session_id}/image-search，请使用新的API端点"
    )

@router.post("/search-by-text", response_model=List[ImageSearchResponse])
async def search_by_text(
    search_request: ImageSearchRequest,
    db: Session = Depends(get_db)
):
    """以文找图搜索 - 根据设计文档实现（已迁移到QA模块）"""
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="此API已迁移到 /api/qa/sessions/{session_id}/image-search，请使用新的API端点"
    )

@router.get("/similar/{image_id}", response_model=List[ImageSearchResponse])
async def get_similar_images(
    image_id: int,
    similarity_threshold: float = settings.QA_DEFAULT_SIMILARITY_THRESHOLD,
    limit: int = 10,
    db: Session = Depends(get_db)
):
    """获取相似图片 - 根据设计文档实现（已迁移到QA模块）"""
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="此API已迁移到 /api/qa/sessions/{session_id}/image-search，请使用新的API端点"
    )

@router.post("/upload-and-search", response_model=dict)
async def upload_and_search(
    file: UploadFile = File(...),
    search_type: str = "image",
    similarity_threshold: float = settings.QA_DEFAULT_SIMILARITY_THRESHOLD,
    limit: int = 10,
    knowledge_base_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """上传图片并搜索 - 根据设计文档实现（已迁移到QA模块）"""
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="此API已迁移到 /api/qa/sessions/{session_id}/image-search，请使用新的API端点"
    )

@router.get("/vectors/{image_id}")
async def get_image_vectors(
    image_id: int,
    db: Session = Depends(get_db)
):
    """获取图片向量信息 - 根据设计文档实现"""
    try:
        logger.info(f"API请求: 获取图片向量信息，图片ID: {image_id}")
        
        service = ImageSearchService(db)
        vector_info = await service.get_image_vectors(image_id)
        
        logger.info(f"API响应: 获取图片向量信息成功")
        return vector_info
        
    except Exception as e:
        logger.error(f"获取图片向量信息API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取图片向量信息失败: {str(e)}"
        )
    """上传图片"""
    service = ImageService(db)
    return await service.upload_image(file, document_id)

@router.get("/{image_id}", response_model=ImageResponse)
async def get_image(
    image_id: int,
    db: Session = Depends(get_db)
):
    """获取图片详情"""
    service = ImageService(db)
    image = await service.get_image(image_id)
    if not image:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="图片不存在"
        )
    return image
