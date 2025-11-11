"""
Document API Routes
"""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from typing import List, Optional
import json
from app.schemas.document import DocumentCreate, DocumentUpdate, DocumentResponse, DocumentUploadRequest
from app.services.document_service import DocumentService
from app.dependencies.database import get_db
from sqlalchemy.orm import Session
from app.core.logging import logger
from app.config.settings import settings
from app.services.chunk_service import ChunkService
from app.services.image_service import ImageService
from app.services.minio_storage_service import MinioStorageService
from app.models.document import Document
import gzip, json, io, datetime
import os, tempfile
from app.services.office_converter import convert_docx_to_pdf, compress_pdf
from app.services.opensearch_service import OpenSearchService

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
            "code": 0,
            "message": "ok",
            "data": {
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
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"上传文档API错误: {e}", exc_info=True)
        return {"code": 1, "message": f"上传文档失败: {str(e)}"}

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

@router.get("/{doc_id}/chunks")
async def get_document_chunks(
    doc_id: int,
    page: int = 1,
    size: int = settings.QA_DEFAULT_PAGE_SIZE,
    include_content: bool = False,
    db: Session = Depends(get_db)
):
    """获取指定文档的分块列表（兼容前端 /documents/{id}/chunks）"""
    try:
        skip = max(page - 1, 0) * max(size, 1)
        service = ChunkService(db)
        rows = await service.get_chunks(skip=skip, limit=size, document_id=doc_id)
        items = []

        # 若数据库未存文本，尝试从 MinIO 的 chunks.jsonl.gz 读取对应范围
        content_map = {}
        try:
            doc = db.query(Document).filter(Document.id == doc_id).first()
            if doc:
                created: datetime.datetime = getattr(doc, 'created_at', None) or datetime.datetime.utcnow()
                year = created.strftime('%Y')
                month = created.strftime('%m')
                object_name = f"documents/{year}/{month}/{doc_id}/parsed/chunks/chunks.jsonl.gz"
                minio = MinioStorageService()
                obj = minio.client.get_object(minio.bucket_name, object_name)
                gz_bytes = obj.read()
                obj.close(); obj.release_conn()
                with gzip.GzipFile(fileobj=io.BytesIO(gz_bytes), mode='rb') as gz:
                    idx_start = skip
                    idx_end = skip + size
                    current_index = 0
                    for line in gz:
                        try:
                            d = json.loads(line.decode('utf-8'))
                        except Exception:
                            continue
                        idx = d.get('index') or d.get('chunk_index')
                        if idx is None:
                            idx = current_index
                        current_index += 1
                        if idx < idx_start or idx >= idx_end:
                            continue
                        content_map[int(idx)] = d.get('content') or ''
        except Exception:
            content_map = {}

        from sqlalchemy import func
        from app.models.chunk_version import ChunkVersion
        for c in rows:
            idx = getattr(c, 'chunk_index', None)
            content = getattr(c, 'content', None)
            if (not content) and (idx is not None) and (idx in content_map):
                content = content_map[idx]
            
            # 解析 meta 字段（包含表格数据 table_data）
            meta_dict = None
            if c.meta:
                try:
                    meta_dict = json.loads(c.meta) if isinstance(c.meta, str) else c.meta
                    # ✅ 调试：检查表格块的 meta 数据
                    if getattr(c, "chunk_type", "text") == "table":
                        logger.debug(f"[表格调试] 块 #{idx} (ID={c.id}): meta_dict={meta_dict}")
                        if meta_dict and isinstance(meta_dict, dict):
                            table_data = meta_dict.get('table_data')
                            table_group_uid = meta_dict.get('table_group_uid')
                            table_id = meta_dict.get('table_id')
                            
                            # ✅ 新设计：表格数据通过 API 懒加载，meta 中只存储 table_group_uid 或 table_id
                            if table_data:
                                logger.debug(f"[表格调试] 块 #{idx}: table_data.html={bool(table_data.get('html'))}, "
                                           f"table_data.cells={bool(table_data.get('cells'))}, "
                                           f"rows={table_data.get('rows', 0)}, "
                                           f"columns={table_data.get('columns', 0)}")
                            elif table_group_uid or table_id:
                                # ✅ 有懒加载标识符，这是正常的，不需要警告
                                logger.debug(f"[表格调试] 块 #{idx}: 使用懒加载方式，table_group_uid={table_group_uid}, table_id={table_id}")
                            else:
                                # ⚠️ 既没有 table_data，也没有懒加载标识符，这才是问题
                                logger.warning(f"[表格调试] ⚠️ 块 #{idx} (ID={c.id}): meta 中既缺少 table_data，也缺少 table_group_uid/table_id！meta_dict 内容: {meta_dict.keys() if isinstance(meta_dict, dict) else 'N/A'}")
                except (json.JSONDecodeError, TypeError) as e:
                    logger.error(f"[表格调试] 解析块 #{idx} 的 meta 失败: {e}, meta_raw={c.meta[:100] if c.meta else None}")
                    meta_dict = {}
            
            # 计算版本与修改时间兜底
            try:
                max_ver = db.query(func.max(ChunkVersion.version_number)).filter(
                    ChunkVersion.chunk_id == c.id
                ).scalar() or 0
            except Exception:
                max_ver = 0
            safe_version = max(int(getattr(c, 'version', 0) or 0), int(max_ver)) or 1
            latest_ver = None
            if max_ver:
                try:
                    latest_ver = db.query(ChunkVersion).filter(
                        ChunkVersion.chunk_id == c.id,
                        ChunkVersion.version_number == int(max_ver)
                    ).first()
                except Exception:
                    latest_ver = None
            modified_dt = getattr(c, 'last_modified_at', None) or (getattr(latest_ver, 'created_at', None) if latest_ver else None) or getattr(c, 'created_at', None)

            items.append({
                "id": c.id,
                "document_id": c.document_id,
                "chunk_index": idx,
                **({"content": content} if include_content else {}),
                "chunk_type": getattr(c, "chunk_type", "text"),
                "char_count": len(content or getattr(c, "content", "") or ""),
                "created_at": getattr(c, "created_at", None),
                "version": safe_version,
                "last_modified_at": modified_dt,
                "meta": meta_dict,  # ✅ 新增：返回 meta 字段，包含表格数据 table_data
            })
        return {"code": 0, "message": "ok", "data": {"list": items, "total": len(items), "page": page, "size": size}}
    except Exception as e:
        logger.error(f"获取文档分块失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取文档分块失败: {str(e)}")

@router.get("/{doc_id}/chunks/{chunk_id}")
async def get_document_chunk_detail(
    doc_id: int,
    chunk_id: int,
    db: Session = Depends(get_db)
):
    """获取单个分块详情（含内容）。当数据库未存文本时，从 MinIO 读取对应文本。"""
    try:
        from app.models.chunk import DocumentChunk
        chunk = db.query(DocumentChunk).filter(
            DocumentChunk.id == chunk_id,
            DocumentChunk.document_id == doc_id
        ).first()
        if not chunk:
            raise HTTPException(status_code=404, detail="分块不存在")

        # 读取内容：优先 DB；否则从 MinIO 归档映射定位
        content = chunk.content or ""
        if not content:
            try:
                created = getattr(chunk, 'created_at', None)
                doc = db.query(Document).filter(Document.id == doc_id).first()
                if doc:
                    created = getattr(doc, 'created_at', created) or datetime.datetime.utcnow()
                year = created.strftime('%Y')
                month = created.strftime('%m')
                object_name = f"documents/{year}/{month}/{doc_id}/parsed/chunks/chunks.jsonl.gz"
                minio = MinioStorageService()
                obj = minio.client.get_object(minio.bucket_name, object_name)
                import gzip, json
                try:
                    with gzip.GzipFile(fileobj=obj, mode='rb') as gz:
                        for line in gz:
                            try:
                                item = json.loads(line)
                                # 归档里使用的是 index（chunk_index），兼容旧字段 chunk_id
                                item_index = item.get("index")
                                if item_index is None:
                                    item_index = item.get("chunk_id")
                                if item_index is not None and int(item_index) == int(getattr(chunk, 'chunk_index', 0)):
                                    content = item.get("content", "")
                                    break
                            except Exception:
                                continue
                finally:
                    try:
                        obj.close(); obj.release_conn()
                    except Exception:
                        pass
            except Exception:
                content = ""

        # 解析 meta 字段（包含表格数据 table_data）
        import json
        meta_dict = None
        if chunk.meta:
            try:
                meta_dict = json.loads(chunk.meta) if isinstance(chunk.meta, str) else chunk.meta
            except (json.JSONDecodeError, TypeError):
                meta_dict = {}
        
        data = {
            "chunk_id": chunk.id,
            "document_id": chunk.document_id,
            "chunk_index": getattr(chunk, 'chunk_index', None),
            "chunk_type": getattr(chunk, 'chunk_type', 'text'),
            "content": content,
            "char_count": len(content or getattr(chunk, 'content', '') or ''),
            "version": getattr(chunk, 'version', 1),
            "created_at": getattr(chunk, 'created_at', None),
            "last_modified_at": getattr(chunk, 'last_modified_at', None),
            "meta": meta_dict,  # ✅ 新增：返回 meta 字段，包含表格数据 table_data
        }
        return {"code": 0, "message": "ok", "data": data}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取分块详情失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取分块详情失败: {str(e)}")

@router.get("/{doc_id}/images")
async def get_document_images(
    doc_id: int,
    db: Session = Depends(get_db)
):
    """获取指定文档的图片列表（兼容前端 /documents/{id}/images）"""
    try:
        service = ImageService(db)
        imgs = db.query(service.model).filter(service.model.document_id == doc_id, service.model.is_deleted == False).all()
        items = []
        minio = MinioStorageService()
        for im in imgs:
            # 为前端 <img> 生成可访问 URL（签名）
            url = None
            try:
                from datetime import timedelta
                url = minio.client.presigned_get_object(minio.bucket_name, im.image_path, expires=timedelta(hours=1))
            except Exception:
                url = f"/{im.image_path}"
            items.append({
                "id": im.id,
                "document_id": im.document_id,
                "image_path": im.image_path,
                "thumbnail_path": getattr(im, "thumbnail_path", None),
                "url": url,
                "width": getattr(im, "width", None),
                "height": getattr(im, "height", None),
                "description": getattr(im, "description", ""),
                "ocr_text": getattr(im, "ocr_text", ""),
                "created_at": getattr(im, "created_at", None),
            })
        return {"code": 0, "message": "ok", "data": items}
    except Exception as e:
        logger.error(f"获取文档图片失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取文档图片失败: {str(e)}")

@router.get("/{doc_id}/preview")
async def get_document_preview(
    doc_id: int,
    db: Session = Depends(get_db)
):
    """返回原始文档的直链；若为 Office 文档则自动生成 PDF 预览并返回其直链。"""
    try:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="文档不存在")
        if not doc.file_path:
            raise HTTPException(status_code=404, detail="缺少原始文件路径")

        minio = MinioStorageService()
        # 原始直链
        from datetime import timedelta
        original_url = minio.client.presigned_get_object(minio.bucket_name, doc.file_path, expires=timedelta(hours=1))

        # 推断类型
        content_type = "application/octet-stream"
        try:
            stat = minio.client.stat_object(minio.bucket_name, doc.file_path)
            if getattr(stat, 'content_type', None):
                content_type = stat.content_type
        except Exception:
            pass

        # 如果是 Office 文档，优先使用已转换的PDF（如果存在）
        ext = os.path.splitext(doc.file_path)[1].lower()
        is_office = ext in {".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"}
        
        # 如果已经有转换后的PDF URL，直接使用它
        if is_office and doc.converted_pdf_url:
            try:
                pdf_preview_url = minio.client.presigned_get_object(
                    minio.bucket_name, 
                    doc.converted_pdf_url, 
                    expires=timedelta(hours=1)
                )
                logger.info(f"使用已转换的PDF预览: {doc.converted_pdf_url}")
                return {
                    "code": 0, 
                    "message": "ok", 
                    "data": {
                        "preview_url": pdf_preview_url, 
                        "content_type": "application/pdf", 
                        "original_url": original_url,
                        "is_converted_pdf": True
                    }
                }
            except Exception as e:
                logger.warning(f"获取已转换PDF失败: {e}，尝试重新转换")
                # 如果获取失败，继续执行下面的转换逻辑
        
        if is_office:
            try:
                # 预览目标对象键
                created: datetime.datetime = getattr(doc, 'created_at', None) or datetime.datetime.utcnow()
                year = created.strftime('%Y')
                month = created.strftime('%m')
                preview_base = f"documents/{year}/{month}/{doc.id}/preview"
                preview_object = f"{preview_base}/preview.pdf"
                preview_object_screen = f"{preview_base}/preview_screen.pdf"

                # 若已存在，直接返回
                try:
                    stat_prev = minio.client.stat_object(minio.bucket_name, preview_object)
                    if stat_prev:
                        preview_url = minio.client.presigned_get_object(minio.bucket_name, preview_object, expires=timedelta(hours=1))
                        return {"code": 0, "message": "ok", "data": {"preview_url": preview_url, "content_type": "application/pdf", "original_url": original_url}}
                except Exception:
                    pass

                # 下载原件到临时目录
                obj = minio.client.get_object(minio.bucket_name, doc.file_path)
                data = obj.read(); obj.close(); obj.release_conn()
                with tempfile.TemporaryDirectory() as td:
                    src_path = os.path.join(td, f"origin{ext}")
                    with open(src_path, 'wb') as f:
                        f.write(data)
                    pdf_path = convert_docx_to_pdf(src_path)
                    if pdf_path and os.path.exists(pdf_path):
                        # 若 PDF 较大，尝试生成轻量版本
                        try:
                            size_bytes = os.path.getsize(pdf_path)
                        except Exception:
                            size_bytes = 0
                        threshold_mb = 10  # 10MB 阈值
                        use_screen = size_bytes > threshold_mb * 1024 * 1024

                        if use_screen:
                            screen_pdf = os.path.join(td, 'preview_screen.pdf')
                            if compress_pdf(pdf_path, screen_pdf, quality='screen') and os.path.exists(screen_pdf):
                                with open(screen_pdf, 'rb') as pf:
                                    minio.client.put_object(
                                        minio.bucket_name,
                                        preview_object_screen,
                                        data=pf,
                                        length=os.path.getsize(screen_pdf),
                                        content_type='application/pdf'
                                    )
                                # 写回数据库：记录转换后的PDF对象键
                                try:
                                    doc.converted_pdf_url = preview_object_screen
                                    db.commit()
                                except Exception:
                                    db.rollback()
                                preview_url = minio.client.presigned_get_object(minio.bucket_name, preview_object_screen, expires=timedelta(hours=1))
                                return {"code": 0, "message": "ok", "data": {"preview_url": preview_url, "content_type": "application/pdf", "original_url": original_url}}

                        # 上传 PDF 到 MinIO
                        with open(pdf_path, 'rb') as pf:
                            minio.client.put_object(
                                minio.bucket_name,
                                preview_object,
                                data=pf,
                                length=os.path.getsize(pdf_path),
                                content_type='application/pdf'
                            )
                        # 写回数据库：记录转换后的PDF对象键
                        try:
                            doc.converted_pdf_url = preview_object
                            db.commit()
                        except Exception:
                            db.rollback()
                        preview_url = minio.client.presigned_get_object(minio.bucket_name, preview_object, expires=timedelta(hours=1))
                        return {"code": 0, "message": "ok", "data": {"preview_url": preview_url, "content_type": "application/pdf", "original_url": original_url}}
            except Exception as conv_e:
                logger.warning(f"生成 Office 预览失败，将返回原件直链: {conv_e}")

        # 默认返回原始直链
        return {"code": 0, "message": "ok", "data": {"preview_url": original_url, "content_type": content_type, "original_url": original_url}}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取原文直链失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取原文直链失败: {str(e)}")

@router.get("/{doc_id}/chunks/{chunk_id}/content-opensearch")
async def get_chunk_content_from_opensearch(
    doc_id: int,
    chunk_id: int,
    source: str = Query("db", description="优先数据源: db 或 os"),
    db: Session = Depends(get_db)
):
    """优先从数据库读取块内容，必要时回退至 OpenSearch。"""
    try:
        from app.models.chunk import DocumentChunk

        def load_meta(raw_meta):
            if not raw_meta:
                return {}
            try:
                return json.loads(raw_meta) if isinstance(raw_meta, str) else raw_meta
            except (json.JSONDecodeError, TypeError):
                return {}

        def build_image_fields(meta_dict: dict):
            image_path = meta_dict.get('image_path')
            image_id = meta_dict.get('image_id')
            image_url = None
            if image_path:
                from datetime import timedelta
                minio = MinioStorageService()
                try:
                    image_url = minio.client.presigned_get_object(minio.bucket_name, image_path, expires=timedelta(hours=1))
                except Exception:
                    image_url = f"/{image_path}"
            return image_id, image_path, image_url

        def load_textual_content_from_archive(document_id: int, chunk_index: int) -> str:
            """当数据库未存储正文时，从 MinIO 归档中补齐文本/表格内容。"""
            if chunk_index is None:
                return ""
            try:
                doc = db.query(Document).filter(Document.id == document_id).first()
                if not doc:
                    return ""
                created = getattr(doc, "created_at", None) or datetime.datetime.utcnow()
                year = created.strftime("%Y")
                month = created.strftime("%m")
                object_name = f"documents/{year}/{month}/{document_id}/parsed/chunks/chunks.jsonl.gz"
                minio = MinioStorageService()
                obj = minio.client.get_object(minio.bucket_name, object_name)
                try:
                    with gzip.GzipFile(fileobj=obj, mode="rb") as gz:
                        for line in gz:
                            try:
                                data = json.loads(line.decode("utf-8"))
                            except Exception:
                                continue
                            idx = data.get("index")
                            if idx is None:
                                idx = data.get("chunk_index")
                            if idx is None:
                                continue
                            if int(idx) == int(chunk_index):
                                return data.get("content") or ""
                finally:
                    try:
                        obj.close()
                        obj.release_conn()
                    except Exception:
                        pass
            except Exception as archive_err:
                logger.debug(f"MinIO 归档读取 chunk_index={chunk_index} 失败: {archive_err}")
            return ""

        def build_payload(chunk_type: str, content_value: str, meta_dict: dict, extra: dict = None):
            payload = {
                "chunk_id": chunk_id,
                "chunk_type": chunk_type,
                "content": content_value,
                "char_count": len(content_value),
                "meta": meta_dict or {}
            }
            if extra:
                payload.update(extra)
            return {"code": 0, "message": "ok", "data": payload}

        # 1. 默认走数据库（也是唯一包含 MinIO 信息的权威源）
        if source.lower() != "os":
            chunk = db.query(DocumentChunk).filter(
                DocumentChunk.id == chunk_id,
                DocumentChunk.document_id == doc_id
            ).first()
            if chunk:
                meta_dict = load_meta(chunk.meta)
                chunk_type = (chunk.chunk_type or "text").lower()
                content = chunk.content or ""
                extra_fields = {
                    "chunk_index": getattr(chunk, 'chunk_index', None),
                    "document_id": chunk.document_id
                }

                if chunk_type == 'image':
                    image_id, image_path, image_url = build_image_fields(meta_dict)
                    if image_url:
                        content = image_url
                    extra_fields.update({
                        "image_id": image_id,
                        "image_path": image_path,
                        "image_url": image_url,
                    })
                else:
                    if not content:
                        archive_content = load_textual_content_from_archive(chunk.document_id, extra_fields["chunk_index"])
                        if archive_content:
                            content = archive_content

                return build_payload(chunk_type, content, meta_dict, extra_fields)

        # 2. 若显式要求读取 OpenSearch 或数据库缺失，再访问 OS
        osvc = OpenSearchService()
        source_doc = {}
        try:
            res = osvc.client.get(index=osvc.document_index, id=f"chunk_{chunk_id}")
            source_doc = res.get("_source", {}) if isinstance(res, dict) else {}
        except Exception as e:
            logger.debug(f"OpenSearch 未找到 chunk_{chunk_id}: {e}")
            source_doc = {}

        if source_doc and int(source_doc.get("document_id", 0)) == int(doc_id):
            chunk_type = (source_doc.get("chunk_type", "text") or "text").lower()
            metadata = source_doc.get("metadata") or {}
            content = source_doc.get("content", "") or ""
            extra_fields = {}
            chunk_index = None
            try:
                chunk_index = int(metadata.get("chunk_index", metadata.get("index")))
            except Exception:
                chunk_index = metadata.get("chunk_index") or metadata.get("index")
            if chunk_index is not None:
                extra_fields["chunk_index"] = chunk_index
                extra_fields["document_id"] = doc_id

            if chunk_type == "image":
                image_id, image_path, image_url = build_image_fields(metadata)
                if image_url:
                    content = image_url
                extra_fields.update({
                    "image_id": image_id,
                    "image_path": image_path,
                    "image_url": image_url,
                })
            else:
                if not content and chunk_index is not None:
                    archive_content = load_textual_content_from_archive(doc_id, chunk_index)
                    if archive_content:
                        content = archive_content
            return build_payload(chunk_type, content, metadata, extra_fields)

        return {"code": 1, "message": "未找到该块或文档不匹配", "data": None}
    except Exception as e:
        logger.error(f"读取OpenSearch块内容失败: {e}")
        return {"code": 1, "message": f"读取失败: {str(e)}"}

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
        return {
            "code": 0,
            "message": "ok",
            "data": {"document_id": doc_id, "deleted": True}
        }
        
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
            "code": 0,
            "message": "ok",
            "data": {
                "success_count": success_count,
                "fail_count": fail_count,
                "total": len(files),
                "results": results
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批量上传文档API错误: {e}", exc_info=True)
        return {"code": 1, "message": f"批量上传文档失败: {str(e)}"}

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
        return {"code": 0, "message": "ok"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重新处理文档API错误: {e}", exc_info=True)
        return {"code": 1, "message": f"重新处理文档失败: {str(e)}"}
