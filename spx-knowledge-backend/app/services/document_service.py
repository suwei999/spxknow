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
    
    def _calculate_minio_prefixes(self, doc_id: int, file_path: str = None, converted_pdf_url: str = None) -> List[str]:
        """
        计算文档在MinIO中需要删除的所有前缀路径
        
        参数:
            doc_id: 文档ID
            file_path: 原始文件路径
            converted_pdf_url: 转换后的PDF路径
        
        返回:
            前缀路径列表（已去重和排序）
        
        注意：
            - upload_chunks 使用: documents/{year}/{month}/{doc_id}/parsed/...
            - upload_pdf_file 使用: documents/{year}/{month}/doc_{doc_id}/converted/...
            - 需要同时覆盖两种格式
        """
        prefixes = []
        year = None
        month = None
        
        # 1. 从原始文件路径提取前缀和年月信息
        if file_path:
            parts = file_path.split("/")  # documents/{year}/{month}/{doc_hash}/original.ext
            if len(parts) >= 4:
                year = parts[1] if parts[0] == 'documents' else parts[2]
                month = parts[2] if parts[0] == 'documents' else parts[3]
                # 标准 hash 前缀（基于file_hash）
                prefixes.append("/".join(parts[:4]) + "/")
        
        # 2. 从转换后的PDF路径提取年月信息（如果file_path未提供）
        if not year or not month:
            if converted_pdf_url:
                pdf_parts = converted_pdf_url.split("/")
                if len(pdf_parts) >= 4:
                    year = pdf_parts[1] if pdf_parts[0] == 'documents' else None
                    month = pdf_parts[2] if pdf_parts[0] == 'documents' else None
        
        # 3. 生成所有可能的数字ID前缀格式（基于年月）
        if year and month:
            # 格式1: documents/{year}/{month}/{doc_id}/ (upload_chunks 使用，不带 doc_ 前缀)
            prefixes.append(f"documents/{year}/{month}/{doc_id}/")
            # 格式2: documents/{year}/{month}/doc_{doc_id}/ (upload_pdf_file 使用，带 doc_ 前缀)
            prefixes.append(f"documents/{year}/{month}/doc_{doc_id}/")
        
        # 4. 从转换后的PDF路径提取前缀（如果存在）
        if converted_pdf_url:
            pdf_parts = converted_pdf_url.split("/")
            if len(pdf_parts) >= 4:
                # converted PDF路径格式: documents/{year}/{month}/doc_{id}/converted/xxx.pdf
                pdf_prefix = "/".join(pdf_parts[:4]) + "/"  # documents/{year}/{month}/doc_{id}/
                if pdf_prefix not in prefixes:
                    prefixes.append(pdf_prefix)
                # 也尝试删除converted子目录
                if len(pdf_parts) >= 5:
                    converted_prefix = "/".join(pdf_parts[:5]) + "/"  # documents/{year}/{month}/doc_{id}/converted/
                    if converted_prefix not in prefixes:
                        prefixes.append(converted_prefix)
        
        # 5. 数字ID下的 images 目录（旧格式，不带年月）
        prefixes.append(f"documents/{doc_id}/")
        
        # 去重并排序（保证删除顺序）
        return sorted(list(dict.fromkeys(prefixes)))
    
    def _delete_minio_files(self, doc_id: int, prefixes: List[str], converted_pdf_url: str = None) -> Dict[str, Any]:
        """
        删除MinIO文件（硬删除时使用）
        
        返回:
            删除统计信息字典
        """
        total_deleted = 0
        failed_prefixes = []
        deleted_prefixes = []
        
        logger.info(f"开始删除MinIO文件（文档ID: {doc_id}），前缀列表: {prefixes}")
        
        for pfx in prefixes:
            try:
                deleted_count = self.minio_storage.delete_prefix(pfx)
                if deleted_count > 0:
                    total_deleted += deleted_count
                    deleted_prefixes.append({"prefix": pfx, "count": deleted_count})
                    logger.info(f"MinIO前缀删除完成: {pfx} (删除 {deleted_count} 个对象)")
                else:
                    logger.debug(f"MinIO前缀为空或无匹配对象: {pfx}")
            except Exception as e:
                failed_prefixes.append({"prefix": pfx, "error": str(e)})
                logger.error(f"MinIO前缀删除失败: {pfx} - {e}", exc_info=True)
                # 继续删除其他前缀
        
        # 额外：单独删除转换后的PDF文件（兜底）
        if converted_pdf_url:
            try:
                if self.minio_storage.file_exists(converted_pdf_url):
                    self.minio_storage.delete_file(converted_pdf_url)
                    total_deleted += 1
                    logger.info(f"已单独删除转换后的PDF: {converted_pdf_url}")
            except Exception as e:
                failed_prefixes.append({"prefix": converted_pdf_url, "error": str(e)})
                logger.warning(f"单独删除转换后的PDF失败: {converted_pdf_url} - {e}")
        
        result = {
            "total_deleted": total_deleted,
            "deleted_prefixes": deleted_prefixes,
            "failed_prefixes": failed_prefixes,
            "has_failures": len(failed_prefixes) > 0
        }
        
        logger.info(f"MinIO删除完成，共删除 {total_deleted} 个对象（文档ID: {doc_id}）")
        if failed_prefixes:
            logger.warning(f"MinIO删除有 {len(failed_prefixes)} 个前缀失败，但不影响MySQL删除")
        
        return result

    async def delete_document(self, doc_id: int, hard: bool = True) -> bool:
        """
        删除文档：
        - hard=True：物理删除 MySQL 行，并清理 MinIO 前缀与 OpenSearch 索引
        - hard=False：仅软删除（保留行，仅标记 is_deleted）
        
        删除顺序（硬删除）：
        1. 删除外部依赖（MinIO、OpenSearch）- 即使失败也不阻止MySQL删除
        2. 删除MySQL数据 - 关键操作，确保执行
        3. 记录删除统计信息
        
        返回:
            bool: 删除是否成功
        """
        try:
            logger.info(f"删除文档: {doc_id} (hard={hard})")
            # 读取文档
            doc = await self.get(doc_id)
            if not doc:
                logger.warning(f"文档不存在: {doc_id}")
                return False

            # 计算MinIO前缀列表
            prefixes = self._calculate_minio_prefixes(
                doc_id=doc_id,
                file_path=doc.file_path,
                converted_pdf_url=doc.converted_pdf_url
            )

            # 删除统计信息
            delete_stats = {
                "minio_deleted": 0,
                "minio_failed": 0,
                "mysql_deleted": 0,
                "opensearch_deleted": False
            }

            # 1) 先删除外部依赖（MinIO、OpenSearch）- 即使失败也不阻止MySQL删除
            # 这样可以确保即使外部服务有问题，MySQL数据也能被删除
            
            # 1.1) MinIO 删除（仅硬删除时删除文件，软删除保留文件以便恢复）
            if hard:
                minio_result = self._delete_minio_files(doc_id, prefixes, doc.converted_pdf_url)
                delete_stats["minio_deleted"] = minio_result["total_deleted"]
                delete_stats["minio_failed"] = len(minio_result["failed_prefixes"])
                
                if minio_result["has_failures"]:
                    logger.warning(f"MinIO删除有部分失败，但继续执行MySQL删除（文档ID: {doc_id}）")
            else:
                # 软删除：保留MinIO文件，仅删除OpenSearch索引（避免搜索结果中出现已删除文档）
                logger.info(f"软删除模式：保留MinIO文件，仅删除OpenSearch索引（文档ID: {doc_id}）")

            # 1.2) OpenSearch 删除索引（无论硬删除还是软删除都要删除索引）
            try:
                from app.services.opensearch_service import OpenSearchService
                osvc = OpenSearchService()
                osvc.delete_by_document(doc_id)
                delete_stats["opensearch_deleted"] = True
                logger.info(f"OpenSearch索引删除成功（文档ID: {doc_id}）")
            except Exception as e:
                logger.warning(f"OpenSearch 索引删除失败: {e}，但继续执行MySQL删除")
                delete_stats["opensearch_deleted"] = False

            # 2) 删除MySQL数据（关键操作，确保执行）
            from app.models.chunk import DocumentChunk
            from app.models.image import DocumentImage
            from app.models.chunk_version import ChunkVersion
            from app.models.version import DocumentVersion

            try:
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
                    delete_stats["mysql_deleted"] = 5  # 估算删除的表数量
                else:
                    # 软删除
                    self.db.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).update({"is_deleted": True})
                    self.db.query(DocumentImage).filter(DocumentImage.document_id == doc_id).update({"is_deleted": True})
                    # 软删除文档版本
                    self.db.query(DocumentVersion).filter(DocumentVersion.document_id == doc_id).update({"is_deleted": True})
                    doc.is_deleted = True
                
                self.db.commit()
                logger.info(f"MySQL删除完成（{'硬删除' if hard else '软删除'}）: {doc_id}")
            except Exception as e:
                self.db.rollback()
                logger.error(f"MySQL删除失败: {e}，回滚事务（文档ID: {doc_id}）", exc_info=True)
                raise  # MySQL删除失败必须抛出异常

            # 3) 记录删除统计信息
            logger.info(f"文档删除完成（{'硬删除' if hard else '软删除'}）: {doc_id}, "
                       f"统计: MinIO={delete_stats['minio_deleted']}个对象, "
                       f"失败={delete_stats['minio_failed']}个前缀, "
                       f"OpenSearch={'成功' if delete_stats['opensearch_deleted'] else '失败'}, "
                       f"MySQL=成功")
            
            return True

        except Exception as e:
            # 如果是MySQL删除失败，已经回滚，直接抛出
            # 如果是其他异常（如文档不存在），也抛出
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
    
    def _calculate_dynamic_threshold(
        self,
        element_index_start: int = None,
        element_index_end: int = None,
        base_threshold: int = 10
    ) -> int:
        """
        动态计算 element_index 差值阈值
        
        策略：
        - 如果 chunk 跨度较大（element_index_end - element_index_start > 50），阈值放宽
        - 如果 chunk 跨度较小，阈值收紧
        - 如果只有起始索引，使用较小的阈值
        
        参数:
            element_index_start: 起始元素索引
            element_index_end: 结束元素索引
            base_threshold: 基础阈值（默认10）
        
        返回:
            动态调整后的阈值
        """
        if element_index_start is None and element_index_end is None:
            return base_threshold
        
        if element_index_start is not None and element_index_end is not None:
            chunk_span = element_index_end - element_index_start
            # 如果跨度较大（>50），允许更远的关联（阈值增加）
            # 如果跨度较小（<10），收紧阈值（阈值减少）
            if chunk_span > 50:
                return int(base_threshold * 1.5)  # 放宽阈值
            elif chunk_span < 10:
                return max(5, int(base_threshold * 0.7))  # 收紧阈值
            else:
                return base_threshold
        else:
            # 只有起始或结束索引，使用较小阈值
            return max(5, int(base_threshold * 0.8))
    
    def _calculate_coordinate_overlap(
        self,
        chunk_coords: dict = None,
        image_coords: dict = None
    ) -> float:
        """
        计算文本块与图片的坐标重叠度（IoU - Intersection over Union）
        
        参数:
            chunk_coords: 文本块坐标 {x, y, width, height} 或 None
            image_coords: 图片坐标 {x, y, width, height} 或 None
        
        返回:
            重叠度分数 [0.0, 1.0]，0表示无重叠，1表示完全重叠
        """
        if not chunk_coords or not image_coords:
            return 0.0
        
        try:
            # 提取坐标信息
            chunk_x = chunk_coords.get('x', 0)
            chunk_y = chunk_coords.get('y', 0)
            chunk_w = chunk_coords.get('width', 0)
            chunk_h = chunk_coords.get('height', 0)
            
            img_x = image_coords.get('x', 0)
            img_y = image_coords.get('y', 0)
            img_w = image_coords.get('width', 0)
            img_h = image_coords.get('height', 0)
            
            # 如果没有有效的尺寸信息，返回0
            if chunk_w <= 0 or chunk_h <= 0 or img_w <= 0 or img_h <= 0:
                return 0.0
            
            # 计算交集区域
            inter_x1 = max(chunk_x, img_x)
            inter_y1 = max(chunk_y, img_y)
            inter_x2 = min(chunk_x + chunk_w, img_x + img_w)
            inter_y2 = min(chunk_y + chunk_h, img_y + img_h)
            
            # 如果无交集
            if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
                return 0.0
            
            # 计算交集面积
            inter_area = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
            
            # 计算并集面积
            chunk_area = chunk_w * chunk_h
            img_area = img_w * img_h
            union_area = chunk_area + img_area - inter_area
            
            if union_area <= 0:
                return 0.0
            
            # 计算IoU
            iou = inter_area / union_area
            return min(1.0, max(0.0, iou))
            
        except Exception as e:
            logger.debug(f"计算坐标重叠度失败: {e}")
            return 0.0
    
    def _calculate_association_confidence(
        self,
        chunk_meta: dict,
        image_meta: dict,
        element_index_diff: int = None,
        coordinate_overlap: float = 0.0,
        association_strategy: str = "unknown"
    ) -> float:
        """
        计算关联置信度分数
        
        参数:
            chunk_meta: 文本块元数据
            image_meta: 图片元数据
            element_index_diff: element_index 差值（如果图片在文本块后面）
            coordinate_overlap: 坐标重叠度 [0.0, 1.0]
            association_strategy: 关联策略（"within_range", "nearby_same_page", "adjacent_page"）
        
        返回:
            置信度分数 [0.0, 1.0]
        """
        confidence = 0.0
        
        # 策略1：图片在文本块范围内（最高置信度）
        if association_strategy == "within_range":
            confidence = 0.95  # 基础置信度
            # 如果有坐标重叠，进一步提升
            if coordinate_overlap > 0.3:
                confidence = min(1.0, confidence + 0.05)
        
        # 策略2：相同页码且位置接近
        elif association_strategy == "nearby_same_page":
            if element_index_diff is not None:
                # 基于 element_index 差值计算置信度
                # 差值越小，置信度越高
                if element_index_diff <= 3:
                    confidence = 0.85
                elif element_index_diff <= 5:
                    confidence = 0.75
                elif element_index_diff <= 10:
                    confidence = 0.65
                else:
                    confidence = 0.55
                
                # 如果有坐标重叠，进一步提升
                if coordinate_overlap > 0.2:
                    confidence = min(1.0, confidence + 0.1)
            else:
                confidence = 0.60
        
        # 策略3：相邻页
        elif association_strategy == "adjacent_page":
            confidence = 0.50
            # 如果 element_index 很小（页面开始），可能相关
            image_element_index = image_meta.get('element_index')
            if image_element_index is not None and image_element_index <= 5:
                confidence = 0.60
        
        # 策略4：同页兜底（最低置信度）
        elif association_strategy == "same_page_fallback":
            confidence = 0.40
        
        # 考虑页码一致性
        chunk_page = chunk_meta.get('page_number')
        image_page = image_meta.get('page_number')
        if chunk_page and image_page and chunk_page == image_page:
            confidence *= 1.1  # 相同页码增加10%置信度
        
        return min(1.0, max(0.0, confidence))
    
    def get_images_for_chunk(
        self, 
        document_id: int, 
        chunk,
        min_confidence: float = 0.5,
        return_with_confidence: bool = False
    ) -> list:
        """
        根据文本块查找关联的图片（文本 → 图片）
        
        关联逻辑（已优化）：
        1. 优先：element_index 在 chunk 的 element_index_start 和 element_index_end 范围内
        2. 次优：相同 page_number 且图片紧跟文本块（element_index 在 chunk 后面且差值较小）
        3. 扩展：相邻页面的图片
        4. ✅ 新增：动态阈值、坐标重叠、置信度评分
        
        参数:
            document_id: 文档ID
            chunk: DocumentChunk 对象或包含 metadata 的字典
            min_confidence: 最低置信度阈值（默认0.5），低于此值的关联将被过滤
            return_with_confidence: 是否返回置信度信息（默认False，保持向后兼容）
        
        返回:
            如果 return_with_confidence=False: DocumentImage 对象列表（按置信度降序排列）
            如果 return_with_confidence=True: [(DocumentImage, confidence_score), ...] 元组列表
        """
        import json
        from app.models.image import DocumentImage
        
        try:
            # 解析 chunk metadata
            chunk_meta = {}
            if hasattr(chunk, 'meta') and chunk.meta:
                try:
                    chunk_meta = json.loads(chunk.meta) if isinstance(chunk.meta, str) else chunk.meta
                except:
                    pass
            elif isinstance(chunk, dict):
                chunk_meta = chunk.get('metadata', {})
            
            element_index_start = chunk_meta.get('element_index_start')
            element_index_end = chunk_meta.get('element_index_end')
            chunk_page = chunk_meta.get('page_number')
            chunk_coords = chunk_meta.get('coordinates')  # ✅ 新增：获取文本块坐标
            
            # ✅ 动态计算阈值
            dynamic_threshold = self._calculate_dynamic_threshold(
                element_index_start, element_index_end, base_threshold=10
            )
            
            # 获取文档的所有图片
            images = self.db.query(DocumentImage).filter(
                DocumentImage.document_id == document_id,
                DocumentImage.is_deleted == False
            ).all()
            
            associated_images = []  # 存储 (image, confidence) 元组
            
            for image in images:
                # 解析图片 metadata
                image_meta = {}
                if image.meta:
                    try:
                        image_meta = json.loads(image.meta) if isinstance(image.meta, str) else image.meta
                    except:
                        pass
                
                image_element_index = image_meta.get('element_index')
                image_page = image_meta.get('page_number')
                image_coords = image_meta.get('coordinates')  # ✅ 新增：获取图片坐标
                
                # ✅ 计算坐标重叠度
                coordinate_overlap = self._calculate_coordinate_overlap(chunk_coords, image_coords)
                
                association_strategy = None
                element_index_diff = None
                
                # 策略1：element_index 在范围内（图片在文本块内部）- 最高置信度
                if element_index_start is not None and element_index_end is not None:
                    if image_element_index is not None:
                        if element_index_start <= image_element_index <= element_index_end:
                            association_strategy = "within_range"
                            confidence = self._calculate_association_confidence(
                                chunk_meta, image_meta,
                                element_index_diff=None,
                                coordinate_overlap=coordinate_overlap,
                                association_strategy=association_strategy
                            )
                            if confidence >= min_confidence:
                                associated_images.append((image, confidence))
                            continue
                
                # 策略2：相同页码且图片紧跟文本块（图片在文本块后面）
                if chunk_page and image_page and chunk_page == image_page:
                    if element_index_end is not None and image_element_index is not None:
                        diff = image_element_index - element_index_end
                        # ✅ 使用动态阈值
                        if 0 < diff <= dynamic_threshold:
                            association_strategy = "nearby_same_page"
                            element_index_diff = diff
                            confidence = self._calculate_association_confidence(
                                chunk_meta, image_meta,
                                element_index_diff=diff,
                                coordinate_overlap=coordinate_overlap,
                                association_strategy=association_strategy
                            )
                            if confidence >= min_confidence:
                                associated_images.append((image, confidence))
                            continue
                
                # 策略3：相邻页面的图片
                if chunk_page and image_page:
                    page_diff = abs(image_page - chunk_page)
                    if page_diff == 1:  # 相邻页
                        if element_index_end is not None and image_element_index is not None:
                            # 如果是下一页的第一张图片，可能是相关的
                            if image_page > chunk_page and image_element_index <= 5:
                                association_strategy = "adjacent_page"
                                confidence = self._calculate_association_confidence(
                                    chunk_meta, image_meta,
                                    element_index_diff=None,
                                    coordinate_overlap=coordinate_overlap,
                                    association_strategy=association_strategy
                                )
                                if confidence >= min_confidence:
                                    associated_images.append((image, confidence))
                                continue
            
            # ✅ 按置信度降序排序
            associated_images.sort(key=lambda x: x[1], reverse=True)
            
            # 根据参数决定返回格式
            if return_with_confidence:
                return associated_images  # 返回 (image, confidence) 元组列表
            else:
                return [img for img, _ in associated_images]  # 只返回图片对象列表（向后兼容）
            
        except Exception as e:
            logger.error(f"查找文本块关联图片失败: {e}", exc_info=True)
            return []
    
    def get_chunks_for_image(
        self,
        document_id: int,
        image,
        min_confidence: float = 0.5,
        return_with_confidence: bool = False
    ) -> list:
        """
        根据图片查找关联的文本块（图片 → 文本）
        
        关联逻辑（已优化）：
        1. 优先：图片的 element_index 在文本块的 element_index_start 和 element_index_end 范围内
        2. 次优：相同 page_number 且文本块在图片前面（图片紧跟文本块）
        3. 扩展：图片前后的文本块（包含前一个和后一个）
        4. ✅ 新增：动态阈值、坐标重叠、置信度评分
        
        参数:
            document_id: 文档ID
            image: DocumentImage 对象或包含 metadata 的字典
            min_confidence: 最低置信度阈值（默认0.5），低于此值的关联将被过滤
            return_with_confidence: 是否返回置信度信息（默认False，保持向后兼容）
        
        返回:
            如果 return_with_confidence=False: DocumentChunk 对象列表（按置信度和位置排序）
            如果 return_with_confidence=True: [(DocumentChunk, confidence_score), ...] 元组列表
        """
        import json
        from app.models.chunk import DocumentChunk
        
        try:
            # 解析图片 metadata
            image_meta = {}
            if hasattr(image, 'meta') and image.meta:
                try:
                    image_meta = json.loads(image.meta) if isinstance(image.meta, str) else image.meta
                except:
                    pass
            elif isinstance(image, dict):
                image_meta = image.get('metadata', {})
            
            image_element_index = image_meta.get('element_index')
            image_page = image_meta.get('page_number')
            image_coords = image_meta.get('coordinates')  # ✅ 新增：获取图片坐标
            
            # 获取文档的所有文本块
            chunks = self.db.query(DocumentChunk).filter(
                DocumentChunk.document_id == document_id,
                DocumentChunk.is_deleted == False
            ).order_by(DocumentChunk.chunk_index).all()
            
            associated_chunks = []  # 存储 (chunk, confidence) 元组
            
            for chunk in chunks:
                # 解析 chunk metadata
                chunk_meta = {}
                if chunk.meta:
                    try:
                        chunk_meta = json.loads(chunk.meta) if isinstance(chunk.meta, str) else chunk.meta
                    except:
                        pass
                
                element_index_start = chunk_meta.get('element_index_start')
                element_index_end = chunk_meta.get('element_index_end')
                chunk_page = chunk_meta.get('page_number')
                chunk_coords = chunk_meta.get('coordinates')  # ✅ 新增：获取文本块坐标
                
                # ✅ 计算坐标重叠度
                coordinate_overlap = self._calculate_coordinate_overlap(chunk_coords, image_coords)
                
                # ✅ 动态计算阈值
                dynamic_threshold = self._calculate_dynamic_threshold(
                    element_index_start, element_index_end, base_threshold=10
                )
                
                association_strategy = None
                element_index_diff = None
                
                # 策略1：图片在文本块范围内（图片嵌入在文本块中）- 最高置信度
                if image_element_index is not None:
                    if element_index_start is not None and element_index_end is not None:
                        if element_index_start <= image_element_index <= element_index_end:
                            association_strategy = "within_range"
                            confidence = self._calculate_association_confidence(
                                chunk_meta, image_meta,
                                element_index_diff=None,
                                coordinate_overlap=coordinate_overlap,
                                association_strategy=association_strategy
                            )
                            if confidence >= min_confidence:
                                associated_chunks.append((chunk, confidence))
                            continue
                
                # 策略2：相同页码且文本块在图片前面（图片紧跟文本块）
                if image_page and chunk_page and image_page == chunk_page:
                    if image_element_index is not None and element_index_end is not None:
                        diff = image_element_index - element_index_end
                        # ✅ 使用动态阈值
                        if 0 < diff <= dynamic_threshold:
                            association_strategy = "nearby_same_page"
                            element_index_diff = diff
                            confidence = self._calculate_association_confidence(
                                chunk_meta, image_meta,
                                element_index_diff=diff,
                                coordinate_overlap=coordinate_overlap,
                                association_strategy=association_strategy
                            )
                            if confidence >= min_confidence:
                                associated_chunks.append((chunk, confidence))
                            continue
                
                # 策略3：图片在文本块前面，且距离较近，文本块可能是后续说明
                if image_page and chunk_page and image_page == chunk_page:
                    if image_element_index is not None and element_index_start is not None:
                        diff = element_index_start - image_element_index
                        # ✅ 使用动态阈值
                        if 0 < diff <= dynamic_threshold:
                            association_strategy = "nearby_same_page"  # 复用相同策略
                            element_index_diff = diff
                            confidence = self._calculate_association_confidence(
                                chunk_meta, image_meta,
                                element_index_diff=diff,
                                coordinate_overlap=coordinate_overlap,
                                association_strategy=association_strategy
                            )
                            if confidence >= min_confidence:
                                associated_chunks.append((chunk, confidence))
                            continue
            
            # 如果没有找到关联块，尝试查找同一页的所有文本块作为上下文（兜底策略）
            if not associated_chunks and image_page:
                for chunk in chunks:
                    chunk_meta = {}
                    if chunk.meta:
                        try:
                            chunk_meta = json.loads(chunk.meta) if isinstance(chunk.meta, str) else chunk.meta
                        except:
                            pass
                    chunk_page = chunk_meta.get('page_number')
                    if chunk_page == image_page:
                        # 兜底策略：相同页码，置信度较低
                        chunk_coords = chunk_meta.get('coordinates')
                        coordinate_overlap = self._calculate_coordinate_overlap(chunk_coords, image_coords)
                        confidence = self._calculate_association_confidence(
                            chunk_meta, image_meta,
                            element_index_diff=None,
                            coordinate_overlap=coordinate_overlap,
                            association_strategy="same_page_fallback"
                        )
                        if confidence >= min_confidence:
                            associated_chunks.append((chunk, confidence))
            
            # ✅ 先按置信度降序排序，再按 chunk_index 排序（保证稳定排序）
            associated_chunks.sort(key=lambda x: (-x[1], x[0].chunk_index))
            
            # 根据参数决定返回格式
            if return_with_confidence:
                return associated_chunks  # 返回 (chunk, confidence) 元组列表
            else:
                return [chunk for chunk, _ in associated_chunks]  # 只返回 chunk 对象列表（向后兼容）
            
        except Exception as e:
            logger.error(f"查找图片关联文本块失败: {e}", exc_info=True)
            return []
