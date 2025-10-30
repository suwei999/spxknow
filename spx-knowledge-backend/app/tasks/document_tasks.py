"""
Document Processing Tasks
"""

import os
import tempfile
import time
from celery import current_task
from app.tasks.celery_app import celery_app
from app.services.unstructured_service import UnstructuredService
from app.services.vector_service import VectorService
from app.services.cache_service import CacheService
from app.services.opensearch_service import OpenSearchService
from app.services.minio_storage_service import MinioStorageService
from app.services.image_service import ImageService
from app.config.settings import settings
from app.models.document import Document
from app.models.chunk import DocumentChunk
from sqlalchemy.orm import Session
from app.config.database import SessionLocal
from app.core.logging import logger
from app.core.constants import DOC_STATUS_PARSING, DOC_STATUS_CHUNKING, DOC_STATUS_VECTORIZING, DOC_STATUS_INDEXING, DOC_STATUS_COMPLETED, DOC_STATUS_FAILED

# 确保在Celery进程中注册所有模型，解决字符串关系解析问题
import app.models  # noqa: F401

@celery_app.task(bind=True)
def process_document_task(self, document_id: int):
    """处理文档任务 - 根据文档处理流程设计实现"""
    db = SessionLocal()
    document = None
    task_id = self.request.id if self else "unknown"
    
    try:
        logger.info(f"[任务ID: {task_id}] ========== 开始处理文档 {document_id} ==========")
        
        # 更新任务状态
        current_task.update_state(
            state="PROGRESS",
            meta={"current": 0, "total": 100, "status": "开始处理文档"}
        )
        
        # 获取文档
        logger.debug(f"[任务ID: {task_id}] 步骤1/7: 从数据库获取文档信息 (document_id={document_id})")
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            logger.error(f"[任务ID: {task_id}] 文档 {document_id} 不存在于数据库中")
            raise Exception(f"文档 {document_id} 不存在")
        
        logger.info(f"[任务ID: {task_id}] 文档信息: ID={document.id}, 文件名={document.original_filename}, "
                   f"文件类型={document.file_type}, 文件路径={document.file_path}, "
                   f"知识库ID={document.knowledge_base_id}, 文件大小={document.file_size or '未知'} bytes")
        
        # 更新文档状态为解析中
        logger.debug(f"[任务ID: {task_id}] 步骤2/7: 更新文档状态为解析中")
        document.status = DOC_STATUS_PARSING
        document.processing_progress = 10.0
        db.commit()
        
        current_task.update_state(
            state="PROGRESS",
            meta={"current": 10, "total": 100, "status": "下载文件到临时目录"}
        )
        
        # 1. 下载文件到临时目录 - 根据设计文档实现
        logger.info(f"[任务ID: {task_id}] 步骤3/7: 开始从MinIO下载文件 (file_path={document.file_path})")
        download_start = time.time()
        
        try:
            minio_service = MinioStorageService()
            file_content = minio_service.download_file(document.file_path)
            download_time = time.time() - download_start
            logger.info(f"[任务ID: {task_id}] MinIO文件下载成功: 大小={len(file_content)} bytes, 耗时={download_time:.2f}秒")
        except Exception as e:
            logger.error(f"[任务ID: {task_id}] MinIO文件下载失败: {e}", exc_info=True)
            raise
        
        # 创建临时文件
        logger.debug(f"[任务ID: {task_id}] 步骤3.1/7: 创建临时文件目录")
        temp_dir = tempfile.mkdtemp()
        file_extension = os.path.splitext(document.original_filename)[1].lstrip('.')
        temp_file_path = os.path.join(temp_dir, f"{document_id}.{file_extension}")
        
        try:
            with open(temp_file_path, 'wb') as f:
                f.write(file_content)
            logger.info(f"[任务ID: {task_id}] 临时文件创建成功: {temp_file_path}, 大小={os.path.getsize(temp_file_path)} bytes")
        except Exception as e:
            logger.error(f"[任务ID: {task_id}] 临时文件创建失败: {e}", exc_info=True)
            raise
        
        current_task.update_state(
            state="PROGRESS",
            meta={"current": 15, "total": 100, "status": "开始解析文档"}
        )
        
        # 2. 解析文档 - 根据设计文档实现
        logger.info(f"[任务ID: {task_id}] 步骤4/7: 开始使用Unstructured解析文档")
        parse_start = time.time()
        
        unstructured_service = UnstructuredService(db)
        
        # 根据文件类型选择解析策略
        strategy = unstructured_service._select_parsing_strategy(document.file_type)
        logger.info(f"[任务ID: {task_id}] 解析配置: 文件类型={document.file_type}, 解析策略={strategy}, "
                   f"临时文件={temp_file_path}")
        
        try:
            parse_result = unstructured_service.parse_document(temp_file_path, strategy=strategy)
            parse_time = time.time() - parse_start
            text_content = parse_result.get('text_content', '')
            elements_count = len(parse_result.get('elements', []))
            text_length = len(text_content)
            
            logger.info(f"[任务ID: {task_id}] Unstructured解析完成: 耗时={parse_time:.2f}秒, "
                       f"提取元素数={elements_count}, 文本长度={text_length} 字符")
            
            if text_length == 0:
                logger.warning(f"[任务ID: {task_id}] 警告: 解析结果为空，可能文档无文本内容或解析失败")
            else:
                logger.debug(f"[任务ID: {task_id}] 解析结果预览 (前200字符): {text_content[:200]}...")
        except Exception as e:
            logger.error(f"[任务ID: {task_id}] Unstructured解析失败: {e}", exc_info=True)
            raise
        
        # 3. 清理临时文件
        logger.debug(f"[任务ID: {task_id}] 步骤4.1/7: 清理临时文件")
        try:
            os.remove(temp_file_path)
            os.rmdir(temp_dir)
            logger.debug(f"[任务ID: {task_id}] 临时文件清理成功: {temp_file_path}")
        except Exception as e:
            logger.warning(f"[任务ID: {task_id}] 清理临时文件失败: {e}, 路径={temp_file_path}")
        
        current_task.update_state(
            state="PROGRESS",
            meta={"current": 30, "total": 100, "status": "文档解析完成"}
        )
        
        # 更新文档状态为分块中
        logger.debug(f"[任务ID: {task_id}] 步骤5/7: 开始文档分块处理")
        document.status = DOC_STATUS_CHUNKING
        document.processing_progress = 40.0
        db.commit()
        
        # 创建文档分块
        chunk_start = time.time()
        text_content = parse_result.get("text_content", "")
        logger.debug(f"[任务ID: {task_id}] 分块输入: 文本长度={len(text_content)} 字符")
        
        chunks = unstructured_service.chunk_text(text_content)
        chunk_time = time.time() - chunk_start
        
        logger.info(f"[任务ID: {task_id}] 文档分块完成: 耗时={chunk_time:.2f}秒, 共生成 {len(chunks)} 个分块")
        
        if len(chunks) == 0:
            logger.warning(f"[任务ID: {task_id}] 警告: 未生成任何分块，可能文本内容为空")
        else:
            total_chunk_length = sum(len(chunk) for chunk in chunks)
            avg_chunk_length = total_chunk_length / len(chunks)
            logger.debug(f"[任务ID: {task_id}] 分块统计: 总字符数={total_chunk_length}, 平均分块长度={avg_chunk_length:.0f} 字符")
        
        # 保存分块到数据库（按配置决定是否存正文）
        logger.debug(f"[任务ID: {task_id}] 步骤5.1/7: 保存分块到数据库")
        store_text = getattr(settings, 'STORE_CHUNK_TEXT_IN_DB', False)
        for i, chunk_content in enumerate(chunks):
            chunk = DocumentChunk(
                document_id=document_id,
                content=chunk_content if store_text else "",
                chunk_index=i,
                chunk_type="text"
            )
            db.add(chunk)
            if (i + 1) % 50 == 0:  # 每50个分块记录一次
                logger.debug(f"[任务ID: {task_id}] 已保存 {i + 1}/{len(chunks)} 个分块到数据库")
        
        db.commit()
        logger.info(f"[任务ID: {task_id}] 分块数据已保存到数据库: 共 {len(chunks)} 条记录")

        # 将全文分块归档到 MinIO
        try:
            minio = MinioStorageService()
            minio.upload_chunks(str(document_id), chunks)
            logger.info(f"[任务ID: {task_id}] 分块JSON已归档到 MinIO")
        except Exception as e:
            logger.warning(f"[任务ID: {task_id}] 分块归档到 MinIO 失败: {e}")

        # 图片处理流水线（若解析结果包含图片二进制，则落 MinIO + 入库 + 向量化 + 索引）
        try:
            images_meta = parse_result.get('images', [])
            if images_meta:
                img_service = ImageService(db)
                vector_service = VectorService(db)
                os_service = OpenSearchService()
                saved = 0
                for img in images_meta:
                    data = img.get('data') or img.get('bytes')
                    if not data:
                        continue
                    image_row = img_service.create_image_from_bytes(document_id, data, image_ext=img.get('ext', '.png'), image_type=img.get('image_type'))
                    # 生成图片向量
                    tmp_path = None
                    try:
                        tmp_dir = tempfile.mkdtemp()
                        tmp_path = os.path.join(tmp_dir, f"img_{image_row.id}.png")
                        with open(tmp_path, 'wb') as f:
                            f.write(data)
                        image_vector = vector_service.generate_image_embedding(tmp_path)
                    finally:
                        try:
                            if tmp_path and os.path.exists(tmp_path):
                                os.remove(tmp_path)
                                os.rmdir(os.path.dirname(tmp_path))
                        except Exception:
                            pass
                    # 更新 MySQL 向量维度/模型（若表有对应列）
                    try:
                        if hasattr(image_row, 'vector_model'):
                            image_row.vector_model = settings.OLLAMA_IMAGE_MODEL
                        if hasattr(image_row, 'vector_dim') and isinstance(image_vector, list):
                            image_row.vector_dim = len(image_vector)
                        db.commit()
                    except Exception:
                        db.rollback()
                    # 索引到 OpenSearch images 索引
                    try:
                        os_service.index_image_sync({
                            "image_id": image_row.id,
                            "document_id": document.id,
                            "knowledge_base_id": document.knowledge_base_id,
                            "category_id": getattr(document, 'category_id', None),
                            "image_path": image_row.image_path,
                            "page_number": img.get('page_number'),
                            "coordinates": img.get('coordinates'),
                            "width": image_row.width,
                            "height": image_row.height,
                            "image_type": image_row.image_type,
                            "ocr_text": image_row.ocr_text or "",
                            "description": img.get('description', ''),
                            "feature_tags": img.get('feature_tags', []),
                            "image_vector": image_vector,
                            "created_at": getattr(image_row, 'created_at', None).isoformat() if getattr(image_row, 'created_at', None) else None,
                            "updated_at": getattr(image_row, 'updated_at', None).isoformat() if getattr(image_row, 'updated_at', None) else None,
                            "metadata": img.get('metadata', {}),
                            "processing_status": getattr(image_row, 'status', 'completed'),
                            "model_version": "1.0",
                        })
                    except Exception as idxe:
                        logger.warning(f"[任务ID: {task_id}] 图片索引失败 image_id={image_row.id}: {idxe}")
                    saved += 1
                logger.info(f"[任务ID: {task_id}] 图片持久化完成: {saved}/{len(images_meta)}")
        except Exception as e:
            logger.warning(f"[任务ID: {task_id}] 图片持久化失败: {e}")
        
        current_task.update_state(
            state="PROGRESS",
            meta={"current": 60, "total": 100, "status": "文档分块完成"}
        )
        
        # 更新文档状态为向量化中
        logger.debug(f"[任务ID: {task_id}] 步骤6/7: 开始向量化和索引建立")
        document.status = DOC_STATUS_VECTORIZING
        document.processing_progress = 70.0
        db.commit()
        
        # 向量化处理
        vector_service = VectorService(db)
        chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).all()
        
        logger.info(f"[任务ID: {task_id}] 开始向量化: 共 {len(chunks)} 个分块需要处理")
        if len(chunks) == 0:
            logger.warning(f"[任务ID: {task_id}] 无分块可向量化，跳过向量化与索引阶段")
            document.status = DOC_STATUS_COMPLETED
            document.processing_progress = 100.0
            db.commit()
            total_time = time.time() - download_start
            current_task.update_state(state="SUCCESS", meta={"current": 100, "total": 100, "status": "文档无文本，流程结束"})
            return {
                "status": "success",
                "message": "文档无文本，流程结束",
                "document_id": document_id,
                "chunks_count": 0,
                "text_length": len(text_content),
                "processing_time": total_time,
            }
        vectorize_start = time.time()
        
        # 初始化OpenSearch服务
        opensearch_service = OpenSearchService()
        
        # 批量生成向量并存储到OpenSearch
        success_count = 0
        error_count = 0
        
        for i, chunk in enumerate(chunks):
            chunk_start = time.time()
            
            try:
                # 生成向量
                vector = vector_service.generate_embedding(chunk.content)
                vectorize_time = time.time() - chunk_start
                
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
                index_start = time.time()
                # 同步索引到 OpenSearch（使用同步封装）
                try:
                    opensearch_service.index_document_chunk_sync(chunk_doc)
                except Exception as idx_err:
                    logger.error(f"[任务ID: {task_id}] OpenSearch 索引分块失败: {idx_err}")
                index_time = time.time() - index_start
                
                success_count += 1
                
                if (i + 1) % 10 == 0 or i == len(chunks) - 1:  # 每10个或最后一个记录日志
                    logger.info(f"[任务ID: {task_id}] 向量化进度: {i+1}/{len(chunks)} "
                               f"(分块ID={chunk.id}, 向量维度={len(vector)}, "
                               f"向量化耗时={vectorize_time:.2f}秒, 索引耗时={index_time:.2f}秒)")
                else:
                    logger.debug(f"[任务ID: {task_id}] 分块 {chunk.id} 处理完成: "
                               f"向量维度={len(vector)}, 向量化={vectorize_time:.2f}秒, 索引={index_time:.2f}秒")
                
            except Exception as e:
                error_count += 1
                logger.error(f"[任务ID: {task_id}] 分块 {chunk.id} (索引 {i+1}/{len(chunks)}) 处理失败: {e}", exc_info=True)
                raise e
            
            # 更新任务进度
            progress = 60 + (i / len(chunks)) * 30
            current_task.update_state(
                state="PROGRESS",
                meta={"current": int(progress), "total": 100, "status": f"向量化中 ({i+1}/{len(chunks)})"}
            )
        
        vectorize_total_time = time.time() - vectorize_start
        avg_time = (vectorize_total_time / len(chunks)) if len(chunks) else 0.0
        logger.info(f"[任务ID: {task_id}] 向量化完成: 成功={success_count}, 失败={error_count}, 总耗时={vectorize_total_time:.2f}秒, 平均耗时={avg_time:.2f}秒/分块")
        
        current_task.update_state(
            state="PROGRESS",
            meta={"current": 90, "total": 100, "status": "向量化完成，索引已建立"}
        )
        
        # 更新文档状态为索引中（OpenSearch索引已在上面的循环中建立）
        logger.debug(f"[任务ID: {task_id}] 步骤7/7: 完成处理，更新文档状态")
        document.status = DOC_STATUS_INDEXING
        document.processing_progress = 95.0
        db.commit()
        
        logger.info(f"[任务ID: {task_id}] OpenSearch索引建立完成: 共索引 {len(chunks)} 个分块")
        
        # 更新文档状态为完成
        document.status = DOC_STATUS_COMPLETED
        document.processing_progress = 100.0
        db.commit()
        
        total_time = time.time() - download_start
        logger.info(f"[任务ID: {task_id}] ========== 文档 {document_id} 处理完成 ==========")
        logger.info(f"[任务ID: {task_id}] 处理统计: 总耗时={total_time:.2f}秒, "
                   f"文件大小={len(file_content)} bytes, 分块数={len(chunks)}, "
                   f"文本长度={len(text_content)} 字符")
        
        current_task.update_state(
            state="SUCCESS",
            meta={"current": 100, "total": 100, "status": "文档处理完成"}
        )
        
        return {
            "status": "success",
            "message": "文档处理完成",
            "document_id": document_id,
            "chunks_count": len(chunks),
            "text_length": len(text_content),
            "processing_time": total_time
        }
        
    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}"
        logger.error(f"[任务ID: {task_id}] ========== 文档 {document_id} 处理失败 ==========")
        logger.error(f"[任务ID: {task_id}] 错误信息: {error_msg}", exc_info=True)
        
        # 更新文档状态为失败
        if document:
            try:
                document.status = DOC_STATUS_FAILED
                document.error_message = error_msg
                db.commit()
                logger.debug(f"[任务ID: {task_id}] 文档状态已更新为失败")
            except Exception as db_err:
                logger.error(f"[任务ID: {task_id}] 更新文档状态失败: {db_err}", exc_info=True)
        
        current_task.update_state(
            state="FAILURE",
            meta={"error": error_msg, "document_id": document_id}
        )
        raise e
    finally:
        try:
            db.close()
            logger.debug(f"[任务ID: {task_id}] 数据库连接已关闭")
        except Exception as e:
            logger.warning(f"[任务ID: {task_id}] 关闭数据库连接时出错: {e}")

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
