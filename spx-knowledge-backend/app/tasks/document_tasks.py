"""
Document Processing Tasks
"""

import os
import tempfile
import time
import hashlib
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
from app.models.image import DocumentImage
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
            # 优先从解析阶段给出的统计读取，避免因未返回 elements 列表而显示为 0
            try:
                elements_count = int(parse_result.get('metadata', {}).get('element_count'))
            except Exception:
                elements_count = 0
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
        
        # 创建文档分块（支持100%还原：记录element_index范围）
        chunk_start = time.time()
        text_content = parse_result.get("text_content", "")
        text_element_index_map = parse_result.get("text_element_index_map", [])  # 文本元素索引映射
        logger.debug(f"[任务ID: {task_id}] 分块输入: 文本长度={len(text_content)} 字符, 文本元素映射数={len(text_element_index_map)}")
        
        # 调用改进后的分块方法，传入 text_element_index_map
        chunks_with_index = unstructured_service.chunk_text(
            text_content, 
            text_element_index_map=text_element_index_map
        )
        chunk_time = time.time() - chunk_start
        
        # 兼容处理：如果是旧格式（纯字符串列表），转换为新格式
        if chunks_with_index and isinstance(chunks_with_index[0], str):
            chunks = chunks_with_index
            chunks_metadata = []
        else:
            chunks = [chunk.get('content', '') for chunk in chunks_with_index]
            chunks_metadata = chunks_with_index
        
        logger.info(f"[任务ID: {task_id}] 文档分块完成: 耗时={chunk_time:.2f}秒, 共生成 {len(chunks)} 个分块")
        
        if len(chunks) == 0:
            logger.warning(f"[任务ID: {task_id}] 警告: 未生成任何分块，可能文本内容为空")
        else:
            total_chunk_length = sum(len(chunk) for chunk in chunks)
            avg_chunk_length = total_chunk_length / len(chunks)
            logger.debug(f"[任务ID: {task_id}] 分块统计: 总字符数={total_chunk_length}, 平均分块长度={avg_chunk_length:.0f} 字符")
        
        # 合并“表格块”：将 tables 融入分块序列，按 element_index 顺序排序
        logger.debug(f"[任务ID: {task_id}] 步骤5.1/7: 合并表格块并保存到数据库（含element_index）")
        tables_meta = parse_result.get('tables', [])
        merged_items = []
        # 收集文本块
        for i, chunk_content in enumerate(chunks):
            element_index_start = None
            element_index_end = None
            if chunks_metadata and i < len(chunks_metadata):
                element_index_start = chunks_metadata[i].get('element_index_start')
                element_index_end = chunks_metadata[i].get('element_index_end')
            # 定位排序用的 pos：优先使用 element_index_start；缺失则使用一个递增的偏移
            pos = element_index_start if element_index_start is not None else (10_000_000 + i)
            merged_items.append({
                'type': 'text',
                'content': chunk_content,
                'pos': pos,
                'meta': {
                    'chunk_index': i,
                    'element_index_start': element_index_start,
                    'element_index_end': element_index_end
                }
            })

        # 收集表格块
        for tbl in tables_meta:
            try:
                tbl_index = tbl.get('element_index')
                tbl_text = tbl.get('table_text') or ''
                tbl_data = tbl.get('table_data')
                merged_items.append({
                    'type': 'table',
                    'content': tbl_text,
                    'pos': tbl_index if tbl_index is not None else 9_000_000,
                    'meta': {
                        'element_index': tbl_index,
                        'table_data': tbl_data
                    }
                })
            except Exception:
                continue

        # 重新按 pos 排序并重建 chunk_index
        merged_items.sort(key=lambda x: (x.get('pos') is None, x.get('pos')))

        # 保存分块到数据库（按配置决定是否存正文，同时保存 element_index 范围/表格数据）
        store_text = getattr(settings, 'STORE_CHUNK_TEXT_IN_DB', False)
        import json

        for new_index, item in enumerate(merged_items):
            chunk_metadata = item['meta'] or {}
            chunk_metadata['chunk_index'] = new_index
            chunk = DocumentChunk(
                document_id=document_id,
                content=item['content'] if store_text else "",
                chunk_index=new_index,
                chunk_type=item['type'],
                meta=json.dumps(chunk_metadata, ensure_ascii=False)
            )
            db.add(chunk)
            if (new_index + 1) % 50 == 0:
                logger.debug(f"[任务ID: {task_id}] 已保存 {new_index + 1}/{len(merged_items)} 个分块到数据库")
        
        db.commit()
        logger.info(f"[任务ID: {task_id}] 分块数据已保存到数据库: 共 {len(merged_items)} 条记录（含element_index范围/表格）")

        # 将全文分块归档到 MinIO（同时保存 element_index 信息）
        try:
            minio = MinioStorageService()
            # 保存带索引信息的分块数据
            chunks_for_storage = []
            for i, item in enumerate(merged_items):
                chunk_data = {
                    'index': i,
                    'content': item['content'],
                    'chunk_type': item['type']
                }
                meta = item.get('meta') or {}
                if 'element_index_start' in meta:
                    chunk_data['element_index_start'] = meta.get('element_index_start')
                if 'element_index_end' in meta:
                    chunk_data['element_index_end'] = meta.get('element_index_end')
                if 'element_index' in meta:
                    chunk_data['element_index'] = meta.get('element_index')
                chunks_for_storage.append(chunk_data)
            minio.upload_chunks(str(document_id), chunks_for_storage)
            logger.info(f"[任务ID: {task_id}] 分块JSON已归档到 MinIO（含element_index）")
        except Exception as e:
            logger.warning(f"[任务ID: {task_id}] 分块归档到 MinIO 失败: {e}")

        # 图片处理流水线（若解析结果包含图片二进制，则落 MinIO + 入库 + 向量化 + 索引）
        try:
            images_meta = parse_result.get('images', [])
            if images_meta:
                try:
                    total_images = len(images_meta)
                    with_data = sum(1 for _img in images_meta if (_img.get('data') or _img.get('bytes')))
                    logger.info(f"[任务ID: {task_id}] 解析到图片: {total_images} 张，其中含二进制数据: {with_data}/{total_images}")
                    if with_data == 0:
                        logger.warning(f"[任务ID: {task_id}] 警告：所有图片均缺少二进制数据(data/bytes)，将无法持久化。")
                except Exception:
                    pass
                img_service = ImageService(db)
                vector_service = VectorService(db)
                os_service = OpenSearchService()
                saved = 0
                for img in images_meta:
                    data = img.get('data') or img.get('bytes')
                    if not data:
                        continue
                    
                    # 步骤1：创建或获取图片记录（基于SHA256去重）
                    # 注意：如果图片已存在（SHA256相同），会直接返回已存在的记录，不会重复上传到MinIO
                    image_sha256 = hashlib.sha256(data).hexdigest()
                    
                    # 获取图片的 element_index（用于100%还原文档顺序）
                    element_index = img.get('element_index')  # 从解析结果中获取
                    
                    # 先检查图片是否已存在（用于判断是否需要生成向量）
                    existing_image = db.query(DocumentImage).filter(
                        DocumentImage.sha256_hash == image_sha256,
                        DocumentImage.is_deleted == False
                    ).first()
                    is_new_image = existing_image is None
                    
                    # 创建或获取图片记录
                    image_row = img_service.create_image_from_bytes(document_id, data, image_ext=img.get('ext', '.png'), image_type=img.get('image_type'))
                    
                    # 保存 element_index 到图片的 metadata JSON 中（关键：用于100%还原）
                    if element_index is not None:
                        import json
                        try:
                            existing_meta = {}
                            if image_row.meta:
                                existing_meta = json.loads(image_row.meta) if isinstance(image_row.meta, str) else image_row.meta
                            existing_meta['element_index'] = element_index
                            image_row.meta = json.dumps(existing_meta, ensure_ascii=False)
                            db.commit()
                            logger.debug(f"[任务ID: {task_id}] 图片 {image_row.id} 已保存 element_index={element_index}")
                        except Exception as e:
                            logger.warning(f"[任务ID: {task_id}] 保存图片 element_index 失败: {e}")
                            db.rollback()
                    
                    # 步骤2：检查图片是否已有向量（避免重复生成）
                    # 注意：相同图片（SHA256相同）复用向量，不重复生成
                    image_vector = None
                    if not is_new_image:
                        # 图片已存在，尝试从OpenSearch获取已有向量（使用同步方法）
                        try:
                            response = os_service.client.get(
                                index=os_service.image_index,
                                id=f"image_{image_row.id}"
                            )
                            existing_vector = response.get("_source", {}).get("image_vector")
                            if existing_vector and len(existing_vector) == 512:
                                # 图片已存在且有向量，复用向量（跳过向量生成）
                                image_vector = existing_vector
                                logger.info(f"[任务ID: {task_id}] 图片 {image_row.id} (SHA256: {image_sha256[:8]}...) 已存在，复用向量（跳过向量生成和重复上传）")
                        except Exception:
                            # 索引不存在或图片未索引，需要生成向量
                            logger.debug(f"[任务ID: {task_id}] 图片 {image_row.id} 未在OpenSearch中找到向量，将生成新向量")
                    
                    # 步骤3：如果是新图片或没有向量，生成向量（优先内存，失败回退临时文件）
                    if not image_vector:
                        image_vector = vector_service.generate_image_embedding_prefer_memory(data)
                        logger.info(f"[任务ID: {task_id}] 图片 {image_row.id} 向量生成完成，维度: {len(image_vector)}")
                    
                    # 步骤4：索引到 OpenSearch（更新索引，记录图片与当前文档的关联）
                    # 注意：即使图片已存在，也需要更新索引以反映图片与当前文档的关联关系
                    try:
                        # 构建 metadata（包含 element_index，用于100%还原）
                        image_metadata = img.get('metadata', {})
                        if element_index is not None:
                            image_metadata['element_index'] = element_index
                        
                        os_service.index_image_sync({
                            "image_id": image_row.id,
                            "document_id": document.id,  # 更新为当前文档ID
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
                            "element_index": element_index,  # 关键：记录 element_index 用于100%还原
                            "created_at": getattr(image_row, 'created_at', None).isoformat() if getattr(image_row, 'created_at', None) else None,
                            "updated_at": getattr(image_row, 'updated_at', None).isoformat() if getattr(image_row, 'updated_at', None) else None,
                            "metadata": image_metadata,
                            "processing_status": getattr(image_row, 'status', 'completed'),
                            "model_version": "1.0",
                        })
                        logger.info(f"[任务ID: {task_id}] 图片 {image_row.id} 索引完成（element_index={element_index}）")
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
        db_chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).order_by(DocumentChunk.chunk_index).all()
        
        logger.info(f"[任务ID: {task_id}] 开始向量化: 共 {len(db_chunks)} 个分块需要处理")
        if len(db_chunks) == 0:
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
        
        # 准备文本迭代器：当不在DB存正文时，从 MinIO 的 chunks.jsonl.gz 流式读取
        def _stream_chunk_texts_from_minio(doc_id: int):
            try:
                minio = MinioStorageService()
                files = minio.list_files("documents/")
                needle = f"/{doc_id}/parsed/chunks/chunks.jsonl.gz"
                target = None
                for fobj in files:
                    if fobj.get("object_name", "").endswith(needle):
                        target = fobj["object_name"]
                        break
                if not target:
                    logger.warning(f"[任务ID: {task_id}] 未找到 MinIO 分块归档，回退使用内存分块")
                    for t in chunks:
                        yield t
                    return
                import gzip, json
                response = minio.client.get_object(minio.bucket_name, target)
                try:
                    with gzip.GzipFile(fileobj=response, mode='rb') as gz:
                        for line in gz:
                            try:
                                item = json.loads(line)
                                yield item.get("content", "")
                            except Exception:
                                yield ""
                finally:
                    try:
                        response.close(); response.release_conn()
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"[任务ID: {task_id}] 从 MinIO 流式读取分块失败: {e}，回退内存分块")
                for t in chunks:
                    yield t

        store_text = getattr(settings, 'STORE_CHUNK_TEXT_IN_DB', False)
        text_iter = iter([c if isinstance(c, str) else str(c) for c in chunks]) if store_text else _stream_chunk_texts_from_minio(document_id)

        docs_to_index = []
        for i, chunk in enumerate(db_chunks):
            chunk_start = time.time()
            
            try:
                # 获取对应文本，StopIteration 时置空
                try:
                    chunk_text = next(text_iter)
                except StopIteration:
                    chunk_text = ""
                # 跳过空内容分块
                if not (chunk_text or "").strip():
                    logger.warning(f"[任务ID: {task_id}] 分块 {chunk.id} 内容为空，跳过向量化与索引")
                    continue
                # 生成向量（Ollama不可用时将返回空列表，允许继续索引文本）
                vector = vector_service.generate_embedding(chunk_text)
                vectorize_time = time.time() - chunk_start
                
                # 构建索引文档
                chunk_doc = {
                    "document_id": document_id,
                    "chunk_id": chunk.id,
                    "knowledge_base_id": document.knowledge_base_id,
                    "category_id": document.category_id if hasattr(document, 'category_id') else None,
                    "content": chunk_text,
                    "chunk_type": chunk.chunk_type if hasattr(chunk, 'chunk_type') else "text",
                    "metadata": {"chunk_index": i},
                    "created_at": chunk.created_at.isoformat() if chunk.created_at else None
                }
                # 仅当有有效向量时写入
                if isinstance(vector, list) and len(vector) > 0:
                    chunk_doc["content_vector"] = vector
                docs_to_index.append(chunk_doc)
                
                index_time = 0.0
                
                success_count += 1
                
                if (i + 1) % 10 == 0 or i == len(db_chunks) - 1:  # 每10个或最后一个记录日志
                    logger.info(f"[任务ID: {task_id}] 向量化进度: {i+1}/{len(chunks)} "
                               f"(分块ID={chunk.id}, 向量维度={len(vector)}, "
                               f"向量化耗时={vectorize_time:.2f}秒, 索引耗时={index_time:.2f}秒)")
                else:
                    logger.debug(f"[任务ID: {task_id}] 分块 {chunk.id} 处理完成: "
                               f"向量维度={len(vector)}, 向量化={vectorize_time:.2f}秒, 索引={index_time:.2f}秒")
                
            except Exception as e:
                error_count += 1
                logger.error(f"[任务ID: {task_id}] 分块 {chunk.id} (索引 {i+1}/{len(chunks)}) 处理失败: {e}", exc_info=True)
                continue
            
            # 更新任务进度
            progress = 60 + (i / max(1, len(db_chunks))) * 30
            current_task.update_state(
                state="PROGRESS",
                meta={"current": int(progress), "total": 100, "status": f"向量化中 ({i+1}/{len(chunks)})"}
            )
        
        # 批量索引到 OpenSearch（默认不刷新，提升吞吐）
        try:
            bulk_index_start = time.time()
            opensearch_service.bulk_index_document_chunks_sync(docs_to_index)
            bulk_index_time = time.time() - bulk_index_start
            logger.info(f"[任务ID: {task_id}] 批量索引完成，耗时={bulk_index_time:.2f}秒，总文档={len(docs_to_index)}")
        except Exception as e:
            logger.error(f"[任务ID: {task_id}] 批量索引失败: {e}", exc_info=True)
            # 批量索引失败不再抛出，避免任务整体失败
            pass
        
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

        # 若不存在任何文档版本，则创建初始版本 v1（以原始文件为基准）
        try:
            from app.models.version import DocumentVersion
            existing_count = db.query(DocumentVersion).filter(
                DocumentVersion.document_id == document_id,
                DocumentVersion.is_deleted == False
            ).count()
            if existing_count == 0:
                initial_version = DocumentVersion(
                    document_id=document_id,
                    version_number=1,
                    version_type="auto",
                    description="初始版本",
                    file_path=document.file_path or "",
                    file_size=document.file_size,
                    file_hash=document.file_hash,
                )
                db.add(initial_version)
                db.commit()
                logger.info(f"[任务ID: {task_id}] 已创建文档初始版本 v1 (document_id={document_id})")
        except Exception as ver_err:
            logger.warning(f"[任务ID: {task_id}] 创建初始版本失败（不影响主流程）: {ver_err}")
        
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
        
        # 获取所有块（不重新解析文件），按 chunk_index 排序
        db_chunks = db.query(DocumentChunk).filter(
            DocumentChunk.document_id == document_id
        ).order_by(DocumentChunk.chunk_index).all()
        
        logger.info(f"文档 {document_id} 共有 {len(db_chunks)} 个块需要重新向量化")
        
        # 向量化处理：从 MinIO 流式读取文本（避免内存占用）
        def _stream_chunk_texts_from_minio(doc_id: int):
            try:
                minio = MinioStorageService()
                files = minio.list_files("documents/")
                needle = f"/{doc_id}/parsed/chunks/chunks.jsonl.gz"
                target = None
                for fobj in files:
                    if fobj.get("object_name", "").endswith(needle):
                        target = fobj["object_name"]
                        break
                if not target:
                    logger.warning(f"重新向量化：未找到 MinIO 分块归档，文档ID={doc_id}")
                    return
                import gzip, json
                response = minio.client.get_object(minio.bucket_name, target)
                try:
                    with gzip.GzipFile(fileobj=response, mode='rb') as gz:
                        for line in gz:
                            try:
                                item = json.loads(line)
                                yield item.get("content", "")
                            except Exception:
                                yield ""
                finally:
                    try:
                        response.close(); response.release_conn()
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f"重新向量化：从 MinIO 流式读取分块失败: {e}", exc_info=True)
                return

        vector_service = VectorService(db)
        opensearch_service = OpenSearchService()
        store_text = getattr(settings, 'STORE_CHUNK_TEXT_IN_DB', False)
        text_iter = _stream_chunk_texts_from_minio(document_id) if not store_text else None
        success_count = 0
        error_count = 0
        
        for i, chunk in enumerate(db_chunks):
            # 获取文本：优先从 MinIO 流式读取，否则从 DB
            if store_text:
                chunk_text = chunk.content or ""
            else:
                try:
                    chunk_text = next(text_iter) if text_iter else ""
                except (StopIteration, TypeError):
                    chunk_text = ""
            # 跳过空内容分块
            if not (chunk_text or "").strip():
                logger.warning(f"分块 {chunk.id} 内容为空，跳过重新向量化")
                continue
            try:
                # 生成向量
                vector = vector_service.generate_embedding(chunk_text)
                
                # 构建索引文档
                import json as _json
                meta_raw = getattr(chunk, 'meta', getattr(chunk, 'metadata', {}))
                meta_text = meta_raw if isinstance(meta_raw, str) else _json.dumps(meta_raw, ensure_ascii=False)
                chunk_doc = {
                    "document_id": document_id,
                    "chunk_id": chunk.id,
                    "knowledge_base_id": document.knowledge_base_id,
                    "category_id": document.category_id if hasattr(document, 'category_id') else None,
                    "content": chunk_text,
                    "chunk_type": getattr(chunk, 'chunk_type', "text"),
                    "metadata": meta_text,
                    "content_vector": vector,
                    "version": getattr(chunk, 'version', 1),
                    "created_at": chunk.created_at.isoformat() if chunk.created_at else None
                }
                
                # 更新OpenSearch索引
                opensearch_service.index_document_chunk_sync(chunk_doc)
                logger.debug(f"分块 {chunk.id} 重新向量化完成")
                success_count += 1
            except Exception as e:
                error_count += 1
                logger.error(f"分块 {chunk.id} 重新向量化失败: {e}", exc_info=True)
                continue
        
        logger.info(f"文档 {document_id} 重新向量化完成: 成功={success_count}, 失败={error_count}, 总块数={len(db_chunks)}")
        
        # 更新文档状态为完成
        document.status = DOC_STATUS_COMPLETED
        document.processing_progress = 100.0
        db.commit()
        
        return {
            "status": "success",
            "message": "重新向量化完成",
            "chunks_count": len(db_chunks),
            "success_count": success_count,
            "error_count": error_count
        }
        
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
