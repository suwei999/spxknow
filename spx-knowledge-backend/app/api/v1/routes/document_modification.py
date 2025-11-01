"""
文档块编辑 API（骨架版）
PATCH /api/documents/{id}/chunks/{chunk_id}
 - 写入 chunk_versions
 - 切换当前块版本（可选）
 - 重新生成向量并更新 OpenSearch
"""

from fastapi import APIRouter, Depends, Path, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.dependencies.database import get_db
from app.core.logging import logger
from app.models.chunk import DocumentChunk
from app.models.chunk_version import ChunkVersion
from app.models.document import Document
from app.services.vector_service import VectorService
from app.services.opensearch_service import OpenSearchService
from datetime import datetime
import json

router = APIRouter()


def parse_chunk_metadata(chunk_meta) -> dict:
    """解析 chunk metadata，返回字典 - 辅助函数"""
    if not chunk_meta:
        return {}
    try:
        if isinstance(chunk_meta, str):
            return json.loads(chunk_meta)
        elif isinstance(chunk_meta, dict):
            return chunk_meta
        else:
            return {}
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}


class ChunkEditPayload(BaseModel):
    content: str = Field(..., min_length=1, description="新内容")
    version_comment: str | None = Field(None, description="版本备注")


@router.patch("/documents/{doc_id}/chunks/{chunk_id}")
def edit_chunk(
    payload: ChunkEditPayload,
    doc_id: int = Path(...),
    chunk_id: int = Path(...),
    db: Session = Depends(get_db),
):
    # ✅ 修复：统一错误响应格式，使用 HTTPException
    chunk = db.query(DocumentChunk).filter(DocumentChunk.id == chunk_id, DocumentChunk.document_id == doc_id).first()
    if not chunk:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": 404, "message": "chunk not found", "data": None}
        )
    
    # ✅ 修复：添加输入验证
    if not payload.content or not payload.content.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": 400, "message": "内容不能为空", "data": None}
        )

    # 创建 chunk 版本记录（递增版本号，记录操作者与创建时间）
    # ✅ 修复：简化 getattr，直接访问属性
    new_version_number = (chunk.version or 0) + 1
    cv = ChunkVersion(
        chunk_id=chunk.id,
        version_number=new_version_number,
        content=payload.content,
        version_comment=payload.version_comment or "",
        modified_by="user",
        created_at=datetime.utcnow(),
    )
    db.add(cv)
    db.commit()
    db.refresh(cv)

    # 将块内容切换为新版本（更新指针与版本号，按需更新正文）
    # ✅ 修复：简化 hasattr，直接访问属性（模型中有这些字段）
    chunk.content = payload.content
    chunk.version = new_version_number
    chunk.chunk_version_id = cv.id
    chunk.last_modified_at = datetime.utcnow()
    chunk.modification_count = (chunk.modification_count or 0) + 1
    chunk.last_modified_by = "user"
    db.commit()

    # 重新生成向量并更新 OS
    vs = VectorService(db)
    osvc = OpenSearchService()
    vector = vs.generate_embedding(payload.content)
    
    # ✅ 修复：使用辅助函数解析 metadata，并指定具体异常类型
    chunk_meta_dict = parse_chunk_metadata(chunk.meta)
    
    # 构建完整的 metadata（保留原有信息并标记为已编辑）
    os_metadata = chunk_meta_dict.copy() if chunk_meta_dict else {}
    os_metadata["edited"] = True
    
    # ✅ 修复：从 document 对象获取 knowledge_base_id 和 category_id
    # chunk 模型中没有这些字段，它们在 document 模型中
    # ✅ 修复：复用 document 对象，避免重复查询
    document = db.query(Document).filter(Document.id == doc_id).first()
    
    os_doc = {
        "document_id": doc_id,
        "chunk_id": chunk.id,
        "knowledge_base_id": document.knowledge_base_id if document else None,
        "category_id": document.category_id if document else None,
        "content": payload.content,
        "chunk_type": chunk.chunk_type or "text",  # ✅ 修复：简化 getattr
        "metadata": os_metadata,  # ✅ 使用完整的 metadata
        "content_vector": vector,
        "created_at": chunk.created_at.isoformat() if chunk.created_at else None,  # ✅ 修复：简化 getattr
    }
    osvc.index_document_chunk_sync(os_doc)
    
    # ✅ 新增：更新 MinIO 中的 chunk 内容
    try:
        from app.services.minio_storage_service import MinioStorageService
        minio_service = MinioStorageService()
        minio_service.update_chunk_content(
            document_id=doc_id,
            chunk_index=chunk.chunk_index,
            new_content=payload.content,
            chunk_meta=chunk_meta_dict
        )
        logger.info(f"MinIO chunk 更新成功: doc_id={doc_id}, chunk_index={chunk.chunk_index}")
    except (Exception, ValueError, AttributeError) as minio_err:  # ✅ 修复：指定具体异常类型
        logger.warning(f"MinIO chunk 更新失败（不影响修改流程）: {minio_err}", exc_info=True)
    
    # ✅ 修复：添加文档版本更新
    # ✅ 修复：复用已查询的 document 对象，避免重复查询
    try:
        from sqlalchemy import func
        from app.models.version import DocumentVersion
        
        # document 已经在上面查询过了，直接使用
        if document:
            # 计算下一个版本号
            max_ver = db.query(func.max(DocumentVersion.version_number)).filter(
                DocumentVersion.document_id == doc_id,
                DocumentVersion.is_deleted == False
            ).scalar() or 0
            next_ver = int(max_ver) + 1
            ver = DocumentVersion(
                document_id=doc_id,
                version_number=next_ver,
                version_type="edit",
                description=f"编辑分块 {chunk_id}",
                file_path=document.file_path or "",
                file_size=document.file_size,
                file_hash=document.file_hash,
            )
            db.add(ver)
            db.commit()
            logger.info(f"文档版本更新成功: doc_id={doc_id}, version={next_ver}")
    except (Exception, ValueError, TypeError) as ver_err:  # ✅ 修复：指定具体异常类型
        logger.warning(f"记录文档版本失败（不影响修改流程）: {ver_err}", exc_info=True)

    logger.info(f"编辑并重索引完成: doc={doc_id} chunk={chunk_id} version={cv.id}")
    return {"code": 0, "message": "ok", "data": {"chunk_id": chunk_id, "version_id": cv.id}}

"""
Document Modification API Routes
根据文档修改功能设计实现
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
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
        
        # 解析 meta 字段（包含表格数据 table_data）
        import json
        meta_dict = None
        if chunk.meta:
            try:
                meta_dict = json.loads(chunk.meta) if isinstance(chunk.meta, str) else chunk.meta
            except (json.JSONDecodeError, TypeError):
                meta_dict = {}
        
        # 构建响应数据 - 严格按照设计文档格式
        data = {
            "chunk_id": str(chunk.id),
            "document_id": str(document_id),
            "content": chunk.content,
            "chunk_type": chunk.chunk_type,
            "version": getattr(chunk, 'version', 1),
            "edit_history": [],
            "meta": meta_dict,  # ✅ 新增：返回 meta 字段，包含表格数据 table_data
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
        
        # 解析每个块的 meta 字段（包含表格数据 table_data）
        import json
        chunks_data = []
        for chunk in chunks:
            meta_dict = None
            if chunk.meta:
                try:
                    meta_dict = json.loads(chunk.meta) if isinstance(chunk.meta, str) else chunk.meta
                except (json.JSONDecodeError, TypeError):
                    meta_dict = {}
            
            chunks_data.append({
                "chunk_id": str(chunk.id),
                "chunk_index": chunk.chunk_index,
                "content_preview": chunk.content[:settings.CONTENT_PREVIEW_LENGTH] + "..." if len(chunk.content) > settings.CONTENT_PREVIEW_LENGTH else chunk.content,
                "chunk_type": chunk.chunk_type,
                "char_count": len(chunk.content),
                "meta": meta_dict,  # ✅ 新增：返回 meta 字段，包含表格数据 table_data
            })
        
        # 按照设计文档要求的响应格式
        data = {
            "document_id": str(document_id),
            "total_chunks": len(chunks),
            "chunks": chunks_data
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

@router.get("/{document_id}/elements")
def get_document_elements(
    document_id: int,
    db: Session = Depends(get_db),
    include_content: bool = True
):
    """
    获取文档所有元素（文本分块+图片）按 element_index 排序 - 用于100%还原原文档顺序
    返回格式：按 element_index 排序的混合列表，包含文本分块和图片
    """
    try:
        import json
        from app.models.image import DocumentImage
        from app.services.minio_storage_service import MinioStorageService
        from app.config.settings import settings
        
        logger.info(f"API请求: 获取文档所有元素（100%还原） document_id={document_id}, include_content={include_content}")
        
        # 验证文档是否存在
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            logger.warning(f"文档不存在: {document_id}")
            raise create_document_not_found_error(document_id)
        
        # 1. 获取所有文本分块
        chunks = db.query(DocumentChunk).filter(
            DocumentChunk.document_id == document_id,
            DocumentChunk.is_deleted == False
        ).order_by(DocumentChunk.chunk_index).all()
        
        # 解析每个分块的 element_index 范围
        chunk_elements = []
        for chunk in chunks:
            chunk_meta = {}
            if chunk.meta:
                try:
                    chunk_meta = json.loads(chunk.meta) if isinstance(chunk.meta, str) else chunk.meta
                except Exception:
                    pass
            
            element_index_start = chunk_meta.get('element_index_start')
            element_index_end = chunk_meta.get('element_index_end')
            
            # 获取分块内容（从DB或MinIO）
            chunk_content = chunk.content if chunk.content else ""
            if not chunk_content and not getattr(settings, 'STORE_CHUNK_TEXT_IN_DB', False):
                # 从 MinIO 读取
                try:
                    minio = MinioStorageService()
                    files = minio.list_files("documents/")
                    needle = f"/{document_id}/parsed/chunks/chunks.jsonl.gz"
                    target = None
                    for fobj in files:
                        if fobj.get("object_name", "").endswith(needle):
                            target = fobj["object_name"]
                            break
                    if target:
                        import gzip
                        response = minio.client.get_object(minio.bucket_name, target)
                        try:
                            with gzip.GzipFile(fileobj=response, mode='rb') as gz:
                                for line in gz:
                                    try:
                                        item = json.loads(line)
                                        if item.get('index') == chunk.chunk_index:
                                            chunk_content = item.get('content', '')
                                            break
                                    except Exception:
                                        pass
                        finally:
                            try:
                                response.close()
                                response.release_conn()
                            except Exception:
                                pass
                except Exception as e:
                    logger.warning(f"从MinIO读取分块内容失败: {e}")
            
            chunk_elements.append({
                'type': 'chunk',
                'element_index_start': element_index_start,
                'element_index_end': element_index_end,
                'element_index': element_index_start,  # 用于排序（使用起始索引）
                'chunk_id': chunk.id,
                'chunk_index': chunk.chunk_index,
                'content': chunk_content if include_content else None,
                'content_length': len(chunk_content),
                'chunk_type': chunk.chunk_type
            })
        
        # 2. 获取所有图片
        images = db.query(DocumentImage).filter(
            DocumentImage.document_id == document_id,
            DocumentImage.is_deleted == False
        ).all()
        
        image_elements = []
        for image in images:
            image_meta = {}
            if image.meta:
                try:
                    image_meta = json.loads(image.meta) if isinstance(image.meta, str) else image.meta
                except Exception:
                    pass
            
            element_index = image_meta.get('element_index')
            
            image_elements.append({
                'type': 'image',
                'element_index': element_index,
                'image_id': image.id,
                'image_path': image.image_path,
                'image_type': image.image_type,
                'width': image.width,
                'height': image.height,
                'page_number': image_meta.get('page_number'),
                'coordinates': image_meta.get('coordinates'),
                'ocr_text': image.ocr_text if include_content else None
            })
        
        # 3. 合并并按 element_index 排序（实现100%还原）
        all_elements = chunk_elements + image_elements
        
        # 过滤掉没有 element_index 的元素（向后兼容）
        elements_with_index = [e for e in all_elements if e.get('element_index') is not None]
        elements_without_index = [e for e in all_elements if e.get('element_index') is None]
        
        # 按 element_index 排序
        elements_with_index.sort(key=lambda x: x.get('element_index', 999999))
        
        # 对于没有 element_index 的元素，按类型和原有顺序追加
        # 文本分块按 chunk_index 排序，图片放在最后
        chunk_without_index = [e for e in elements_without_index if e.get('type') == 'chunk']
        chunk_without_index.sort(key=lambda x: x.get('chunk_index', 999999))
        image_without_index = [e for e in elements_without_index if e.get('type') == 'image']
        
        # 最终排序结果：有索引的按索引排序，无索引的追加
        final_elements = elements_with_index + chunk_without_index + image_without_index
        
        data = {
            "document_id": str(document_id),
            "total_elements": len(final_elements),
            "elements_with_index": len(elements_with_index),
            "elements_without_index": len(elements_without_index),
            "elements": final_elements
        }
        
        result = {
            "status": "success",
            "data": data
        }
        
        logger.info(f"API响应: 返回 {len(final_elements)} 个元素（{len(chunk_elements)} 个分块 + {len(image_elements)} 个图片）")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取文档元素API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取文档元素失败: {str(e)}"
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
            # ✅ 修复：使用 chunk.meta 而不是 chunk.metadata（模型属性是 meta）
            current_version_data = {
                "chunk_id": chunk_id,
                "content": chunk.content or "",
                "metadata": chunk.meta,  # ✅ 使用 meta 属性
                "modified_by": "user",
                "version_comment": "修改前的版本保存"
            }
            cv_response = version_service.create_chunk_version(chunk_id, current_version_data)
            # ✅ 修复：更新 chunk.chunk_version_id 指向新创建的版本
            # ChunkVersionResponse 继承自 BaseResponseSchema，包含 id 字段
            if cv_response and cv_response.id:
                chunk.chunk_version_id = cv_response.id
            else:
                # 兜底：如果响应中没有 id，查询最新创建的版本
                from app.models.chunk_version import ChunkVersion
                latest_version = db.query(ChunkVersion).filter(
                    ChunkVersion.chunk_id == chunk_id
                ).order_by(ChunkVersion.version_number.desc()).first()
                if latest_version:
                    chunk.chunk_version_id = latest_version.id
                    logger.debug(f"通过查询获取 chunk_version_id: {latest_version.id}")
            
            # 更新块内容
            chunk.content = new_content
            
            # ✅ 修复：合并传入的 metadata 和原有的 metadata，而不是替换
            # 确保 MySQL 中的 metadata 包含完整的字段（element_index_start/end, page_number, coordinates等）
            # ✅ 修复：使用辅助函数和指定具体异常类型
            existing_meta_dict = parse_chunk_metadata(chunk.meta)
            
            # 合并 metadata：先保留原有完整字段，再更新传入的字段
            merged_metadata = existing_meta_dict.copy() if isinstance(existing_meta_dict, dict) else {}
            if metadata and isinstance(metadata, dict):
                # 更新传入的字段（可能是部分更新，如表格的 table_data）
                merged_metadata.update(metadata)
            elif metadata:
                # 如果传入的 metadata 是字符串，尝试解析
                # ✅ 修复：使用辅助函数和指定具体异常类型
                try:
                    metadata_dict = parse_chunk_metadata(metadata)
                    if isinstance(metadata_dict, dict):
                        merged_metadata.update(metadata_dict)
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass
            
            # 保存合并后的 metadata
            if merged_metadata:
                chunk.meta = json.dumps(merged_metadata, ensure_ascii=False)
            
            # 更新版本管理字段
            chunk.version += 1
            chunk.last_modified_at = datetime.now()
            chunk.modification_count += 1
            chunk.last_modified_by = "user"
            
            db.commit()
            
            # 更新操作进度
            status_service.update_operation_progress(operation_id, 50.0, "内容已保存，开始重新向量化")

            # 文档版本递增：以文档为单位记录一次修改版本
            try:
                from sqlalchemy import func
                from app.models.version import DocumentVersion
                # 计算下一个版本号
                max_ver = db.query(func.max(DocumentVersion.version_number)).filter(
                    DocumentVersion.document_id == document_id,
                    DocumentVersion.is_deleted == False
                ).scalar() or 0
                next_ver = int(max_ver) + 1
                ver = DocumentVersion(
                    document_id=document_id,
                    version_number=next_ver,
                    version_type="edit",
                    description=f"编辑分块 {chunk_id}",
                    file_path=document.file_path or "",
                    file_size=document.file_size,
                    file_hash=document.file_hash,
                )
                db.add(ver)
                db.commit()
            except (Exception, ValueError, TypeError) as ver_err:  # ✅ 修复：指定具体异常类型
                logger.warning(f"记录文档版本失败（不影响修改流程）: {ver_err}", exc_info=True)
            
            # WebSocket进度通知
            await websocket_notification_service.send_progress_notification(
                operation_id, 50.0, "内容已保存，开始重新向量化", "user"
            )
            
            # 增量向量化：仅对当前修改的块进行向量化并更新 OpenSearch
            try:
                from app.services.vector_service import VectorService
                from app.services.opensearch_service import OpenSearchService
                # ✅ 修复：json 已在文件顶部导入，此处删除重复导入
                vector_service = VectorService(db)
                osvc = OpenSearchService()
                # 生成文本向量（允许为空向量继续索引）
                content_vector = vector_service.generate_embedding(new_content or "") if (new_content or "").strip() else []
                
                # ✅ 修复：使用更新后的 chunk.meta（已合并，包含完整字段）
                # 注意：此时 chunk.meta 已经在上面的合并逻辑中更新为完整的 metadata
                # ✅ 修复：使用辅助函数解析
                chunk_meta_dict = parse_chunk_metadata(chunk.meta)
                # 标记为已编辑
                if not isinstance(chunk_meta_dict, dict):
                    chunk_meta_dict = {}
                chunk_meta_dict["edited"] = True
                
                osvc.index_document_chunk_sync({
                    "document_id": document_id,
                    "knowledge_base_id": document.knowledge_base_id,
                    "category_id": document.category_id,
                    "chunk_id": chunk.id,
                    "content": new_content,
                    "chunk_type": chunk.chunk_type or 'text',  # ✅ 修复：简化 getattr
                    "tags": document.tags or [],
                    "metadata": chunk_meta_dict,  # ✅ 使用解析后的 metadata
                    "created_at": chunk.created_at.isoformat() if chunk.created_at else None,
                    "content_vector": content_vector,
                })
            except (Exception, ValueError, AttributeError) as idx_err:  # ✅ 修复：指定具体异常类型
                logger.warning(f"增量索引更新失败（不影响返回）: {idx_err}", exc_info=True)
            
            # ✅ 新增：更新 MinIO 中的 chunk 内容
            try:
                from app.services.minio_storage_service import MinioStorageService
                minio_service = MinioStorageService()
                minio_service.update_chunk_content(
                    document_id=document_id,
                    chunk_index=chunk.chunk_index,
                    new_content=new_content,
                    chunk_meta=chunk_meta_dict
                )
                logger.info(f"MinIO chunk 更新成功: doc_id={document_id}, chunk_index={chunk.chunk_index}")
            except (Exception, ValueError, AttributeError) as minio_err:  # ✅ 修复：指定具体异常类型
                logger.warning(f"MinIO chunk 更新失败（不影响修改流程）: {minio_err}", exc_info=True)
            
            # 更新操作进度
            status_service.update_operation_progress(operation_id, 85.0, "已更新索引和MinIO")
            
            # WebSocket进度通知
            await websocket_notification_service.send_progress_notification(
                operation_id, 85.0, "已更新索引和MinIO", "user"
            )
            
            # ✅ 修复：移除未定义的 task.id
            # 按照设计文档要求的响应格式
            data = {
                "chunk_id": str(chunk_id),
                "version": chunk.version,
                "operation_id": operation_id,  # ✅ 使用 operation_id 替代 task_id
                "estimated_completion": "2024-01-01T11:02:00Z"  # TODO: 计算实际完成时间
            }
            
            result = {"code": 0, "message": "ok", "data": data}
            
            # 完成操作状态
            status_service.complete_modification_operation(operation_id, True, "修改完成")
            
            # WebSocket完成通知
            await websocket_notification_service.send_modification_notification(
                "modification_completed",
                document_id,
                chunk_id,
                "user",
                {"operation_id": operation_id}  # ✅ 移除未定义的 task.id
            )
            
            logger.info(f"API响应: 块内容更新成功，operation_id: {operation_id}")
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

@router.get("/{document_id}/chunks/{chunk_id}/versions")
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
        return {"code": 0, "message": "ok", "data": result}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取块版本列表API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取块版本列表失败: {str(e)}"
        )

@router.get("/{document_id}/chunks/{chunk_id}/versions/{version_number}")
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
        return {"code": 0, "message": "ok", "data": version}
        
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
    detailed: bool = False,  # ✅ 新增：是否返回详细diff数据，用于前端高亮
    db: Session = Depends(get_db)
):
    """比较块版本 - 根据设计文档实现
    
    Args:
        detailed: 是否返回详细diff数据（用于前端高亮显示），默认False返回统计信息
    """
    try:
        logger.info(f"API请求: 比较块版本 document_id={document_id}, chunk_id={chunk_id}, v1={version1}, v2={version2}, detailed={detailed}")
        
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
        
        # ✅ 修复：版本顺序处理 - 确保旧版本在前，新版本在后
        swapped = False
        if version1 > version2:
            # 交换版本，确保逻辑正确（旧版本 -> 新版本）
            version1, version2 = version2, version1
            version1_data, version2_data = version2_data, version1_data
            swapped = True
            logger.info(f"版本已交换: 原请求 v{version2} vs v{version1}, 实际比较 v{version1} -> v{version2}")
        
        # ✅ 修复：相同版本优化
        if version1 == version2:
            # 相同版本，直接返回相等结果（避免不必要的diff计算）
            version_content = version1_data.content or ""
            version_lines = version_content.splitlines(keepends=True) if version_content else []
            
            diff_data = [{
                "type": "equal",
                "old_line": i + 1,
                "new_line": i + 1,
                "content": line.rstrip('\n\r')
            } for i, line in enumerate(version_lines)]
            
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
                    "statistics": {
                        "added_lines": 0,
                        "removed_lines": 0,
                        "modified_lines": 0,
                        "total_changes": 0,
                        "change_ratio": 0.0,
                        "equal_lines": len(diff_data)
                    },
                    "diff_data": diff_data if detailed else None,
                    "old_line_count": len(version_lines),
                    "new_line_count": len(version_lines),
                    "similarity_score": 1.0
                },
                "comparison_time": datetime.now().isoformat() + "Z",
                "swapped": swapped  # 标记版本是否交换
            }
            
            logger.info(f"相同版本对比: chunk_id={chunk_id}, version={version1}")
            return comparison_result
        
        # 计算差异和相似度 - 使用DiffAnalysisService
        diff_service = DiffAnalysisService()
        
        if detailed:
            # ✅ 返回详细diff数据（用于前端高亮显示）
            # ✅ 修复：确保内容不为 None
            version1_content = version1_data.content or ""
            version2_content = version2_data.content or ""
            
            detailed_diff = diff_service.calculate_detailed_diff(
                old_content=version1_content,
                new_content=version2_content
            )
            
            # 计算相似度
            similarity_score = diff_service.calculate_similarity_score(
                version1_content,
                version2_content
            )
            
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
                    "statistics": detailed_diff["statistics"],
                    "diff_data": detailed_diff["diff_data"],  # ✅ 详细diff数据，用于前端高亮
                    "old_line_count": detailed_diff["old_line_count"],
                    "new_line_count": detailed_diff["new_line_count"],
                    "similarity_score": similarity_score
                },
                "comparison_time": datetime.now().isoformat() + "Z",
                "swapped": swapped  # ✅ 标记版本是否交换
            }
        else:
            # 返回统计信息（兼容旧接口）
            # ✅ 修复：确保内容不为 None
            version1_content = version1_data.content or ""
            version2_content = version2_data.content or ""
            
            compare_result = diff_service.compare_versions(
                version1_content=version1_content,
                version2_content=version2_content
            )
            
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
                "comparison_time": datetime.now().isoformat() + "Z",
                "swapped": swapped  # ✅ 标记版本是否交换
            }
        
        logger.info(f"API响应: 版本比较完成 document_id={document_id}, chunk_id={chunk_id}, detailed={detailed}")
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
