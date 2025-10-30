"""
Image Processing Tasks
"""

from celery import current_task
from app.tasks.celery_app import celery_app
from app.services.image_service import ImageService
from app.services.vector_service import VectorService
from app.services.unstructured_service import UnstructuredService
from app.models.image import DocumentImage
from app.models.document import Document
from sqlalchemy.orm import Session
from app.config.database import SessionLocal

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

@celery_app.task
def extract_images_from_document_task(document_id: int):
    """从文档中提取图片任务"""
    db = SessionLocal()
    try:
        # 获取文档
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            return {"status": "error", "message": "文档不存在"}
        
        # 使用Unstructured提取图片（同步调用）
        unstructured_service = UnstructuredService(db)
        images = unstructured_service.extract_images(document.file_path)
        
        # 创建图片记录
        for i, image_data in enumerate(images):
            image = DocumentImage(
                document_id=document_id,
                image_path=image_data.get("path", ""),
                image_type=image_data.get("type", "unknown"),
                metadata=image_data.get("metadata", {})
            )
            db.add(image)
        
        db.commit()
        
        # 启动图片处理任务
        new_images = db.query(DocumentImage).filter(DocumentImage.document_id == document_id).all()
        image_ids = [img.id for img in new_images]
        
        return batch_process_images_task.delay(image_ids)
        
    except Exception as e:
        db.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        db.close()
