"""
Image Service
"""

from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.image import DocumentImage
from app.services.minio_storage_service import MinioStorageService
from app.services.base import BaseService
from app.utils.image_utils import get_image_info as util_get_image_info
import os
import io
import hashlib
from PIL import Image

try:
    import pytesseract
except Exception:  # pragma: no cover
    pytesseract = None


class ImageService(BaseService[DocumentImage]):
    """图片服务（同步方法，适配 Celery 同步任务）"""
    
    def __init__(self, db: Session):
        super().__init__(db, DocumentImage)
    
    # =============== 基础工具 ===============
    def compute_sha256(self, file_path: str) -> str:
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def generate_thumbnail(self, src_path: str, max_size: int = 512) -> Optional[str]:
        try:
            thumb_dir = os.path.join(os.path.dirname(src_path), 'thumb')
            os.makedirs(thumb_dir, exist_ok=True)
            base = os.path.basename(src_path)
            name, ext = os.path.splitext(base)
            thumb_path = os.path.join(thumb_dir, f"{name}_thumb.jpg")
            with Image.open(src_path) as im:
                im = im.convert('RGB')
                im.thumbnail((max_size, max_size))
                im.save(thumb_path, format='JPEG', quality=85)
            return thumb_path
        except Exception:
            return None
    
    # =============== 信息/识别 ===============
    def get_image_info(self, image_path: str) -> Optional[dict]:
        return util_get_image_info(image_path)
    
    def extract_ocr_text(self, image_path: str) -> str:
        if not pytesseract:
            return ""
        try:
            with Image.open(image_path) as im:
                return pytesseract.image_to_string(im)
        except Exception:
            return ""
    
    # =============== 入口：保存并去重 ===============
    def create_image_from_bytes(self, document_id: int, data: bytes, image_ext: str = ".png", image_type: Optional[str] = None) -> DocumentImage:
        """从二进制创建图片：上传 MinIO，记录 MySQL，返回实体。"""
        sha = hashlib.sha256(data).hexdigest()
        existing = self.db.query(DocumentImage).filter(DocumentImage.sha256_hash == sha, DocumentImage.is_deleted == False).first()
        if existing:
            return existing
        # 上传原图至 MinIO
        minio = MinioStorageService()
        object_name = f"documents/{document_id}/images/{sha}{image_ext}"
        minio.upload_bytes(object_name, data, content_type="image/png")
        # 生成缩略图（内存）
        thumb_object = None
        width = None
        height = None
        try:
            from io import BytesIO
            with Image.open(BytesIO(data)) as im:
                width, height = im.size
                im = im.convert('RGB')
                im.thumbnail((256, 256))
                buf = BytesIO()
                im.save(buf, format='JPEG', quality=85)
                thumb_object = f"documents/{document_id}/images/thumb/{sha}_thumb.jpg"
                minio.upload_bytes(thumb_object, buf.getvalue(), content_type="image/jpeg")
        except Exception:
            pass
        # OCR（可选）
        ocr_text = ""
        try:
            from io import BytesIO
            with Image.open(BytesIO(data)) as im:
                if pytesseract:
                    ocr_text = pytesseract.image_to_string(im)
        except Exception:
            ocr_text = ""
        image = DocumentImage(
            document_id=document_id,
            image_path=object_name,
            thumbnail_path=thumb_object,
            image_type=image_type,
            file_size=len(data),
            width=width,
            height=height,
            sha256_hash=sha,
            ocr_text=ocr_text,
            status='completed'
        )
        self.db.add(image)
        self.db.commit()
        self.db.refresh(image)
        return image
    def create_or_get_image(self, document_id: int, image_path: str, image_type: Optional[str] = None) -> DocumentImage:
        sha = self.compute_sha256(image_path)
        # 去重：已存在则直接返回
        existing = self.db.query(DocumentImage).filter(DocumentImage.sha256_hash == sha, DocumentImage.is_deleted == False).first()
        if existing:
            return existing
        info = self.get_image_info(image_path) or {}
        thumb = self.generate_thumbnail(image_path)
        size = os.path.getsize(image_path) if os.path.exists(image_path) else None
        image_data = {
            "document_id": document_id,
            "image_path": image_path,
            "thumbnail_path": thumb,
            "image_type": image_type,
            "file_size": size,
            "width": info.get("width"),
            "height": info.get("height"),
            "sha256_hash": sha,
            "status": "extracted"
        }
        return self.create(image_data)  # BaseService 同步 create
    
    # =============== 处理流水（供任务调用） ===============
    def process_image_sync(self, image_id: int) -> bool:
        image = self.get(image_id)
        if not image:
            return False
        # 幂等：若已完成，直接返回
        if getattr(image, 'status', None) == 'completed':
            return True
        try:
            image.status = 'processing'
            self.db.commit()
            info = self.get_image_info(image.image_path) or {}
            if info:
                image.width = info.get('width')
                image.height = info.get('height')
            ocr = self.extract_ocr_text(image.image_path)
            if ocr:
                image.ocr_text = ocr
            image.status = 'completed'
            self.db.commit()
            return True
        except Exception as e:
            image.status = 'failed'
            image.error_message = str(e)
            self.db.commit()
            return False