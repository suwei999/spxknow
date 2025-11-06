"""
Image Processing Tasks
"""

from celery import current_task
from app.tasks.celery_app import celery_app
from app.services.image_service import ImageService
from app.services.vector_service import VectorService
from app.models.image import DocumentImage
from app.models.document import Document
from sqlalchemy.orm import Session
from app.config.database import SessionLocal
from typing import List, Dict
from app.core.logging import logger
from app.services.docx_service import DocxService
import os


@celery_app.task(bind=True)
def process_image_task(self, image_id: int):
    """处理图片任务"""
    db = SessionLocal()
    try:
        # 获取图片
        image = db.query(DocumentImage).filter(DocumentImage.id == image_id).first()
        if not image:
            raise Exception(f"图片 {image_id} 不存在")
        
        # 更新任务状态
        current_task.update_state(
            state="PROGRESS",
            meta={"current": 0, "total": 100, "status": "开始处理图片"}
        )
        
        # 图片处理
        image_service = ImageService(db)
        
        # 获取图片信息
        image_info = image_service.get_image_info(image.image_path)
        if image_info:
            image.width = image_info.get("width")
            image.height = image_info.get("height")
            db.commit()
        
        current_task.update_state(
            state="PROGRESS",
            meta={"current": 30, "total": 100, "status": "图片信息提取完成"}
        )
        
        # OCR识别（同步调用）
        ocr_text = image_service.extract_ocr_text(image.image_path)
        if ocr_text:
            image.ocr_text = ocr_text
            db.commit()
        
        current_task.update_state(
            state="PROGRESS",
            meta={"current": 60, "total": 100, "status": "OCR识别完成"}
        )
        
        # 生成图片向量（同步调用）
        vector_service = VectorService(db)
        image_vector = vector_service.generate_image_embedding(image.image_path)
        
        # 这里应该将图片向量存储到OpenSearch
        # 暂时跳过具体实现
        
        current_task.update_state(
            state="PROGRESS",
            meta={"current": 90, "total": 100, "status": "图片向量化完成"}
        )
        
        # 更新图片状态
        image.status = "completed"
        db.commit()
        
        current_task.update_state(
            state="SUCCESS",
            meta={"current": 100, "total": 100, "status": "图片处理完成"}
        )
        
        return {"status": "success", "message": "图片处理完成"}
        
    except Exception as e:
        # 更新图片状态为失败
        if image:
            image.status = "failed"
            image.error_message = str(e)
            db.commit()
        
        current_task.update_state(
            state="FAILURE",
            meta={"error": str(e)}
        )
        raise e
    finally:
        db.close()

@celery_app.task
def batch_process_images_task(image_ids: list):
    """批量处理图片任务"""
    for image_id in image_ids:
        process_image_task.delay(image_id)
    
    return {"status": "success", "message": f"已启动 {len(image_ids)} 个图片处理任务"}


def extract_images_from_document_task(document_id: int) -> List[Dict]:
    """
    仅 DOCX：使用 DocxService 提取图片。
    注意：若传入的文件不是 DOCX，将抛出异常。
    """
    db = SessionLocal()
    try:
        from app.models.document import Document
        from app.services.minio_storage_service import MinioStorageService

        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise Exception(f"文档 {document_id} 不存在")
        is_docx = (str(doc.file_type or '').lower() == 'docx' or doc.original_filename.lower().endswith('.docx'))
        if not is_docx:
            raise Exception("extract_images_from_document_task 仅支持 DOCX")

        # 下载到临时文件
        minio = MinioStorageService()
        content = minio.download_file(doc.file_path)
        import tempfile
        tmpdir = tempfile.mkdtemp()
        path = os.path.join(tmpdir, f"{document_id}.docx")
        with open(path, 'wb') as f:
            f.write(content)

        parser = DocxService(db)
        parse_result = parser.parse_document(path)
        images = parse_result.get('images', []) or []
        logger.info(f"DOCX 图片提取完成: {len(images)} 张")
        return images
    except Exception as e:
        logger.error(f"图片提取失败: {e}")
        return []
    finally:
        try:
            db.close()
        except Exception:
            pass
