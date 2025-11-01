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
            
            # 如果DOCX转换为了PDF，保存PDF到MinIO并更新数据库
            # 注意：必须在清理临时文件之前完成，否则PDF会被删除
            converted_pdf_path = None
            converted_pdf_dir = None
            if parse_result.get('is_converted_pdf') and parse_result.get('converted_pdf_path'):
                converted_pdf_path = parse_result.get('converted_pdf_path')
                converted_pdf_dir = os.path.dirname(converted_pdf_path) if converted_pdf_path else None
                
                if converted_pdf_path and os.path.exists(converted_pdf_path):
                    logger.info(f"[任务ID: {task_id}] 检测到转换后的PDF，开始保存到MinIO: {converted_pdf_path}")
                    try:
                        minio = MinioStorageService()
                        
                        # 上传PDF到MinIO
                        upload_result = minio.upload_pdf_file(
                            pdf_file_path=converted_pdf_path,
                            document_id=document.id,
                            original_filename=os.path.splitext(document.original_filename)[0]
                        )
                        
                        # 更新数据库中的converted_pdf_url
                        document.converted_pdf_url = upload_result['object_name']
                        db.commit()
                        
                        logger.info(f"[任务ID: {task_id}] PDF已保存到MinIO: {upload_result['object_name']}, "
                                  f"数据库已更新converted_pdf_url")
                        
                        # PDF已成功保存，现在可以清理临时文件
                        try:
                            os.remove(converted_pdf_path)
                            logger.debug(f"[任务ID: {task_id}] 已删除临时PDF文件: {converted_pdf_path}")
                        except Exception as e:
                            logger.warning(f"[任务ID: {task_id}] 删除临时PDF文件失败: {e}")
                    except Exception as e:
                        logger.error(f"[任务ID: {task_id}] 保存PDF到MinIO失败: {e}", exc_info=True)
                        # 不影响主流程，但需要清理临时PDF
                        try:
                            if converted_pdf_path and os.path.exists(converted_pdf_path):
                                os.remove(converted_pdf_path)
                        except Exception:
                            pass
                else:
                    logger.warning(f"[任务ID: {task_id}] 转换后的PDF文件不存在: {converted_pdf_path}")
        except Exception as e:
            logger.error(f"[任务ID: {task_id}] Unstructured解析失败: {e}", exc_info=True)
            raise
        
        # 3. 清理临时文件（包括临时目录，但PDF文件已在上面处理）
        logger.debug(f"[任务ID: {task_id}] 步骤4.1/7: 清理临时文件")
        try:
            # 删除原始临时文件
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            
            # 清理PDF临时目录（如果存在且为空）
            if converted_pdf_dir and os.path.isdir(converted_pdf_dir):
                try:
                    # 尝试删除目录内容（如果有残留）
                    import shutil
                    if not os.listdir(converted_pdf_dir):
                        os.rmdir(converted_pdf_dir)
                    else:
                        # 如果目录不为空，尝试强制删除
                        shutil.rmtree(converted_pdf_dir)
                    logger.debug(f"[任务ID: {task_id}] 已清理PDF临时目录: {converted_pdf_dir}")
                except Exception as e:
                    logger.debug(f"[任务ID: {task_id}] 清理PDF临时目录失败（可能已被清理）: {e}")
            
            # 删除主临时目录
            if os.path.isdir(temp_dir):
                try:
                    os.rmdir(temp_dir)
                except OSError:
                    # 如果目录不为空，可能是PDF目录还在，尝试清理
                    try:
                        import shutil
                        shutil.rmtree(temp_dir)
                    except Exception:
                        pass
            
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
            page_number = None
            
            if chunks_metadata and i < len(chunks_metadata):
                element_index_start = chunks_metadata[i].get('element_index_start')
                element_index_end = chunks_metadata[i].get('element_index_end')
            
            # ✅ 新增：从 text_element_index_map 中提取 page_number 和 coordinates
            # 如果 element_index_start 和 element_index_end 都存在，查找对应的信息
            page_numbers = []
            coordinates_list = []  # 收集所有坐标，用于计算合并坐标
            
            if text_element_index_map:
                # 查找 element_index_start 到 element_index_end 范围内的所有信息
                if element_index_start is not None and element_index_end is not None:
                    for map_item in text_element_index_map:
                        elem_idx = map_item.get('element_index')
                        if element_index_start <= elem_idx <= element_index_end:
                            page_num = map_item.get('page_number')
                            if page_num is not None and page_num not in page_numbers:
                                page_numbers.append(page_num)
                            
                            # ✅ 收集坐标信息（用于后续计算合并坐标）
                            coords = map_item.get('coordinates')
                            if coords and isinstance(coords, dict):
                                # 确保坐标有有效值
                                if coords.get('x', 0) > 0 or coords.get('y', 0) > 0:
                                    coordinates_list.append(coords)
                elif element_index_start is not None:
                    # 只有 start，只查找对应的
                    for map_item in text_element_index_map:
                        if map_item.get('element_index') == element_index_start:
                            page_num = map_item.get('page_number')
                            if page_num is not None:
                                page_numbers.append(page_num)
                            
                            # ✅ 获取起始元素的坐标
                            coords = map_item.get('coordinates')
                            if coords and isinstance(coords, dict):
                                if coords.get('x', 0) > 0 or coords.get('y', 0) > 0:
                                    coordinates_list.append(coords)
                            break
                
                # 取主要的 page_number（第一个，通常是起始页码）
                if page_numbers:
                    page_number = page_numbers[0]
            
            # ✅ 计算合并后的坐标（如果 chunk 跨越多个元素，合并坐标范围）
            chunk_coordinates = None
            if coordinates_list:
                if len(coordinates_list) == 1:
                    # 只有一个坐标，直接使用
                    chunk_coordinates = coordinates_list[0]
                else:
                    # 多个坐标，计算合并后的边界框
                    min_x = min(c.get('x', 0) for c in coordinates_list)
                    min_y = min(c.get('y', 0) for c in coordinates_list)
                    max_x = max((c.get('x', 0) + c.get('width', 0)) for c in coordinates_list)
                    max_y = max((c.get('y', 0) + c.get('height', 0)) for c in coordinates_list)
                    chunk_coordinates = {
                        'x': min_x,
                        'y': min_y,
                        'width': max_x - min_x,
                        'height': max_y - min_y
                    }
            
            # 定位排序用的 pos：优先使用 element_index_start；缺失则使用一个递增的偏移
            pos = element_index_start if element_index_start is not None else (10_000_000 + i)
            
            # 构建 chunk metadata（包含 page_number 和 coordinates）
            chunk_meta = {
                'chunk_index': i,
                'element_index_start': element_index_start,
                'element_index_end': element_index_end,
                # ✅ 新增：保存 page_number
                'page_number': page_number,
                # ✅ 新增：保存 coordinates（用于坐标重叠度计算）
                'coordinates': chunk_coordinates
            }
            
            # 如果跨多页，保存 page_number_range（优化：避免重复查找）
            if page_numbers and len(page_numbers) > 1:
                chunk_meta['page_number_range'] = sorted(page_numbers)
            
            merged_items.append({
                'type': 'text',
                'content': chunk_content,
                'pos': pos,
                'meta': chunk_meta
            })

        # 收集表格块
        for tbl in tables_meta:
            try:
                tbl_index = tbl.get('element_index')
                tbl_text = tbl.get('table_text') or ''
                tbl_data = tbl.get('table_data')
                # ✅ 新增：从表格元数据中获取 page_number
                tbl_page_number = tbl.get('page_number')
                merged_items.append({
                    'type': 'table',
                    'content': tbl_text,
                    'pos': tbl_index if tbl_index is not None else 9_000_000,
                    'meta': {
                        'element_index': tbl_index,
                        'table_data': tbl_data,
                        # ✅ 新增：保存 page_number
                        'page_number': tbl_page_number
                    }
                })
            except Exception:
                continue

        # 重新按 pos 排序并重建 chunk_index
        merged_items.sort(key=lambda x: (x.get('pos') is None, x.get('pos')))
        
        # ✅ 验证：检查表格是否在正确位置（基于 element_index 验证）
        logger.info(f"[任务ID: {task_id}] 开始验证表格位置正确性...")
        validation_errors = []
        table_count = 0
        text_count = 0
        
        for idx, item in enumerate(merged_items):
            item_type = item.get('type', 'unknown')
            item_pos = item.get('pos')
            item_meta = item.get('meta', {})
            
            if item_type == 'table':
                table_count += 1
                table_elem_idx = item_meta.get('element_index')
                table_page = item_meta.get('page_number')
                
                # ✅ 验证：表格必须有 element_index
                if table_elem_idx is None:
                    validation_errors.append(f"表格块 (chunk_index={idx}) 缺少 element_index，无法验证位置")
                    logger.warning(f"[任务ID: {task_id}] 表格块 (chunk_index={idx}) 缺少 element_index")
                    continue
                
                # 检查前后的文本块，验证表格是否在正确位置
                prev_item = merged_items[idx - 1] if idx > 0 else None
                next_item = merged_items[idx + 1] if idx < len(merged_items) - 1 else None
                
                validation_info = {
                    'table_pos': item_pos,
                    'table_element_index': table_elem_idx,
                    'table_page': table_page,
                    'chunk_index_after_sort': idx
                }
                
                # 验证前一个块
                if prev_item:
                    prev_type = prev_item.get('type')
                    prev_pos = prev_item.get('pos')
                    prev_meta = prev_item.get('meta', {})
                    prev_elem_start = prev_meta.get('element_index_start') or prev_meta.get('element_index')
                    prev_elem_end = prev_meta.get('element_index_end')
                    
                    validation_info['prev_type'] = prev_type
                    validation_info['prev_pos'] = prev_pos
                    validation_info['prev_elem_start'] = prev_elem_start
                    validation_info['prev_elem_end'] = prev_elem_end
                    
                    # 验证：如果前一个块是文本块且有 element_index_end，检查排序是否正确
                    # 注意：表格可能在文本块的 element_index_end 之后，这是正确的
                    # 但如果表格的 element_index 小于文本块的 element_index_start，那就有问题
                    if prev_type == 'text' and prev_elem_start is not None and table_elem_idx is not None:
                        if table_elem_idx < prev_elem_start:
                            validation_errors.append(f"位置错误: 表格 element_index ({table_elem_idx}) 小于前一个文本块的 element_index_start ({prev_elem_start})")
                    elif prev_pos is not None and item_pos is not None and prev_pos >= item_pos:
                        validation_errors.append(f"位置错误: 表格 (pos={item_pos}) 应该在前一个块 (pos={prev_pos}) 之后")
                
                # 验证后一个块
                if next_item:
                    next_type = next_item.get('type')
                    next_pos = next_item.get('pos')
                    next_meta = next_item.get('meta', {})
                    next_elem_start = next_meta.get('element_index_start') or next_meta.get('element_index')
                    
                    validation_info['next_type'] = next_type
                    validation_info['next_pos'] = next_pos
                    validation_info['next_elem_start'] = next_elem_start
                    
                    # 验证：如果后一个块是文本块，表格的 element_index 应该在后一个块之前
                    if next_type == 'text' and next_elem_start is not None and table_elem_idx is not None:
                        if table_elem_idx >= next_elem_start:
                            validation_info['warning'] = f"表格 element_index ({table_elem_idx}) 应该在后一个文本块之前 ({next_elem_start})"
                    elif next_pos is not None and item_pos is not None and item_pos >= next_pos:
                        validation_errors.append(f"位置错误: 表格 (pos={item_pos}) 应该在后一个块 (pos={next_pos}) 之前")
                
                logger.info(f"[任务ID: {task_id}] 表格验证 (chunk_index={idx}): {validation_info}")
        
        # ✅ 验证：检查是否有表格丢失或重复
        parsed_table_count = len(tables_meta)
        if table_count != parsed_table_count:
            validation_errors.append(f"表格数量不匹配: 解析到 {parsed_table_count} 个表格，但合并后只有 {table_count} 个表格块")
            logger.warning(f"[任务ID: {task_id}] 表格数量不匹配: 解析={parsed_table_count}, 合并={table_count}")
        
        # ✅ 验证：检查表格的 element_index 是否有重复
        table_indices = [item.get('meta', {}).get('element_index') 
                         for item in merged_items 
                         if item.get('type') == 'table' and item.get('meta', {}).get('element_index') is not None]
        if len(table_indices) != len(set(table_indices)):
            duplicates = [idx for idx in table_indices if table_indices.count(idx) > 1]
            validation_errors.append(f"发现重复的表格 element_index: {duplicates}")
            logger.warning(f"[任务ID: {task_id}] 发现重复的表格 element_index: {duplicates}")
        
        if validation_errors:
            logger.warning(f"[任务ID: {task_id}] 表格位置验证发现 {len(validation_errors)} 个错误:")
            for error in validation_errors:
                logger.warning(f"[任务ID: {task_id}]   - {error}")
        else:
            logger.info(f"[任务ID: {task_id}] ✅ 表格位置验证通过: 所有表格都在正确位置 (共 {table_count} 个表格)")
        
        # ✅ 记录排序后的块顺序（前10个和后10个，用于调试）
        total_items = len(merged_items)
        log_items = merged_items[:10] + (merged_items[-10:] if total_items > 20 else [])
        logger.info(f"[任务ID: {task_id}] 排序后的块顺序（前10个{'和后10个' if total_items > 20 else ''}）:")
        for idx, item in enumerate(log_items):
            actual_idx = idx if idx < 10 else (total_items - 10 + (idx - 10))
            item_type = item.get('type')
            item_pos = item.get('pos')
            item_meta = item.get('meta', {})
            if item_type == 'table':
                elem_idx = item_meta.get('element_index')
                logger.info(f"[任务ID: {task_id}]   [{actual_idx}] {item_type}: pos={item_pos}, element_index={elem_idx}")
            else:
                elem_start = item_meta.get('element_index_start')
                elem_end = item_meta.get('element_index_end')
                logger.info(f"[任务ID: {task_id}]   [{actual_idx}] {item_type}: pos={item_pos}, element_index_range=({elem_start}, {elem_end})")
        
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
        
        # ✅ 统计信息
        text_chunks = sum(1 for item in merged_items if item.get('type') == 'text')
        table_chunks = sum(1 for item in merged_items if item.get('type') == 'table')
        logger.info(f"[任务ID: {task_id}] 分块数据已保存到数据库: 共 {len(merged_items)} 条记录（文本块={text_chunks}, 表格块={table_chunks}）")

        # 将全文分块归档到 MinIO（同时保存 element_index 信息）
        try:
            minio = MinioStorageService()
            # 保存带索引信息的分块数据（✅ 新增：包含 coordinates 和 page_number）
            chunks_for_storage = []
            for i, item in enumerate(merged_items):
                chunk_data = {
                    'index': i,
                    'content': item['content'],
                    'chunk_type': item['type']
                }
                meta = item.get('meta') or {}
                # 保存 element_index 信息
                if 'element_index_start' in meta:
                    chunk_data['element_index_start'] = meta.get('element_index_start')
                if 'element_index_end' in meta:
                    chunk_data['element_index_end'] = meta.get('element_index_end')
                if 'element_index' in meta:
                    chunk_data['element_index'] = meta.get('element_index')
                # ✅ 新增：保存 page_number 和 coordinates（用于坐标重叠度计算）
                if 'page_number' in meta:
                    chunk_data['page_number'] = meta.get('page_number')
                if 'coordinates' in meta and meta.get('coordinates'):
                    chunk_data['coordinates'] = meta.get('coordinates')
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
                    
                    # ✅ 保存 element_index 和 page_number 到图片的 metadata JSON 中（关键：用于100%还原和关联查找）
                    element_index = img.get('element_index')
                    page_number = img.get('page_number')
                    if element_index is not None or page_number is not None:
                        import json
                        try:
                            existing_meta = {}
                            if image_row.meta:
                                existing_meta = json.loads(image_row.meta) if isinstance(image_row.meta, str) else image_row.meta
                            if element_index is not None:
                                existing_meta['element_index'] = element_index
                            if page_number is not None:
                                existing_meta['page_number'] = page_number
                            # 同时保存 coordinates（如果存在）
                            coordinates = img.get('coordinates')
                            if coordinates:
                                existing_meta['coordinates'] = coordinates
                            image_row.meta = json.dumps(existing_meta, ensure_ascii=False)
                            db.commit()
                            logger.debug(f"[任务ID: {task_id}] 图片 {image_row.id} 已保存 element_index={element_index}, page_number={page_number}")
                        except Exception as e:
                            logger.warning(f"[任务ID: {task_id}] 保存图片 metadata 失败: {e}")
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
                
                # ✅ 优化：对于表格块，从 meta 中提取完整的表格数据并生成完整文本
                chunk_meta_dict = {}  # 确保在所有情况下都有定义
                if chunk.chunk_type == 'table' and chunk.meta:
                    try:
                        chunk_meta_dict = json.loads(chunk.meta) if isinstance(chunk.meta, str) else chunk.meta
                        table_data = chunk_meta_dict.get('table_data', {})
                        
                        # 优先使用结构化单元格数据生成完整文本
                        if table_data.get('cells'):
                            cells = table_data['cells']
                            text_lines = []
                            for row in cells:
                                if isinstance(row, (list, tuple)):
                                    # 使用制表符分隔，保持列对齐
                                    row_text = '\t'.join(str(cell) if cell is not None else '' for cell in row)
                                    text_lines.append(row_text)
                                else:
                                    text_lines.append(str(row))
                            chunk_text = '\n'.join(text_lines)
                            logger.debug(f"[任务ID: {task_id}] 表格块 {chunk.id}: 从结构化数据生成完整文本 ({len(text_lines)} 行)")
                        # 如果没有 cells，尝试使用 HTML（至少包含结构化信息）
                        elif table_data.get('html'):
                            # ✅ 修复：正确解析 HTML 表格结构，保持行列关系
                            try:
                                import re
                                html_text = table_data['html']
                                
                                # 方法1：使用 BeautifulSoup（如果可用）
                                try:
                                    from bs4 import BeautifulSoup
                                    soup = BeautifulSoup(html_text, 'html.parser')
                                    table = soup.find('table')
                                    if table:
                                        text_lines = []
                                        for tr in table.find_all('tr'):
                                            row_cells = []
                                            for td in tr.find_all(['td', 'th']):
                                                cell_text = td.get_text(strip=True)
                                                row_cells.append(cell_text)
                                            if row_cells:
                                                # 使用制表符分隔同一行的单元格
                                                text_lines.append('\t'.join(row_cells))
                                        
                                        if text_lines:
                                            # 使用换行符分隔不同行
                                            chunk_text = '\n'.join(text_lines)
                                            logger.debug(f"[任务ID: {task_id}] 表格块 {chunk.id}: 从 HTML (BeautifulSoup) 提取文本 ({len(text_lines)} 行)")
                                except ImportError:
                                    # 方法2：使用正则表达式解析（兜底方案）
                                    tr_pattern = r'<tr[^>]*>(.*?)</tr>'
                                    td_pattern = r'<t[dh][^>]*>(.*?)</t[dh]>'
                                    
                                    trs = re.findall(tr_pattern, html_text, re.DOTALL | re.IGNORECASE)
                                    if trs:
                                        text_lines = []
                                        for tr_content in trs:
                                            tds = re.findall(td_pattern, tr_content, re.DOTALL | re.IGNORECASE)
                                            if tds:
                                                row_cells = []
                                                for td in tds:
                                                    # 移除内嵌的 HTML 标签
                                                    cell_text = re.sub(r'<[^>]+>', '', td)
                                                    # 处理 HTML 实体
                                                    cell_text = cell_text.replace('&nbsp;', ' ').replace('&amp;', '&')
                                                    cell_text = ' '.join(cell_text.split()).strip()
                                                    row_cells.append(cell_text)
                                                
                                                if row_cells:
                                                    text_lines.append('\t'.join(row_cells))
                                        
                                        if text_lines:
                                            chunk_text = '\n'.join(text_lines)
                                            logger.debug(f"[任务ID: {task_id}] 表格块 {chunk.id}: 从 HTML (正则) 提取文本 ({len(text_lines)} 行)")
                            except Exception as e:
                                logger.warning(f"[任务ID: {task_id}] 表格块 {chunk.id}: 从 HTML 提取文本失败: {e}")
                                chunk_text = None  # 继续使用原始的 table_text
                        # 如果都没有，使用原始的 table_text（已在上面获取）
                        if chunk_text:
                            logger.debug(f"[任务ID: {task_id}] 表格块 {chunk.id} 最终文本长度: {len(chunk_text)}")
                    except Exception as e:
                        logger.warning(f"[任务ID: {task_id}] 表格块 {chunk.id} 提取完整内容失败: {e}，使用原始文本")
                        # 解析失败时确保 chunk_meta_dict 至少是空字典
                        chunk_meta_dict = {}
                
                # 跳过空内容分块
                if not (chunk_text or "").strip():
                    logger.warning(f"[任务ID: {task_id}] 分块 {chunk.id} 内容为空，跳过向量化与索引")
                    continue
                
                # ✅ 优化：记录表格块的处理信息
                if chunk.chunk_type == 'table':
                    logger.info(f"[任务ID: {task_id}] 表格块 {chunk.id} 向量化: 文本长度={len(chunk_text)}, "
                               f"包含单元格数据={bool(chunk_meta_dict.get('table_data', {}).get('cells'))}")
                
                # 生成向量（Ollama不可用时将返回空列表，允许继续索引文本）
                vector = vector_service.generate_embedding(chunk_text)
                vectorize_time = time.time() - chunk_start
                
                # 构建索引文档（✅ 新增：包含完整的 metadata 信息）
                # 从 chunk.meta 中提取完整的 metadata（包含 element_index、page_number、coordinates）
                # ✅ 注意：对于表格块，chunk_meta_dict 已经在上面提取过，需要确保已定义
                if chunk.chunk_type != 'table':
                    # 非表格块，需要重新解析 meta
                    chunk_meta_dict = {}
                    if chunk.meta:
                        try:
                            chunk_meta_dict = json.loads(chunk.meta) if isinstance(chunk.meta, str) else chunk.meta
                        except:
                            pass
                # 表格块的 chunk_meta_dict 已在上面提取，直接使用
                
                # 构建 metadata（包含所有关键信息）
                chunk_metadata = {
                    "chunk_index": i
                }
                # ✅ 添加 element_index 信息
                if chunk_meta_dict.get('element_index_start') is not None:
                    chunk_metadata['element_index_start'] = chunk_meta_dict.get('element_index_start')
                if chunk_meta_dict.get('element_index_end') is not None:
                    chunk_metadata['element_index_end'] = chunk_meta_dict.get('element_index_end')
                # ✅ 添加 page_number
                if chunk_meta_dict.get('page_number') is not None:
                    chunk_metadata['page_number'] = chunk_meta_dict.get('page_number')
                # ✅ 添加 coordinates
                if chunk_meta_dict.get('coordinates'):
                    chunk_metadata['coordinates'] = chunk_meta_dict.get('coordinates')
                
                chunk_doc = {
                    "document_id": document_id,
                    "chunk_id": chunk.id,
                    "knowledge_base_id": document.knowledge_base_id,
                    "category_id": document.category_id if hasattr(document, 'category_id') else None,
                    "content": chunk_text,
                    "chunk_type": chunk.chunk_type if hasattr(chunk, 'chunk_type') else "text",
                    "metadata": chunk_metadata,  # ✅ 使用完整的 metadata
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
