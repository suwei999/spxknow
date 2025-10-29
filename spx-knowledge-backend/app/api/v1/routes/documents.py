"""
Document API Routes
"""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from typing import List, Optional
import json
from app.schemas.document import DocumentCreate, DocumentUpdate, DocumentResponse, DocumentUploadRequest
from app.services.document_service import DocumentService
from app.dependencies.database import get_db
from sqlalchemy.orm import Session
from app.core.logging import logger
from app.config.settings import settings

router = APIRouter()

@router.get("/")
async def get_documents(
    page: int = 1,
    size: int = settings.QA_DEFAULT_PAGE_SIZE,
    knowledge_base_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """获取文档列表 - 根据文档处理流程设计实现"""
    try:
        logger.info(f"API请求: 获取文档列表，page: {page}, size: {size}, 知识库ID: {knowledge_base_id}")
        
        service = DocumentService(db)
        skip = max(page - 1, 0) * max(size, 1)
        documents = await service.get_documents(
            skip=skip,
            limit=size,
            knowledge_base_id=knowledge_base_id
        )
        # 构建返回项并统计总数
        from app.models.document import Document
        from app.models.knowledge_base import KnowledgeBase
        base_q = db.query(Document).filter(Document.is_deleted == False)
        if knowledge_base_id:
            base_q = base_q.filter(Document.knowledge_base_id == knowledge_base_id)
        total = base_q.count()

        # 预取知识库名称映射
        kb_ids = {d.knowledge_base_id for d in documents}
        kb_map = {}
        if kb_ids:
            rows = db.query(KnowledgeBase.id, KnowledgeBase.name).filter(KnowledgeBase.id.in_(kb_ids)).all()
            kb_map = {rid: name for rid, name in rows}

        items = []
        for d in documents:
            meta = getattr(d, 'meta', None)
            title = None
            if isinstance(meta, dict):
                title = meta.get('title') or meta.get('name')
            if not title:
                # 默认使用原始文件名（去扩展名）作为标题
                try:
                    import os
                    title = os.path.splitext(d.original_filename or '')[0] or d.original_filename
                except Exception:
                    title = d.original_filename
            items.append({
                "id": d.id,
                "title": title,
                "file_name": d.original_filename,
                "file_type": d.file_type,
                "file_size": d.file_size,
                "status": d.status,
                "knowledge_base_id": d.knowledge_base_id,
                "knowledge_base_name": kb_map.get(d.knowledge_base_id)
            })

        logger.info(f"API响应: 返回 {len(documents)} 个文档")
        return {
            "code": 0,
            "message": "ok",
            "data": {
                "list": items,
                "total": total,
                "page": page,
                "size": size
            }
        }
        
    except Exception as e:
        logger.error(f"获取文档列表API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取文档列表失败: {str(e)}"
        )

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    knowledge_base_id: int = Form(...),
    category_id: Optional[int] = Form(None),
    tags: Optional[str] = Form(None),
    metadata: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """
    上传文档 - 根据文档处理流程设计实现
    
    请求参数：
    - file: 文件对象 (multipart/form-data)
    - knowledge_base_id: 知识库ID (必填)
    - category_id: 分类ID (可选)
    - tags: 标签列表JSON字符串 (可选)
    - metadata: 元数据JSON字符串 (可选)
    
    响应内容：
    - document_id: 文档唯一标识
    - task_id: 处理任务标识
    - file_info: 文件信息
    - knowledge_base_info: 知识库信息
    - tag_info: 标签信息
    - upload_time: 上传时间
    """
    try:
        logger.info(f"API请求: 上传文档 {file.filename}, 知识库ID: {knowledge_base_id}")
        
        # 解析tags
        parsed_tags = []
        if tags:
            try:
                parsed_tags = json.loads(tags)
            except json.JSONDecodeError:
                logger.warning(f"标签格式错误: {tags}，使用空列表")
                parsed_tags = []
        
        # 解析metadata
        parsed_metadata = {}
        if metadata:
            try:
                parsed_metadata = json.loads(metadata)
            except json.JSONDecodeError:
                logger.warning(f"元数据格式错误: {metadata}，使用空对象")
                parsed_metadata = {}
        
        logger.info(f"解析参数: category_id={category_id}, tags={parsed_tags}, metadata={parsed_metadata}")
        
        # 调用服务上传文档
        service = DocumentService(db)
        result = await service.upload_document(
            file=file,
            knowledge_base_id=knowledge_base_id,
            category_id=category_id,
            tags=parsed_tags,
            metadata=parsed_metadata
        )
        
        logger.info(f"API响应: 文档上传成功，文档ID: {result['document_id']}, 任务ID: {result.get('task_id')}")
        return {
            "document_id": result['document_id'],
            "task_id": result.get('task_id'),
            "file_info": {
                "filename": file.filename,
                "size": result.get('file_size'),
                "type": result.get('file_type')
            },
            "knowledge_base_info": {
                "knowledge_base_id": knowledge_base_id,
                "category_id": category_id
            },
            "tag_info": {
                "tags": parsed_tags
            },
            "upload_time": result.get('upload_timestamp')
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"上传文档API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"上传文档失败: {str(e)}"
        )

@router.get("/{doc_id}")
async def get_document(
    doc_id: int,
    db: Session = Depends(get_db)
):
    """获取文档详情 - 根据文档处理流程设计实现"""
    try:
        logger.info(f"API请求: 获取文档详情 {doc_id}")
        
        service = DocumentService(db)
        doc = await service.get_document(doc_id)
        
        if not doc:
            logger.warning(f"API响应: 文档不存在 {doc_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文档不存在"
            )
        # 构造统一响应
        from app.models.knowledge_base import KnowledgeBase
        kb_name = None
        try:
            kb_name = db.query(KnowledgeBase.name).filter(KnowledgeBase.id == doc.knowledge_base_id).scalar()
        except Exception:
            kb_name = None
        meta = getattr(doc, 'meta', None)
        title = None
        if isinstance(meta, dict):
            title = meta.get('title') or meta.get('name')
        if not title:
            try:
                import os
                title = os.path.splitext(doc.original_filename or '')[0] or doc.original_filename
            except Exception:
                title = doc.original_filename

        payload = {
            "id": doc.id,
            "title": title,
            "file_name": doc.original_filename,
            "file_type": doc.file_type,
            "file_size": doc.file_size,
            "status": doc.status,
            "knowledge_base_id": doc.knowledge_base_id,
            "knowledge_base_name": kb_name,
            "created_at": doc.created_at,
            "updated_at": doc.updated_at,
        }
        
        logger.info(f"API响应: 返回文档详情 {doc.original_filename}")
        return {"code": 0, "message": "ok", "data": payload}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取文档详情API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取文档详情失败: {str(e)}"
        )

@router.put("/{doc_id}", response_model=DocumentResponse)
async def update_document(
    doc_id: int,
    document: DocumentUpdate,
    db: Session = Depends(get_db)
):
    """更新文档 - 根据文档处理流程设计实现"""
    try:
        logger.info(f"API请求: 更新文档 {doc_id}")
        
        service = DocumentService(db)
        doc = await service.update_document(doc_id, document)
        
        if not doc:
            logger.warning(f"API响应: 文档不存在 {doc_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文档不存在"
            )
        
        logger.info(f"API响应: 文档更新成功 {doc.original_filename}")
        return doc
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新文档API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新文档失败: {str(e)}"
        )

@router.delete("/{doc_id}")
async def delete_document(
    doc_id: int,
    db: Session = Depends(get_db)
):
    """删除文档 - 根据文档处理流程设计实现"""
    try:
        logger.info(f"API请求: 删除文档 {doc_id}")
        
        service = DocumentService(db)
        success = await service.delete_document(doc_id)
        
        if not success:
            logger.warning(f"API响应: 文档不存在 {doc_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文档不存在"
            )
        
        logger.info(f"API响应: 文档删除成功 {doc_id}")
        return {"message": "文档删除成功"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除文档API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除文档失败: {str(e)}"
        )

@router.post("/batch-upload")
async def batch_upload_documents(
    files: List[UploadFile] = File(...),
    knowledge_base_id: int = Form(...),
    category_id: Optional[int] = Form(None),
    tags: Optional[str] = Form(None),
    metadata: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """
    批量上传文档 - 根据文档处理流程设计实现
    
    请求参数：
    - files: 文件列表 (multipart/form-data)
    - knowledge_base_id: 知识库ID (必填)
    - category_id: 分类ID (可选)
    - tags: 标签列表JSON字符串 (可选)
    - metadata: 元数据JSON字符串 (可选)
    
    响应内容：
    - success_count: 成功数量
    - fail_count: 失败数量
    - results: 结果列表
    """
    try:
        logger.info(f"API请求: 批量上传文档，文件数量: {len(files)}, 知识库ID: {knowledge_base_id}")
        
        # 解析tags
        parsed_tags = []
        if tags:
            try:
                parsed_tags = json.loads(tags)
            except json.JSONDecodeError:
                logger.warning(f"标签格式错误: {tags}，使用空列表")
                parsed_tags = []
        
        # 解析metadata
        parsed_metadata = {}
        if metadata:
            try:
                parsed_metadata = json.loads(metadata)
            except json.JSONDecodeError:
                logger.warning(f"元数据格式错误: {metadata}，使用空对象")
                parsed_metadata = {}
        
        service = DocumentService(db)
        results = []
        success_count = 0
        fail_count = 0
        
        for file in files:
            try:
                logger.info(f"处理文件: {file.filename}")
                result = await service.upload_document(
                    file=file,
                    knowledge_base_id=knowledge_base_id,
                    category_id=category_id,
                    tags=parsed_tags,
                    metadata=parsed_metadata
                )
                results.append({
                    "filename": file.filename,
                    "document_id": result['document_id'],
                    "task_id": result.get('task_id'),
                    "status": "success"
                })
                success_count += 1
            except Exception as e:
                logger.error(f"文件 {file.filename} 上传失败: {e}")
                results.append({
                    "filename": file.filename,
                    "status": "failed",
                    "error": str(e)
                })
                fail_count += 1
        
        logger.info(f"API响应: 批量上传完成，成功: {success_count}, 失败: {fail_count}")
        return {
            "success_count": success_count,
            "fail_count": fail_count,
            "total": len(files),
            "results": results
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批量上传文档API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"批量上传文档失败: {str(e)}"
        )

@router.post("/{doc_id}/reprocess")
def reprocess_document(
    doc_id: int,
    db: Session = Depends(get_db)
):
    """重新处理文档 - 根据文档处理流程设计实现"""
    try:
        logger.info(f"API请求: 重新处理文档 {doc_id}")
        
        service = DocumentService(db)
        success = service.reprocess_document(doc_id)
        
        if not success:
            logger.warning(f"API响应: 文档不存在 {doc_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文档不存在"
            )
        
        logger.info(f"API响应: 文档重新处理已启动 {doc_id}")
        return {"message": "文档重新处理已启动"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重新处理文档API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"重新处理文档失败: {str(e)}"
        )
