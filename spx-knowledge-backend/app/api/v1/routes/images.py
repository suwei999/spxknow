"""
Image API Routes
根据文档处理流程设计实现图片搜索API接口
"""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Response, Request
from typing import List, Optional
from app.schemas.image import ImageResponse, ImageSearchRequest, ImageSearchResponse
from app.services.image_service import ImageService
from app.services.image_search_service import ImageSearchService
from app.dependencies.database import get_db
from sqlalchemy.orm import Session
from app.core.logging import logger
from app.config.settings import settings
from app.services.opensearch_service import OpenSearchService
from app.services.minio_storage_service import MinioStorageService
from app.models.image import DocumentImage
from fastapi import Body

router = APIRouter()

@router.get("/", response_model=List[ImageResponse])
async def get_images(
    skip: int = 0,
    limit: int = 100,
    document_id: Optional[int] = None,
    db: Session = Depends(get_db),
    request: Request = None
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

        # 将 MinIO 对象名转换为可访问 URL（优先缩略图）
        scheme = "https" if settings.MINIO_SECURE else "http"
        base = f"{scheme}://{settings.MINIO_ENDPOINT}/{settings.MINIO_BUCKET_NAME}"
        def to_url(object_name: str | None) -> str | None:
            if not object_name:
                return None
            if object_name.startswith('http://') or object_name.startswith('https://'):
                return object_name
            return f"{base}/{object_name}"

        # 从请求中获取token（如果有），添加到URL中（用于<img>标签认证）
        token = ""
        if request:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header.replace("Bearer ", "")

        for img in images:
            # 动态属性赋值：如果有缩略图，用缩略图；否则用原图
            preview = getattr(img, 'thumbnail_path', None) or getattr(img, 'image_path', None)
            # 统一改为后端代理，避免前端直连 MinIO
            if preview:
                try:
                    from urllib.parse import quote
                    if token:
                        proxy_url = f"/api/images/file?object={quote(preview, safe='')}&token={token}"
                    else:
                        proxy_url = f"/api/images/file?object={quote(preview, safe='')}"
                    setattr(img, 'image_path', proxy_url)
                except Exception:
                    pass

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
    similarity_threshold: float = settings.SEARCH_VECTOR_THRESHOLD,
    limit: int = 10,
    knowledge_base_id: Optional[List[int]] = None,
    db: Session = Depends(get_db)
):
    """以图找图搜索 - 使用CLIP图像编码器进行512维向量搜索"""
    try:
        logger.info(f"API请求: 以图找图搜索，文件: {file.filename}, 相似度阈值: {similarity_threshold}, 知识库ID: {knowledge_base_id}")
        
        # 验证知识库ID（如果提供了）
        if knowledge_base_id:
            from app.models.knowledge_base import KnowledgeBase
            kb_ids = knowledge_base_id if isinstance(knowledge_base_id, list) else [knowledge_base_id]
            if len(kb_ids) > 0:
                kbs = db.query(KnowledgeBase).filter(
                    KnowledgeBase.id.in_(kb_ids),
                    KnowledgeBase.is_active == True
                ).all()
                found_ids = {kb.id for kb in kbs}
                missing_ids = set(kb_ids) - found_ids
                if missing_ids:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"以下知识库ID不存在或未激活: {', '.join(map(str, missing_ids))}"
                    )
        
        service = ImageSearchService(db)
        results = await service.search_by_image(
            file=file,
            similarity_threshold=similarity_threshold,
            limit=limit,
            knowledge_base_id=knowledge_base_id
        )
        
        logger.info(f"API响应: 找到 {len(results)} 个相似图片")
        return results
        
    except Exception as e:
        logger.error(f"以图找图搜索API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"以图找图搜索失败: {str(e)}"
        )

@router.post("/search-by-text", response_model=List[ImageSearchResponse])
async def search_by_text(
    search_request: ImageSearchRequest,
    db: Session = Depends(get_db)
):
    """以文找图搜索 - 使用CLIP文本编码器进行512维向量搜索"""
    try:
        # 记录前端传入的所有参数
        logger.info(
            f"[以文搜图API] 前端传入参数: "
            f"query_text='{search_request.query_text}', "
            f"similarity_threshold={search_request.similarity_threshold}, "
            f"limit={search_request.limit}, "
            f"knowledge_base_id={search_request.knowledge_base_id}"
        )
        
        service = ImageSearchService(db)
        results = await service.search_by_text(search_request)
        
        logger.info(f"[以文搜图API] 响应: 找到 {len(results)} 个相关图片")
        return results
        
    except Exception as e:
        logger.error(f"[以文搜图API] 错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"以文找图搜索失败: {str(e)}"
        )

@router.get("/similar/{image_id}", response_model=List[ImageSearchResponse])
async def get_similar_images(
    image_id: int,
    similarity_threshold: float = settings.SEARCH_VECTOR_THRESHOLD,
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
    similarity_threshold: float = settings.SEARCH_VECTOR_THRESHOLD,
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

@router.get("/{image_id}", response_model=ImageResponse)
async def get_image(
    image_id: int,
    db: Session = Depends(get_db),
    request: Request = None
):
    """获取图片详情"""
    try:
        logger.info(f"API请求: 获取图片详情，图片ID: {image_id}")
        service = ImageService(db)
        image = await service.get_image(image_id)
        if not image:
            logger.warning(f"图片不存在: {image_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="图片不存在"
            )
        # 优先从 OpenSearch 读取向量信息；若缺失再兜底
        try:
            os_service = OpenSearchService()
            vec_meta = await os_service.get_image_vector_info(image_id)
            if vec_meta:
                if vec_meta.get('dimension') and not getattr(image, 'vector_dim', None):
                    setattr(image, 'vector_dim', vec_meta.get('dimension'))
                # 使用索引中的模型版本标注
                if vec_meta.get('model') and not getattr(image, 'vector_model', None):
                    setattr(image, 'vector_model', vec_meta.get('model'))
        except Exception:
            pass

        # 字段兜底：图片类型/向量模型/向量维度
        try:
            # 推断图片类型
            img_path = getattr(image, 'image_path', None)
            if not getattr(image, 'image_type', None) and isinstance(img_path, str):
                ext = img_path.split('.')[-1].lower() if '.' in img_path else ''
                guessed = 'jpeg' if ext in ['jpg', 'jpeg'] else (ext if ext in ['png','gif','webp','bmp'] else None)
                if guessed:
                    setattr(image, 'image_type', guessed)
            # 默认向量信息（系统使用 CLIP ViT-B/32 生成 512 维）
            if not getattr(image, 'vector_model', None):
                setattr(image, 'vector_model', 'CLIP ViT-B/32')
            if not getattr(image, 'vector_dim', None):
                setattr(image, 'vector_dim', 512)
        except Exception:
            pass

        # 统一返回可访问的图片URL（包含token用于认证）
        try:
            from urllib.parse import quote
            # 从请求中获取token（如果有），添加到URL中
            token = ""
            if request:
                auth_header = request.headers.get("Authorization", "")
                if auth_header.startswith("Bearer "):
                    token = auth_header.replace("Bearer ", "")
            
            if img_path:
                if token:
                    proxy_url = f"/api/images/file?object={quote(img_path, safe='')}&token={token}"
                else:
                    proxy_url = f"/api/images/file?object={quote(img_path, safe='')}"
                setattr(image, 'image_path', proxy_url)
        except Exception:
            pass

        logger.info(f"API响应: 获取图片详情成功")
        return image
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取图片详情API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取图片详情失败: {str(e)}"
        )

@router.post("/{image_id}/retry-ocr")
async def retry_image_ocr(
    image_id: int,
    db: Session = Depends(get_db)
):
    """重新触发图片OCR + 向量化 + 索引"""
    service = ImageService(db)
    image = service.db.query(DocumentImage).filter(
        DocumentImage.id == image_id,
        DocumentImage.is_deleted == False
    ).first()
    if not image:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="图片不存在")
    if image.status == "completed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="图片已处理完成，无需重试")
    success = service.process_image_sync(image_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="重试失败，请稍后再试")
    return {"status": "success", "message": "图片OCR已重新执行"}

@router.get("/file")
async def get_image_file(
    object: str,
    request: Request
):
    """图片代理：通过 MinIO 读取并返回图片二进制，避免前端直连 MinIO。需要认证"""
    try:
        # 从请求中获取当前用户ID（由中间件设置）
        user = getattr(request.state, 'user', None)
        if not user:
            from fastapi import HTTPException, status
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未认证")
        
        minio = MinioStorageService()
        data = minio.download_file(object)

        lower = object.lower()
        if lower.endswith((".jpg", ".jpeg")):
            content_type = "image/jpeg"
        elif lower.endswith(".png"):
            content_type = "image/png"
        elif lower.endswith(".gif"):
            content_type = "image/gif"
        elif lower.endswith(".webp"):
            content_type = "image/webp"
        else:
            content_type = "application/octet-stream"

        return Response(content=data, media_type=content_type)
    except Exception as e:
        logger.error(f"图片代理错误: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="图片不存在或无法访问")
