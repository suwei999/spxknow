"""
文档块编辑 API（骨架版）
PATCH /api/documents/{id}/chunks/{chunk_id}
 - 写入 chunk_versions
 - 切换当前块版本（可选）
 - 重新生成向量并更新 OpenSearch
"""

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.dependencies.database import get_db
from app.core.logging import logger
from app.models.chunk import DocumentChunk
from app.models.chunk_version import ChunkVersion
from app.services.vector_service import VectorService
from app.services.opensearch_service import OpenSearchService

router = APIRouter()


class ChunkEditPayload(BaseModel):
    content: str = Field(..., description="新内容")
    version_comment: str | None = Field(None, description="版本备注")


@router.patch("/documents/{doc_id}/chunks/{chunk_id}")
def edit_chunk(
    payload: ChunkEditPayload,
    doc_id: int = Path(...),
    chunk_id: int = Path(...),
    db: Session = Depends(get_db),
):
    chunk = db.query(DocumentChunk).filter(DocumentChunk.id == chunk_id, DocumentChunk.document_id == doc_id).first()
    if not chunk:
        return {"code": 404, "message": "chunk not found", "data": None}

    # 创建 chunk 版本记录
    cv = ChunkVersion(
        chunk_id=chunk.id,
        content=payload.content,
        version_comment=payload.version_comment or "",
    )
    db.add(cv)
    db.commit()
    db.refresh(cv)

    # 将块内容切换为新版本（如果表保留 content 字段，则更新它）
    if hasattr(chunk, "content"):
        chunk.content = payload.content
        db.commit()

    # 重新生成向量并更新 OS
    vs = VectorService(db)
    osvc = OpenSearchService()
    vector = vs.generate_embedding(payload.content)
    os_doc = {
        "document_id": doc_id,
        "chunk_id": chunk.id,
        "knowledge_base_id": getattr(chunk, "knowledge_base_id", None),
        "category_id": getattr(chunk, "category_id", None),
        "content": payload.content,
        "chunk_type": getattr(chunk, "chunk_type", "text"),
        "metadata": {"edited": True},
        "content_vector": vector,
        "created_at": chunk.created_at.isoformat() if getattr(chunk, "created_at", None) else None,
    }
    osvc.index_document_chunk_sync(os_doc)

    logger.info(f"编辑并重索引完成: doc={doc_id} chunk={chunk_id} version={cv.id}")
    return {"code": 0, "message": "ok", "data": {"chunk_id": chunk_id, "version_id": cv.id}}

"""
Document Modification API Routes
根据文档修改功能设计实现
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime
from app.dependencies.database import get_db
from app.core.logging import logger
from app.config.settings import settings
from app.models.chunk import DocumentChunk
from app.models.document import Document
from app.models.chunk_version import ChunkVersion
from app.schemas.chunk_version import ChunkVersionResponse, ChunkVersionListResponse, ChunkRevertRequest, ChunkRevertResponse
from app.services.chunk_version_service import ChunkVersionService
from app.services.content_validation_service import ContentValidationService
from app.services.smart_vectorization_service import SmartVectorizationService
from app.services.operation_status_service import OperationStatusService
from app.services.performance_monitoring_service import PerformanceMonitoringService
from app.services.websocket_notification_service import websocket_notification_service
from app.services.diff_analysis_service import DiffAnalysisService
from app.tasks.document_tasks import process_document_task
from app.core.document_modification_errors import (
    DocumentModificationErrorCode,
    DocumentModificationErrorResponse
)

def create_document_not_found_error(document_id: int) -> HTTPException:
    """创建文档不存在的错误响应"""
    error_response = DocumentModificationErrorResponse.create_error_response(
        DocumentModificationErrorCode.CHUNK_NOT_FOUND,
        f"文档 {document_id} 不存在"
    )
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=error_response
    )

def create_chunk_not_found_error(chunk_id: int) -> HTTPException:
    """创建块不存在的错误响应"""
    error_response = DocumentModificationErrorResponse.create_error_response(
        DocumentModificationErrorCode.CHUNK_NOT_FOUND,
        f"块 {chunk_id} 不存在"
    )
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=error_response
    )

def create_content_validation_error(message: str) -> HTTPException:
    """创建内容验证错误响应"""
    error_response = DocumentModificationErrorResponse.create_error_response(
        DocumentModificationErrorCode.CONTENT_FORMAT_ERROR,
        message
    )
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=error_response
    )

def create_permission_error(message: str) -> HTTPException:
    """创建权限错误响应"""
    error_response = DocumentModificationErrorResponse.create_error_response(
        DocumentModificationErrorCode.PERMISSION_DENIED,
        message
    )
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=error_response
    )

def create_version_conflict_error(message: str) -> HTTPException:
    """创建版本冲突错误响应"""
    error_response = DocumentModificationErrorResponse.create_error_response(
        DocumentModificationErrorCode.VERSION_CONFLICT,
        message
    )
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=error_response
    )

def create_vectorization_error(message: str) -> HTTPException:
    """创建向量化错误响应"""
    error_response = DocumentModificationErrorResponse.create_error_response(
        DocumentModificationErrorCode.VECTORIZATION_FAILED,
        message
    )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=error_response
    )

def create_index_update_error(message: str) -> HTTPException:
    """创建索引更新错误响应"""
    error_response = DocumentModificationErrorResponse.create_error_response(
        DocumentModificationErrorCode.INDEX_UPDATE_FAILED,
        message
    )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=error_response
    )

def create_cache_update_error(message: str) -> HTTPException:
    """创建缓存更新错误响应"""
    error_response = DocumentModificationErrorResponse.create_error_response(
        DocumentModificationErrorCode.CACHE_UPDATE_FAILED,
        message
    )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=error_response
    )

router = APIRouter()

@router.get("/{document_id}/chunks/{chunk_id}")
def get_chunk_content(
    document_id: int,
    chunk_id: int,
    include_metadata: bool = True,
    db: Session = Depends(get_db)
):
    """获取块内容 - 根据文档修改功能设计实现"""
    try:
        logger.info(f"API请求: 获取块内容 document_id={document_id}, chunk_id={chunk_id}")
        
        # 验证文档是否存在
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            logger.warning(f"文档不存在: {document_id}")
            raise create_document_not_found_error(document_id)
        
        # 获取块内容
        chunk = db.query(DocumentChunk).filter(
            DocumentChunk.id == chunk_id,
            DocumentChunk.document_id == document_id
        ).first()
        
        if not chunk:
            logger.warning(f"块不存在: document_id={document_id}, chunk_id={chunk_id}")
            error_response = DocumentModificationErrorResponse.create_error_response(
                DocumentModificationErrorCode.CHUNK_NOT_FOUND,
                f"块 {chunk_id} 不存在"
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response
            )
        
        # 构建响应数据 - 严格按照设计文档格式
        data = {
            "chunk_id": str(chunk.id),
            "document_id": str(document_id),
            "content": chunk.content,
            "chunk_type": chunk.chunk_type,
            "version": getattr(chunk, 'version', 1),
            "edit_history": []
        }
        
        if include_metadata:
            data["metadata"] = {
                "char_count": len(chunk.content),
                "token_count": len(chunk.content.split()),  # 简单的词数统计
                "language": "zh",  # TODO: 实现语言检测
                "created_at": chunk.created_at.isoformat() if chunk.created_at else "2024-01-01T10:00:00Z"
            }
        else:
            data["metadata"] = None
        
        # 按照设计文档要求的响应格式
        result = {
            "status": "success",
            "data": data
        }
        
        logger.info(f"API响应: 成功获取块内容 document_id={document_id}, chunk_id={chunk_id}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取块内容API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取块内容失败: {str(e)}"
        )

@router.get("/{document_id}/chunks")
def get_document_chunks(
    document_id: int,
    db: Session = Depends(get_db)
):
    """获取文档所有块 - 根据文档修改功能设计实现"""
    try:
        logger.info(f"API请求: 获取文档所有块 document_id={document_id}")
        
        # 验证文档是否存在
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            logger.warning(f"文档不存在: {document_id}")
            raise create_document_not_found_error(document_id)
        
        # 获取所有块
        chunks = db.query(DocumentChunk).filter(
            DocumentChunk.document_id == document_id
        ).order_by(DocumentChunk.chunk_index).all()
        
        # 按照设计文档要求的响应格式
        data = {
            "document_id": str(document_id),
            "total_chunks": len(chunks),
            "chunks": [
                {
                    "chunk_id": str(chunk.id),
                    "chunk_index": chunk.chunk_index,
                    "content_preview": chunk.content[:settings.CONTENT_PREVIEW_LENGTH] + "..." if len(chunk.content) > settings.CONTENT_PREVIEW_LENGTH else chunk.content,
                    "chunk_type": chunk.chunk_type,
                    "char_count": len(chunk.content)
                }
                for chunk in chunks
            ]
        }
        
        result = {
            "status": "success",
            "data": data
        }
        
        logger.info(f"API响应: 返回 {len(chunks)} 个块")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取文档块API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取文档块失败: {str(e)}"
        )

@router.put("/{document_id}/chunks/{chunk_id}")
async def update_chunk_content(
    document_id: int,
    chunk_id: int,
    content_data: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """更新块内容 - 根据文档修改功能设计实现"""
    try:
        logger.info(f"API请求: 更新块内容 document_id={document_id}, chunk_id={chunk_id}")
        
        # 验证文档是否存在
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            logger.warning(f"文档不存在: {document_id}")
            raise create_document_not_found_error(document_id)
        
        # 获取块
        chunk = db.query(DocumentChunk).filter(
            DocumentChunk.id == chunk_id,
            DocumentChunk.document_id == document_id
        ).first()
        
        if not chunk:
            logger.warning(f"块不存在: document_id={document_id}, chunk_id={chunk_id}")
            raise create_chunk_not_found_error(chunk_id)
        
        # 验证内容
        new_content = content_data.get("content", "")
        if not new_content:
            raise create_content_validation_error("内容不能为空")
        
        # 内容验证 - 根据设计文档实现
        validation_service = ContentValidationService(db)
        metadata = content_data.get("metadata", {})
        validation_result = validation_service.validate_content(new_content, metadata)
        
        if not validation_result["valid"]:
            error_response = DocumentModificationErrorResponse.create_error_response(
                DocumentModificationErrorCode.CONTENT_FORMAT_ERROR,
                validation_result['message']
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_response
            )
        
        # 操作状态管理 - 根据设计文档实现
        status_service = OperationStatusService(db)
        operation_id = status_service.start_modification_operation(document_id, chunk_id, "user")
        
        # WebSocket通知 - 根据设计文档实现
        await websocket_notification_service.send_modification_notification(
            "modification_started",
            document_id,
            chunk_id,
            "user",
            {"operation_id": operation_id}
        )
        
        try:
            # 保存当前版本 - 根据设计文档实现版本管理
            version_service = ChunkVersionService(db)
            current_version_data = {
                "chunk_id": chunk_id,
                "content": chunk.content,
                "metadata": chunk.metadata,
                "modified_by": "user",
                "version_comment": "修改前的版本保存"
            }
            version_service.create_chunk_version(chunk_id, current_version_data)
            
            # 更新块内容
            chunk.content = new_content
            
            # 更新元数据和版本信息
            if metadata:
                chunk.metadata = str(metadata)
            
            # 更新版本管理字段
            chunk.version += 1
            chunk.last_modified_at = datetime.now()
            chunk.modification_count += 1
            chunk.last_modified_by = "user"
            
            db.commit()
            
            # 更新操作进度
            status_service.update_operation_progress(operation_id, 50.0, "内容已保存，开始重新向量化")
            
            # WebSocket进度通知
            await websocket_notification_service.send_progress_notification(
                operation_id, 50.0, "内容已保存，开始重新向量化", "user"
            )
            
            # 触发全文档重新向量化任务
            # 根据设计文档，修改后需要重新向量化整个文档的所有块
            from app.tasks.document_tasks import reprocess_document_task
            task = reprocess_document_task.delay(document_id)
            
            # 更新操作进度
            status_service.update_operation_progress(operation_id, 80.0, "向量化任务已启动")
            
            # WebSocket进度通知
            await websocket_notification_service.send_progress_notification(
                operation_id, 80.0, "向量化任务已启动", "user"
            )
            
            # 按照设计文档要求的响应格式
            data = {
                "chunk_id": str(chunk_id),
                "version": chunk.version,
                "task_id": task.id,
                "estimated_completion": "2024-01-01T11:02:00Z"  # TODO: 计算实际完成时间
            }
            
            result = {
                "status": "success",
                "data": data
            }
            
            # 完成操作状态
            status_service.complete_modification_operation(operation_id, True, "修改完成")
            
            # WebSocket完成通知
            await websocket_notification_service.send_modification_notification(
                "modification_completed",
                document_id,
                chunk_id,
                "user",
                {"operation_id": operation_id, "task_id": task.id}
            )
            
            logger.info(f"API响应: 块内容更新成功，任务ID: {task.id}")
            return result
            
        except Exception as e:
            # 操作失败，更新状态
            status_service.complete_modification_operation(operation_id, False, f"修改失败: {str(e)}")
            
            # WebSocket错误通知
            await websocket_notification_service.send_error_notification(
                "modification_error",
                str(e),
                document_id,
                chunk_id,
                "user"
            )
            raise
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新块内容API错误: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新块内容失败: {str(e)}"
        )

# 块版本管理API接口 - 根据设计文档实现

@router.get("/{document_id}/chunks/{chunk_id}/versions", response_model=ChunkVersionListResponse)
def get_chunk_versions(
    document_id: int,
    chunk_id: int,
    skip: int = 0,
    limit: int = settings.QA_DEFAULT_PAGE_SIZE,
    db: Session = Depends(get_db)
):
    """获取块版本列表 - 根据设计文档实现"""
    try:
        logger.info(f"API请求: 获取块版本列表 document_id={document_id}, chunk_id={chunk_id}")
        
        # 验证文档和块是否存在
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise create_document_not_found_error(document_id)
        
        chunk = db.query(DocumentChunk).filter(
            DocumentChunk.id == chunk_id,
            DocumentChunk.document_id == document_id
        ).first()
        
        if not chunk:
            raise create_chunk_not_found_error(chunk_id)
        
        # 获取版本列表
        version_service = ChunkVersionService(db)
        result = version_service.get_chunk_versions(chunk_id, skip, limit)
        
        logger.info(f"API响应: 获取块版本列表成功，版本数={result.total_versions}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取块版本列表API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取块版本列表失败: {str(e)}"
        )

@router.get("/{document_id}/chunks/{chunk_id}/versions/{version_number}", response_model=ChunkVersionResponse)
def get_chunk_version(
    document_id: int,
    chunk_id: int,
    version_number: int,
    db: Session = Depends(get_db)
):
    """获取特定版本 - 根据设计文档实现"""
    try:
        logger.info(f"API请求: 获取特定版本 document_id={document_id}, chunk_id={chunk_id}, version={version_number}")
        
        # 验证文档和块是否存在
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise create_document_not_found_error(document_id)
        
        chunk = db.query(DocumentChunk).filter(
            DocumentChunk.id == chunk_id,
            DocumentChunk.document_id == document_id
        ).first()
        
        if not chunk:
            raise create_chunk_not_found_error(chunk_id)
        
        # 获取特定版本
        version_service = ChunkVersionService(db)
        version = version_service.get_chunk_version(chunk_id, version_number)
        
        if not version:
            raise create_chunk_not_found_error(version_number)
        
        logger.info(f"API响应: 获取特定版本成功")
        return version
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取特定版本API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取特定版本失败: {str(e)}"
        )

@router.post("/{document_id}/chunks/{chunk_id}/versions/{version_number}/restore", response_model=ChunkRevertResponse)
def restore_chunk_version(
    document_id: int,
    chunk_id: int,
    version_number: int,
    revert_request: ChunkRevertRequest,
    db: Session = Depends(get_db)
):
    """回退版本 - 根据设计文档实现"""
    try:
        logger.info(f"API请求: 回退版本 document_id={document_id}, chunk_id={chunk_id}, version={version_number}")
        
        # 验证文档和块是否存在
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise create_document_not_found_error(document_id)
        
        chunk = db.query(DocumentChunk).filter(
            DocumentChunk.id == chunk_id,
            DocumentChunk.document_id == document_id
        ).first()
        
        if not chunk:
            raise create_chunk_not_found_error(chunk_id)
        
        # 执行版本回退
        version_service = ChunkVersionService(db)
        result = version_service.revert_chunk_to_version(chunk_id, revert_request)
        
        logger.info(f"API响应: 版本回退成功，任务ID={result.task_id}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"回退版本API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"回退版本失败: {str(e)}"
        )

@router.post("/{document_id}/chunks/{chunk_id}/revert-to-previous", response_model=ChunkRevertResponse)
def revert_chunk_to_previous_version(
    document_id: int,
    chunk_id: int,
    db: Session = Depends(get_db)
):
    """回退到上一个版本 - 根据设计文档实现"""
    try:
        logger.info(f"API请求: 回退到上一个版本 document_id={document_id}, chunk_id={chunk_id}")
        
        # 验证文档和块是否存在
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise create_document_not_found_error(document_id)
        
        chunk = db.query(DocumentChunk).filter(
            DocumentChunk.id == chunk_id,
            DocumentChunk.document_id == document_id
        ).first()
        
        if not chunk:
            raise create_chunk_not_found_error(chunk_id)
        
        # 执行回退到上一个版本
        version_service = ChunkVersionService(db)
        result = version_service.revert_chunk_to_previous_version(chunk_id)
        
        logger.info(f"API响应: 回退到上一个版本成功，任务ID={result.task_id}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"回退到上一个版本API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"回退到上一个版本失败: {str(e)}"
        )

# 内容验证API接口 - 根据设计文档实现

@router.post("/{document_id}/chunks/{chunk_id}/validate")
def validate_chunk_content(
    document_id: int,
    chunk_id: int,
    content_data: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """内容验证 - 根据设计文档实现"""
    try:
        logger.info(f"API请求: 内容验证 document_id={document_id}, chunk_id={chunk_id}")
        
        # 验证文档和块是否存在
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise create_document_not_found_error(document_id)
        
        chunk = db.query(DocumentChunk).filter(
            DocumentChunk.id == chunk_id,
            DocumentChunk.document_id == document_id
        ).first()
        
        if not chunk:
            raise create_chunk_not_found_error(chunk_id)
        
        # 获取验证内容
        content = content_data.get("content", "")
        metadata = content_data.get("metadata", {})
        
        if not content:
            raise create_content_validation_error("内容不能为空")
        
        # 执行内容验证
        validation_service = ContentValidationService(db)
        result = validation_service.validate_content(content, metadata)
        
        logger.info(f"API响应: 内容验证完成，结果={result['valid']}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"内容验证API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"内容验证失败: {str(e)}"
        )

# 性能监控和状态管理API接口 - 根据设计文档实现

@router.get("/performance/summary")
def get_performance_summary(
    db: Session = Depends(get_db)
):
    """获取性能摘要 - 根据设计文档实现"""
    try:
        logger.info("API请求: 获取性能摘要")
        
        monitoring_service = PerformanceMonitoringService(db)
        summary = monitoring_service.get_performance_summary()
        
        logger.info(f"API响应: 性能摘要获取成功，评分={summary['performance_score']}")
        return summary
        
    except Exception as e:
        logger.error(f"获取性能摘要API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取性能摘要失败: {str(e)}"
        )

@router.get("/performance/metrics/{metrics_type}")
def get_performance_metrics(
    metrics_type: str,
    hours: int = 24,
    db: Session = Depends(get_db)
):
    """获取性能指标历史 - 根据设计文档实现"""
    try:
        logger.info(f"API请求: 获取性能指标历史，类型={metrics_type}, 小时={hours}")
        
        monitoring_service = PerformanceMonitoringService(db)
        metrics_history = monitoring_service.get_metrics_history(metrics_type, hours)
        
        logger.info(f"API响应: 性能指标历史获取成功，记录数={len(metrics_history)}")
        
        # 按照设计文档要求的响应格式
        data = {
            "metrics_type": metrics_type,
            "hours": hours,
            "records_count": len(metrics_history),
            "metrics": metrics_history
        }
        
        result = {
            "status": "success",
            "data": data
        }
        
        return result
        
    except Exception as e:
        logger.error(f"获取性能指标历史API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取性能指标历史失败: {str(e)}"
        )

@router.get("/operations/status/{operation_id}")
def get_operation_status(
    operation_id: str,
    db: Session = Depends(get_db)
):
    """获取操作状态 - 根据设计文档实现"""
    try:
        logger.info(f"API请求: 获取操作状态，operation_id={operation_id}")
        
        status_service = OperationStatusService(db)
        status_info = status_service.get_operation_status(operation_id)
        
        if not status_info:
            raise create_chunk_not_found_error(operation_id)
        
        logger.info(f"API响应: 操作状态获取成功，状态={status_info['status']}")
        return status_info
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取操作状态API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取操作状态失败: {str(e)}"
        )

@router.get("/operations/active")
def get_active_operations(
    db: Session = Depends(get_db)
):
    """获取活跃操作 - 根据设计文档实现"""
    try:
        logger.info("API请求: 获取活跃操作")
        
        status_service = OperationStatusService(db)
        active_operations = status_service.get_active_operations()
        
        logger.info(f"API响应: 活跃操作获取成功，数量={len(active_operations)}")
        
        # 按照设计文档要求的响应格式
        data = {
            "active_count": len(active_operations),
            "operations": active_operations
        }
        
        result = {
            "status": "success",
            "data": data
        }
        
        return result
        
    except Exception as e:
        logger.error(f"获取活跃操作API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取活跃操作失败: {str(e)}"
        )

@router.post("/operations/{operation_id}/progress")
def update_operation_progress(
    operation_id: str,
    progress_data: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """更新操作进度 - 根据设计文档实现"""
    try:
        logger.info(f"API请求: 更新操作进度，operation_id={operation_id}")
        
        progress = progress_data.get("progress", 0.0)
        message = progress_data.get("message", "")
        
        if not 0.0 <= progress <= 100.0:
            raise create_content_validation_error("进度值必须在0-100之间")
        
        status_service = OperationStatusService(db)
        success = status_service.update_operation_progress(operation_id, progress, message)
        
        if not success:
            raise create_chunk_not_found_error(operation_id)
        
        logger.info(f"API响应: 操作进度更新成功，进度={progress}")
        
        # 按照设计文档要求的响应格式
        data = {
            "message": "操作进度更新成功",
            "progress": progress
        }
        
        result = {
            "status": "success",
            "data": data
        }
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新操作进度API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新操作进度失败: {str(e)}"
        )

# 缺失的API接口 - 根据设计文档补充

@router.get("/{document_id}/chunks/{chunk_id}/consistency-check")
def check_chunk_consistency(
    document_id: int,
    chunk_id: int,
    db: Session = Depends(get_db)
):
    """检查块数据一致性 - 根据设计文档实现"""
    try:
        logger.info(f"API请求: 检查块一致性 document_id={document_id}, chunk_id={chunk_id}")
        
        # 验证文档和块是否存在
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise create_document_not_found_error(document_id)
        
        chunk = db.query(DocumentChunk).filter(
            DocumentChunk.id == chunk_id,
            DocumentChunk.document_id == document_id
        ).first()
        
        if not chunk:
            raise create_chunk_not_found_error(chunk_id)
        
        # 实现块级别一致性检查逻辑 - 使用ConsistencyCheckService
        from app.services.consistency_check_service import ConsistencyCheckService
        
        consistency_service = ConsistencyCheckService(db)
        check_result = consistency_service.check_chunk_consistency(document_id, chunk_id)
        
        result = {
            "status": "success",
            "data": check_result
        }
        
        logger.info(f"API响应: 块一致性检查完成 document_id={document_id}, chunk_id={chunk_id}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"块一致性检查API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"块一致性检查失败: {str(e)}"
        )

@router.get("/{document_id}/chunks/{chunk_id}/revert-preview")
def get_revert_preview(
    document_id: int,
    chunk_id: int,
    db: Session = Depends(get_db)
):
    """获取回退预览 - 根据设计文档实现"""
    try:
        logger.info(f"API请求: 获取回退预览 document_id={document_id}, chunk_id={chunk_id}")
        
        # 验证文档和块是否存在
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise create_document_not_found_error(document_id)
        
        chunk = db.query(DocumentChunk).filter(
            DocumentChunk.id == chunk_id,
            DocumentChunk.document_id == document_id
        ).first()
        
        if not chunk:
            raise create_chunk_not_found_error(chunk_id)
        
        # 获取上一个版本
        version_service = ChunkVersionService(db)
        previous_version = db.query(ChunkVersion).filter(
            ChunkVersion.chunk_id == chunk_id,
            ChunkVersion.version_number < chunk.version
        ).order_by(ChunkVersion.version_number.desc()).first()
        
        if not previous_version:
            raise create_chunk_not_found_error(0)
        
        # 计算差异和风险评估 - 使用DiffAnalysisService
        diff_service = DiffAnalysisService()
        diff_result = diff_service.calculate_content_diff(
            current_content=chunk.content,
            new_content=previous_version.content
        )
        risk_level = diff_service.assess_risk(diff_result)
        estimated_time = diff_service.estimate_processing_time(
            content_length=len(chunk.content),
            similarity_score=1.0 - diff_result.get("change_ratio", 0)
        )
        
        # 构建预览数据
        preview_data = {
                "chunk_id": chunk_id,
                "current_version": {
                    "version_number": chunk.version,
                    "content": chunk.content,
                    "last_modified_at": chunk.last_modified_at.isoformat() if chunk.last_modified_at else None
                },
                "target_version": {
                    "version_number": previous_version.version_number,
                    "content": previous_version.content,
                    "created_at": previous_version.created_at.isoformat(),
                    "version_comment": previous_version.version_comment
                },
                "differences": {
                    "added_lines": diff_result["added_lines"],
                    "removed_lines": diff_result["removed_lines"],
                    "modified_lines": diff_result["modified_lines"],
                    "total_changes": diff_result["total_changes"]
                },
                "risk_assessment": risk_level,
                "estimated_time": estimated_time
            }
        
        logger.info(f"API响应: 回退预览获取成功 document_id={document_id}, chunk_id={chunk_id}")
        return preview_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取回退预览API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取回退预览失败: {str(e)}"
        )

@router.post("/{document_id}/chunks/batch-revert-previous")
def batch_revert_to_previous_version(
    document_id: int,
    chunk_ids: List[int],
    db: Session = Depends(get_db)
):
    """批量回退到上一个版本 - 根据设计文档实现"""
    try:
        logger.info(f"API请求: 批量回退到上一个版本 document_id={document_id}, 块数量={len(chunk_ids)}")
        
        # 验证文档是否存在
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise create_document_not_found_error(document_id)
        
        # 限制并发回退数量
        if len(chunk_ids) > settings.MAX_BATCH_OPERATION_SIZE:
            raise create_content_validation_error(f"单次批量回退不能超过{settings.MAX_BATCH_OPERATION_SIZE}个块")
        
        version_service = ChunkVersionService(db)
        batch_results = []
        success_count = 0
        failed_count = 0
        
        # 批量处理回退
        for chunk_id in chunk_ids:
            try:
                # 验证块是否存在
                chunk = db.query(DocumentChunk).filter(
                    DocumentChunk.id == chunk_id,
                    DocumentChunk.document_id == document_id
                ).first()
                
                if not chunk:
                    batch_results.append({
                        "chunk_id": chunk_id,
                        "success": False,
                        "error": "块不存在"
                    })
                    failed_count += 1
                    continue
                
                # 执行回退
                revert_result = version_service.revert_chunk_to_previous_version(chunk_id)
                
                batch_results.append({
                    "chunk_id": chunk_id,
                    "success": True,
                    "task_id": revert_result.task_id,
                    "from_version": revert_result.from_version,
                    "to_version": revert_result.to_version
                })
                success_count += 1
                
            except Exception as e:
                logger.error(f"块 {chunk_id} 回退失败: {e}")
                batch_results.append({
                    "chunk_id": chunk_id,
                    "success": False,
                    "error": str(e)
                })
                failed_count += 1
        
        result = {
            "document_id": document_id,
            "total_chunks": len(chunk_ids),
            "success_count": success_count,
            "failed_count": failed_count,
            "batch_results": batch_results,
            "message": f"批量回退完成，成功 {success_count}/{len(chunk_ids)} 个块"
        }
        
        logger.info(f"API响应: 批量回退完成 document_id={document_id}, 成功 {success_count}/{len(chunk_ids)}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批量回退API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"批量回退失败: {str(e)}"
        )

@router.get("/{document_id}/chunks/{chunk_id}/versions/{version1}/compare/{version2}")
def compare_chunk_versions(
    document_id: int,
    chunk_id: int,
    version1: int,
    version2: int,
    db: Session = Depends(get_db)
):
    """比较块版本 - 根据设计文档实现"""
    try:
        logger.info(f"API请求: 比较块版本 document_id={document_id}, chunk_id={chunk_id}, v1={version1}, v2={version2}")
        
        # 验证文档和块是否存在
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise create_document_not_found_error(document_id)
        
        chunk = db.query(DocumentChunk).filter(
            DocumentChunk.id == chunk_id,
            DocumentChunk.document_id == document_id
        ).first()
        
        if not chunk:
            raise create_chunk_not_found_error(chunk_id)
        
        # 获取两个版本
        version_service = ChunkVersionService(db)
        version1_data = version_service.get_chunk_version(chunk_id, version1)
        version2_data = version_service.get_chunk_version(chunk_id, version2)
        
        if not version1_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"版本 {version1} 不存在"
            )
        
        if not version2_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"版本 {version2} 不存在"
            )
        
        # 计算差异和相似度 - 使用DiffAnalysisService
        diff_service = DiffAnalysisService()
        compare_result = diff_service.compare_versions(
            version1_content=version1_data.content,
            version2_content=version2_data.content
        )
        
        # 构建比较结果
        comparison_result = {
                "chunk_id": chunk_id,
                "version1": {
                    "version_number": version1,
                    "content": version1_data.content,
                    "created_at": version1_data.created_at.isoformat(),
                    "modified_by": version1_data.modified_by,
                    "version_comment": version1_data.version_comment
                },
                "version2": {
                    "version_number": version2,
                    "content": version2_data.content,
                    "created_at": version2_data.created_at.isoformat(),
                    "modified_by": version2_data.modified_by,
                    "version_comment": version2_data.version_comment
                },
                "differences": {
                    "added_lines": compare_result["added_lines"],
                    "removed_lines": compare_result["removed_lines"],
                    "modified_lines": compare_result["modified_lines"],
                    "total_changes": compare_result["total_changes"],
                    "similarity_score": compare_result["similarity_score"]
                },
                "comparison_time": datetime.now().isoformat() + "Z"
            }
        
        logger.info(f"API响应: 版本比较完成 document_id={document_id}, chunk_id={chunk_id}")
        return comparison_result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"版本比较API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"版本比较失败: {str(e)}"
        )

@router.get("/{document_id}/consistency-check")
def check_document_consistency(
    document_id: int,
    db: Session = Depends(get_db)
):
    """检查文档数据一致性 - 根据文档修改功能设计实现"""
    try:
        logger.info(f"API请求: 检查文档一致性 document_id={document_id}")
        
        # 验证文档是否存在
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            logger.warning(f"文档不存在: {document_id}")
            raise create_document_not_found_error(document_id)
        
        # 实现一致性检查逻辑 - 使用ConsistencyCheckService
        from app.services.consistency_check_service import ConsistencyCheckService
        
        consistency_service = ConsistencyCheckService(db)
        check_result = consistency_service.check_document_consistency(document_id)
        
        result = {
            "status": "success",
            "data": check_result
        }
        
        logger.info(f"API响应: 一致性检查完成 document_id={document_id}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"一致性检查API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"一致性检查失败: {str(e)}"
        )

@router.post("/{document_id}/consistency-repair")
def repair_document_consistency(
    document_id: int,
    db: Session = Depends(get_db)
):
    """修复文档数据不一致问题 - 根据文档修改功能设计实现"""
    try:
        logger.info(f"API请求: 修复文档一致性 document_id={document_id}")
        
        # 验证文档是否存在
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            logger.warning(f"文档不存在: {document_id}")
            raise create_document_not_found_error(document_id)
        
        # 实现一致性修复逻辑 - 使用ConsistencyRepairService
        from app.services.consistency_repair_service import ConsistencyRepairService
        
        repair_service = ConsistencyRepairService(db)
        result = repair_service.repair_document_consistency(document_id)
        
        logger.info(f"API响应: 一致性修复完成 document_id={document_id}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"一致性修复API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"一致性修复失败: {str(e)}"
        )
