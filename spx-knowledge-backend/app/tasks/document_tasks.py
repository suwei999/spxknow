"""
Document Processing Tasks
"""

import os
import tempfile
from celery import current_task
from app.tasks.celery_app import celery_app
from app.services.unstructured_service import UnstructuredService
from app.services.vector_service import VectorService
from app.services.cache_service import CacheService
from app.services.opensearch_service import OpenSearchService
from app.services.minio_storage_service import MinioStorageService
from app.models.document import Document
from app.models.chunk import DocumentChunk
from sqlalchemy.orm import Session
from app.config.database import SessionLocal
from app.core.logging import logger
from app.core.constants import DOC_STATUS_PARSING, DOC_STATUS_CHUNKING, DOC_STATUS_VECTORIZING, DOC_STATUS_INDEXING, DOC_STATUS_COMPLETED, DOC_STATUS_FAILED

@celery_app.task(bind=True)
def process_document_task(self, document_id: int):
    """处理文档任务 - 根据文档处理流程设计实现"""
    db = SessionLocal()
    document = None
    
    try:
        logger.info(f"开始处理文档 {document_id}")
        
        # 更新任务状态
        current_task.update_state(
            state="PROGRESS",
            meta={"current": 0, "total": 100, "status": "开始处理文档"}
        )
        
        # 获取文档
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            logger.error(f"文档 {document_id} 不存在")
            raise Exception(f"文档 {document_id} 不存在")
        
        logger.info(f"找到文档 {document_id}: {document.original_filename}")
        
        # 更新文档状态为解析中
        document.status = DOC_STATUS_PARSING
        document.processing_progress = 10.0
        db.commit()
        
        current_task.update_state(
            state="PROGRESS",
            meta={"current": 10, "total": 100, "status": "下载文件到临时目录"}
        )
        
        # 1. 下载文件到临时目录 - 根据设计文档实现
        logger.info(f"开始下载文件 {document.file_path} 到临时目录")
        minio_service = MinioStorageService()
        file_content = minio_service.download_file(document.file_path)
        
        # 创建临时文件
        temp_dir = tempfile.mkdtemp()
        file_extension = os.path.splitext(document.original_filename)[1].lstrip('.')
        temp_file_path = os.path.join(temp_dir, f"{document_id}.{file_extension}")
        
        with open(temp_file_path, 'wb') as f:
            f.write(file_content)
        
        logger.info(f"文件已下载到临时目录: {temp_file_path}")
        
        current_task.update_state(
            state="PROGRESS",
            meta={"current": 15, "total": 100, "status": "开始解析文档"}
        )
        
        # 2. 解析文档 - 根据设计文档实现
        unstructured_service = UnstructuredService(db)
        
        # 根据文件类型选择解析策略
        strategy = unstructured_service._select_parsing_strategy(document.file_type)
        logger.info(f"选择解析策略: {strategy}")
        
        parse_result = unstructured_service.parse_document(temp_file_path, strategy=strategy)
        
        # 3. 清理临时文件
        try:
            os.remove(temp_file_path)
            os.rmdir(temp_dir)
            logger.info("临时文件已清理")
        except Exception as e:
            logger.warning(f"清理临时文件失败: {e}")
        
        logger.info(f"文档 {document_id} 解析完成，提取到 {len(parse_result.get('text_content', ''))} 字符")
        
        current_task.update_state(
            state="PROGRESS",
            meta={"current": 30, "total": 100, "status": "文档解析完成"}
        )
        
        # 更新文档状态为分块中
        document.status = DOC_STATUS_CHUNKING
        document.processing_progress = 40.0
        db.commit()
        
        # 创建文档分块
        chunks = unstructured_service.chunk_text(parse_result.get("text_content", ""))
        
        logger.info(f"文档 {document_id} 分块完成，共 {len(chunks)} 个分块")
        
        for i, chunk_content in enumerate(chunks):
            chunk = DocumentChunk(
                document_id=document_id,
                content=chunk_content,
                chunk_index=i,
                chunk_type="text"
            )
            db.add(chunk)
        
        db.commit()
        
        current_task.update_state(
            state="PROGRESS",
            meta={"current": 60, "total": 100, "status": "文档分块完成"}
        )
        
        # 更新文档状态为向量化中
        document.status = DOC_STATUS_VECTORIZING
        document.processing_progress = 70.0
        db.commit()
        
        # 向量化处理
        vector_service = VectorService(db)
        chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).all()
        
        logger.info(f"开始向量化文档 {document_id} 的 {len(chunks)} 个分块")
        
        # 初始化OpenSearch服务
        opensearch_service = OpenSearchService()
        
        # 批量生成向量并存储到OpenSearch
        for i, chunk in enumerate(chunks):
            vector = vector_service.generate_embedding(chunk.content)
            
            # 构建索引文档
            chunk_doc = {
                "document_id": document_id,
                "chunk_id": chunk.id,
                "knowledge_base_id": document.knowledge_base_id,
                "category_id": document.category_id if hasattr(document, 'category_id') else None,
                "content": chunk.content,
                "chunk_type": chunk.chunk_type if hasattr(chunk, 'chunk_type') else "text",
                "metadata": {"chunk_index": i},
                "vector": vector,
                "created_at": chunk.created_at.isoformat() if chunk.created_at else None
            }
            
            # 存储到OpenSearch
            try:
                opensearch_service.index_document_chunk(chunk_doc)
                logger.debug(f"分块 {chunk.id} 向量化完成，向量维度: {len(vector)}")
            except Exception as e:
                logger.error(f"存储分块 {chunk.id} 到OpenSearch失败: {e}", exc_info=True)
                raise e
            
            # 更新任务进度
            progress = 60 + (i / len(chunks)) * 30
            current_task.update_state(
                state="PROGRESS",
                meta={"current": int(progress), "total": 100, "status": f"向量化中 ({i+1}/{len(chunks)})"}
            )
        
        logger.info(f"文档 {document_id} 向量化完成")
        
        current_task.update_state(
            state="PROGRESS",
            meta={"current": 90, "total": 100, "status": "向量化完成，开始建立索引"}
        )
        
        # 更新文档状态为索引中
        document.status = DOC_STATUS_INDEXING
        document.processing_progress = 95.0
        db.commit()
        
        # OpenSearch索引已在上面的循环中建立
        logger.info(f"文档 {document_id} 索引建立完成")
        
        # 更新文档状态为完成
        document.status = DOC_STATUS_COMPLETED
        document.processing_progress = 100.0
        db.commit()
        
        logger.info(f"文档 {document_id} 处理完成")
        
        current_task.update_state(
            state="SUCCESS",
            meta={"current": 100, "total": 100, "status": "文档处理完成"}
        )
        
        return {"status": "success", "message": "文档处理完成"}
        
    except Exception as e:
        logger.error(f"文档 {document_id} 处理失败: {str(e)}", exc_info=True)
        
        # 更新文档状态为失败
        if document:
            document.status = DOC_STATUS_FAILED
            document.error_message = str(e)
            db.commit()
        
        current_task.update_state(
            state="FAILURE",
            meta={"error": str(e)}
        )
        raise e
    finally:
        db.close()

@celery_app.task(bind=True)
def reprocess_document_task(self, document_id: int):
    """重新向量化文档 - 根据文档修改功能设计实现"""
    db = SessionLocal()
    
    try:
        logger.info(f"开始重新向量化文档 {document_id}")
        
        # 获取文档
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            logger.error(f"文档 {document_id} 不存在")
            raise Exception(f"文档 {document_id} 不存在")
        
        logger.info(f"找到文档 {document_id}: {document.original_filename}")
        
        # 更新文档状态为向量化中
        document.status = DOC_STATUS_VECTORIZING
        document.processing_progress = 50.0
        db.commit()
        
        # 获取所有块（不重新解析文件）
        chunks = db.query(DocumentChunk).filter(
            DocumentChunk.document_id == document_id
        ).all()
        
        logger.info(f"文档 {document_id} 共有 {len(chunks)} 个块需要重新向量化")
        
        # 向量化处理
        vector_service = VectorService(db)
        opensearch_service = OpenSearchService()
        
        for i, chunk in enumerate(chunks):
            # 生成向量
            vector = vector_service.generate_embedding(chunk.content)
            
            # 构建索引文档
            chunk_doc = {
                "document_id": document_id,
                "chunk_id": chunk.id,
                "knowledge_base_id": document.knowledge_base_id,
                "category_id": document.category_id if hasattr(document, 'category_id') else None,
                "content": chunk.content,
                "chunk_type": chunk.chunk_type if hasattr(chunk, 'chunk_type') else "text",
                "metadata": getattr(chunk, 'meta', getattr(chunk, 'metadata', {})),
                "vector": vector,
                "version": chunk.version if hasattr(chunk, 'version') else 1,
                "created_at": chunk.created_at.isoformat() if chunk.created_at else None
            }
            
            # 更新OpenSearch索引
            try:
                opensearch_service.index_document_chunk(chunk_doc)
                logger.debug(f"分块 {chunk.id} 重新向量化完成")
            except Exception as e:
                logger.error(f"存储分块 {chunk.id} 到OpenSearch失败: {e}", exc_info=True)
                raise e
        
        logger.info(f"文档 {document_id} 重新向量化完成")
        
        # 更新文档状态为完成
        document.status = DOC_STATUS_COMPLETED
        document.processing_progress = 100.0
        db.commit()
        
        return {"status": "success", "message": "重新向量化完成", "chunks_count": len(chunks)}
        
    except Exception as e:
        logger.error(f"重新向量化文档 {document_id} 失败: {str(e)}", exc_info=True)
        
        # 更新文档状态为失败
        if document:
            document.status = DOC_STATUS_FAILED
            document.error_message = str(e)
            db.commit()
        
        raise e
    finally:
        db.close()

@celery_app.task
def delete_document_task(document_id: int):
    """删除文档任务"""
    db = SessionLocal()
    try:
        # 获取文档
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            return {"status": "error", "message": "文档不存在"}
        
        # 删除相关数据
        db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete()
        
        # 软删除文档
        document.is_deleted = True
        db.commit()
        
        return {"status": "success", "message": "文档删除完成"}
        
    except Exception as e:
        db.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        db.close()
