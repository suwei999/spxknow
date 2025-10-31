"""
Document Service
"""

from typing import List, Optional, Dict, Any
from fastapi import UploadFile
from sqlalchemy.orm import Session
from app.models.document import Document
from app.schemas.document import DocumentCreate, DocumentUpdate
from app.services.base import BaseService
from app.core.logging import logger
from app.tasks.document_tasks import process_document_task
from app.services.file_validation_service import FileValidationService
from app.services.minio_storage_service import MinioStorageService
from app.services.duplicate_detection_service import DuplicateDetectionService
from app.core.exceptions import CustomException, ErrorCode
import os

class DocumentService(BaseService[Document]):
    """文档服务"""
    
    def __init__(self, db: Session):
        super().__init__(db, Document)
        self.file_validation = FileValidationService()
        self.minio_storage = MinioStorageService()
        self.duplicate_detection = DuplicateDetectionService(db)
    
    async def get_documents(
        self, 
        skip: int = 0, 
        limit: int = 100,
        knowledge_base_id: Optional[int] = None
    ) -> List[Document]:
        """获取文档列表 - 根据文档处理流程设计实现"""
        try:
            logger.info(f"获取文档列表，跳过: {skip}, 限制: {limit}, 知识库ID: {knowledge_base_id}")
            
            filters = {}
            if knowledge_base_id:
                filters["knowledge_base_id"] = knowledge_base_id
            
            documents = await self.get_multi(skip=skip, limit=limit, **filters)
            logger.info(f"获取到 {len(documents)} 个文档")
            return documents
            
        except Exception as e:
            logger.error(f"获取文档列表错误: {e}", exc_info=True)
            raise e
    
    async def get_document(self, doc_id: int) -> Optional[Document]:
        """获取文档详情 - 根据文档处理流程设计实现"""
        try:
            logger.info(f"获取文档详情: {doc_id}")
            
            document = await self.get(doc_id)
            if document:
                logger.info(f"找到文档: {document.original_filename}")
            else:
                logger.warning(f"文档不存在: {doc_id}")
            
            return document
            
        except Exception as e:
            logger.error(f"获取文档详情错误: {e}", exc_info=True)
            raise e
    
    async def upload_document(
        self, 
        file: UploadFile, 
        knowledge_base_id: int,
        category_id: Optional[int] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        上传文档 - 严格按照设计文档实现完整流程
        
        支持参数：
        - file: 文件对象
        - knowledge_base_id: 知识库ID（必填）
        - category_id: 分类ID（可选）
        - tags: 标签列表（可选）
        - metadata: 元数据（可选）
        
        返回内容：
        - document_id: 文档ID
        - task_id: 任务ID
        - file_size: 文件大小
        - file_type: 文件类型
        - upload_timestamp: 上传时间戳
        """
        try:
            logger.info(f"开始上传文档: {file.filename}, 知识库ID: {knowledge_base_id}, category_id: {category_id}, tags: {tags}")
            
            # 根据设计文档的完整流程：
            # 选择知识库 → 上传文档 → 格式验证 → 安全扫描 → 重复检测 → 存储文件 → 解析处理
            
            # 1. 文件验证（格式验证、大小检查、安全扫描）
            logger.info("步骤1: 开始文件验证")
            validation_result = self.file_validation.validate_file(file)
            
            if not validation_result["valid"]:
                raise CustomException(
                    code=ErrorCode.VALIDATION_ERROR,
                    message="文件验证失败"
                )
            
            # 2. 重复检测
            logger.info("步骤2: 开始重复检测")
            file_hash = validation_result["hash_calculation"]["sha256_hash"]
            filename = file.filename
            file_size = validation_result["size_validation"]["file_size"]
            
            duplicate_result = self.duplicate_detection.check_duplicate_comprehensive(
                filename, file_size, file_hash
            )
            
            # 处理重复检测结果
            duplicate_action = self.duplicate_detection.handle_duplicate_detection(
                duplicate_result, filename
            )
            
            if duplicate_action["action"] == "warning":
                logger.warning(f"重复检测警告: {duplicate_action['message']}")
            elif duplicate_action["action"] == "reject":
                raise CustomException(
                    code=ErrorCode.DOCUMENT_ALREADY_EXISTS,
                    message=duplicate_action["message"]
                )
            
            # 3. 存储文件到MinIO
            logger.info("步骤3: 开始存储文件到MinIO")
            storage_result = self.minio_storage.upload_original_file(file, file_hash)
            
            # 4. 保存元数据到MySQL
            logger.info("步骤4: 开始保存元数据到MySQL")
            from datetime import datetime
            upload_timestamp = datetime.utcnow().isoformat()
            
            # 补充元数据（默认标题为文件名去扩展名）
            if metadata is None:
                metadata = {}
            if isinstance(metadata, dict) and not metadata.get("title"):
                metadata["title"] = os.path.splitext(file.filename)[0]

            doc_data = {
                "original_filename": file.filename,
                "file_type": validation_result["format_validation"]["file_type"],
                "file_size": file_size,
                "file_hash": file_hash,
                "file_path": storage_result["object_name"],
                "knowledge_base_id": knowledge_base_id,
                "category_id": category_id,
                "tags": tags,
                "metadata": metadata,
                "status": "uploaded",
                "processing_progress": 0.0
            }
            
            document = await self.create(doc_data)
            logger.info(f"文档元数据保存完成，文档ID: {document.id}")
            
            # 5. 触发异步处理任务
            logger.info("步骤5: 触发异步处理任务")
            from app.tasks.document_tasks import process_document_task
            task = process_document_task.delay(document.id)
            logger.info(f"文档处理任务已启动，任务ID: {task.id}")
            
            # 6. 上传元数据到MinIO
            logger.info("步骤6: 上传元数据到MinIO")
            doc_id = f"doc_{file_hash[:8]}"
            metadata_obj = {
                "document_id": document.id,
                "original_filename": file.filename,
                "file_type": validation_result["format_validation"]["file_type"],
                "file_size": file_size,
                "file_hash": file_hash,
                "knowledge_base_id": knowledge_base_id,
                "category_id": category_id,
                "tags": tags,
                "metadata": metadata,
                "validation_result": validation_result,
                "storage_result": storage_result,
                "duplicate_result": duplicate_result,
                "upload_timestamp": upload_timestamp
            }
            
            self.minio_storage.upload_metadata(doc_id, metadata_obj)
            
            logger.info(f"文档上传完成: {file.filename}, 文档ID: {document.id}, 任务ID: {task.id}")
            
            # 返回符合设计文档要求的响应
            return {
                "document_id": document.id,
                "task_id": task.id,
                "file_size": file_size,
                "file_type": validation_result["format_validation"]["file_type"],
                "upload_timestamp": upload_timestamp
            }
            
        except CustomException:
            raise
        except Exception as e:
            logger.error(f"文档上传错误: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.VALIDATION_ERROR,
                message=f"文档上传失败: {str(e)}"
            )
    
    def update_document(
        self, 
        doc_id: int, 
        doc_data: DocumentUpdate
    ) -> Optional[Document]:
        """更新文档 - 根据文档处理流程设计实现"""
        try:
            logger.info(f"更新文档: {doc_id}")
            
            document = self.update(doc_id, doc_data.dict(exclude_unset=True))
            if document:
                logger.info(f"文档更新完成: {document.original_filename}")
            else:
                logger.warning(f"文档不存在: {doc_id}")
            
            return document
            
        except Exception as e:
            logger.error(f"更新文档错误: {e}", exc_info=True)
            raise e
    
    async def delete_document(self, doc_id: int, hard: bool = True) -> bool:
        """删除文档：
        - hard=True：物理删除 MySQL 行，并清理 MinIO 前缀与 OpenSearch 索引
        - hard=False：仅软删除（保留行，仅标记 is_deleted）
        """
        try:
            logger.info(f"删除文档: {doc_id}")
            # 读取文档
            doc = await self.get(doc_id)
            if not doc:
                logger.warning(f"文档不存在: {doc_id}")
                return False

            # 预先计算 MinIO 前缀（兼容两种存储布局：doc_hash 与 数字ID）
            prefixes = []
            if doc.file_path:
                parts = doc.file_path.split("/")  # documents/{year}/{month}/{doc_hash}/original.ext
                if len(parts) >= 4:
                    year = parts[1] if parts[0] == 'documents' else parts[2]
                    # 标准 hash 前缀
                    prefixes.append("/".join(parts[:4]) + "/")
                    try:
                        # 同一 year/month 下的 数字ID 目录（chunks.jsonl.gz 归档使用）
                        prefixes.append(f"documents/{parts[1]}/{parts[2]}/{doc_id}/")
                    except Exception:
                        pass
            # 数字ID下的 images 目录（不带年月）
            prefixes.append(f"documents/{doc_id}/")

            # 1) MinIO 严格删除（逐个前缀校验，失败直接抛错）
            for pfx in list(dict.fromkeys(prefixes)):
                try:
                    deleted = self.minio_storage.delete_prefix(pfx)
                    remaining = len(self.minio_storage.list_files(pfx))
                    if remaining > 0:
                        raise Exception(f"前缀未清空，剩余 {remaining} 个对象")
                    logger.info(f"MinIO前缀删除完成: {pfx} (删除 {deleted} 个对象)")
                except Exception as e:
                    logger.error(f"MinIO前缀删除失败(严格模式): {pfx} - {e}")
                    raise

            from app.models.chunk import DocumentChunk
            from app.models.image import DocumentImage
            from app.models.chunk_version import ChunkVersion
            from app.models.version import DocumentVersion

            if hard:
                # 物理删除顺序：文档版本 -> 分块版本 -> 分块 -> 图片 -> 文档
                chunk_ids = [rid for (rid,) in self.db.query(DocumentChunk.id).filter(DocumentChunk.document_id == doc_id).all()]
                if chunk_ids:
                    self.db.query(ChunkVersion).filter(ChunkVersion.chunk_id.in_(chunk_ids)).delete(synchronize_session=False)
                    self.db.query(DocumentChunk).filter(DocumentChunk.id.in_(chunk_ids)).delete(synchronize_session=False)
                # 删除文档级版本记录
                self.db.query(DocumentVersion).filter(DocumentVersion.document_id == doc_id).delete(synchronize_session=False)
                self.db.query(DocumentImage).filter(DocumentImage.document_id == doc_id).delete(synchronize_session=False)
                self.db.query(Document).filter(Document.id == doc_id).delete(synchronize_session=False)
                self.db.commit()
            else:
                # 软删除
                self.db.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).update({"is_deleted": True})
                self.db.query(DocumentImage).filter(DocumentImage.document_id == doc_id).update({"is_deleted": True})
                # 软删除文档版本
                self.db.query(DocumentVersion).filter(DocumentVersion.document_id == doc_id).update({"is_deleted": True})
                doc.is_deleted = True
                self.db.commit()

            # 3) OpenSearch 删除索引
            try:
                from app.services.opensearch_service import OpenSearchService
                osvc = OpenSearchService()
                osvc.delete_by_document(doc_id)
            except Exception as e:
                logger.warning(f"OpenSearch 索引删除失败: {e}")

            logger.info(f"文档删除完成（{'硬删除' if hard else '软删除'}）: {doc_id}")
            return True

        except Exception as e:
            logger.error(f"删除文档错误: {e}", exc_info=True)
            raise e
    
    def reprocess_document(self, doc_id: int) -> bool:
        """重新处理文档 - 根据文档处理流程设计实现"""
        try:
            logger.info(f"重新处理文档: {doc_id}")
            
            doc = self.get(doc_id)
            if not doc:
                logger.warning(f"文档不存在: {doc_id}")
                return False
            
            # 更新状态为重新处理
            doc.status = "reprocessing"
            doc.processing_progress = 0.0
            doc.error_message = None
            
            self.db.commit()
            
            # 触发异步任务重新处理文档
            task = process_document_task.delay(doc_id)
            logger.info(f"文档重新处理任务已启动，任务ID: {task.id}")
            
            return True
            
        except Exception as e:
            logger.error(f"重新处理文档错误: {e}", exc_info=True)
            raise e
