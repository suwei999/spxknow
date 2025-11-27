"""
Image Service
"""

from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.models.image import DocumentImage
from app.services.minio_storage_service import MinioStorageService
from app.services.base import BaseService
from app.utils.image_utils import get_image_info as util_get_image_info
import os
import io
import hashlib
import mimetypes
from PIL import Image
from app.core.logging import logger

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
    
    def _normalize_ext(self, image_ext: Optional[str]) -> str:
        ext = (image_ext or ".png").lower()
        if not ext.startswith("."):
            ext = f".{ext}"
        return ext
    
    def _infer_image_type(self, image_ext: str, explicit_type: Optional[str] = None, info_format: Optional[str] = None) -> str:
        candidates = [
            explicit_type,
            image_ext.lstrip(".") if image_ext else None,
            info_format.lower() if info_format else None,
        ]
        for candidate in candidates:
            if candidate:
                return candidate.replace(".", "").lower()
        return "unknown"
    
    def ensure_image_type_from_storage(self, image: DocumentImage, minio: Optional[MinioStorageService] = None) -> Optional[str]:
        """确保图片类型存在；如缺失则根据路径或 MinIO 内容推断并回写数据库。"""
        current = (getattr(image, "image_type", None) or "").strip().lower()
        if current and current != "unknown":
            return current
        
        path = getattr(image, "image_path", "") or ""
        inferred = None
        if path:
            ext = os.path.splitext(path)[1]
            if ext:
                inferred = self._infer_image_type(self._normalize_ext(ext))
        
        if (not inferred or inferred == "unknown") and path:
            storage = minio or MinioStorageService()
            try:
                obj = storage.client.get_object(storage.bucket_name, path)
                data = obj.read()
                obj.close()
                obj.release_conn()
                with Image.open(io.BytesIO(data)) as im:
                    fmt = (im.format or "").lower()
                    if fmt:
                        inferred = fmt
            except Exception as exc:
                logger.warning(f"无法从 MinIO 推断图片类型: image_id={image.id}, path={path}, error={exc}")
        
        if inferred:
            image.image_type = inferred
            self.db.commit()
            return inferred
        return None
    
    def backfill_missing_image_types(self, batch_size: int = 200) -> int:
        """回填缺失的 image_type 字段"""
        query = self.db.query(DocumentImage).filter(
            DocumentImage.is_deleted == False,
            or_(
                DocumentImage.image_type == None,  # noqa: E711
                DocumentImage.image_type == "",
                DocumentImage.image_type == "unknown"
            )
        )
        total = query.count()
        if total == 0:
            logger.info("没有需要回填的图片类型记录")
            return 0
        
        logger.info(f"开始回填 image_type, 待处理: {total} 条")
        updated = 0
        minio = MinioStorageService()
        for image in query.yield_per(batch_size):
            inferred = self.ensure_image_type_from_storage(image, minio=minio)
            if inferred:
                updated += 1
        logger.info(f"回填图片类型完成，更新 {updated}/{total} 条记录")
        return updated
    
    # =============== 入口：保存并去重 ===============
    def create_image_from_bytes(self, document_id: int, data: bytes, image_ext: str = ".png", image_type: Optional[str] = None) -> DocumentImage:
        """从二进制创建图片：上传 MinIO，记录 MySQL，返回实体。"""
        sha = hashlib.sha256(data).hexdigest()
        norm_ext = self._normalize_ext(image_ext)
        inferred_type = self._infer_image_type(norm_ext, explicit_type=image_type)
        existing = self.db.query(DocumentImage).filter(DocumentImage.sha256_hash == sha, DocumentImage.is_deleted == False).first()
        if existing:
            if not existing.image_type and inferred_type != "unknown":
                existing.image_type = inferred_type
                self.db.commit()
            return existing
        # 上传原图至 MinIO
        minio = MinioStorageService()
        object_name = f"documents/{document_id}/images/{sha}{norm_ext}"
        content_type = mimetypes.types_map.get(norm_ext, f"image/{inferred_type}" if inferred_type != "unknown" else "application/octet-stream")
        minio.upload_bytes(object_name, data, content_type=content_type)
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
            image_type=inferred_type,
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
        _, ext = os.path.splitext(image_path)
        norm_ext = self._normalize_ext(ext if ext else ".png")
        info = self.get_image_info(image_path) or {}
        inferred_type = self._infer_image_type(norm_ext, explicit_type=image_type, info_format=info.get("format"))
        # 去重：已存在则直接返回
        existing = self.db.query(DocumentImage).filter(DocumentImage.sha256_hash == sha, DocumentImage.is_deleted == False).first()
        if existing:
            if not existing.image_type and inferred_type != "unknown":
                existing.image_type = inferred_type
                self.db.commit()
            return existing
        thumb = self.generate_thumbnail(image_path)
        size = os.path.getsize(image_path) if os.path.exists(image_path) else None
        image_data = {
            "document_id": document_id,
            "image_path": image_path,
            "thumbnail_path": thumb,
            "image_type": inferred_type,
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

    # =============== API 适配：异步包装 ===============
    async def get_images(self, skip: int = 0, limit: int = 24, document_id: Optional[int] = None) -> List[DocumentImage]:
        """获取图片列表（支持按文档过滤，分页）。
        为兼容路由中的 await，这里声明为 async，但内部为同步 ORM 调用。
        """
        query = self.db.query(DocumentImage).filter(DocumentImage.is_deleted == False)
        if document_id is not None:
            query = query.filter(DocumentImage.document_id == document_id)
        # 按创建时间倒序（BaseModel 通常含 created_at）
        try:
            from app.models.base import BaseModel as _BaseModel  # 仅用于类型上的 created_at 引用
            created_col = getattr(DocumentImage, 'created_at', None)
        except Exception:
            created_col = None
        if created_col is not None:
            query = query.order_by(created_col.desc())
        else:
            query = query.order_by(DocumentImage.id.desc())
        return query.offset(skip).limit(limit).all()

    async def get_image(self, image_id: int) -> Optional[DocumentImage]:
        """获取单张图片详情（异步包装）。"""
        return self.db.query(DocumentImage).filter(DocumentImage.id == image_id, DocumentImage.is_deleted == False).first()

    async def upload_image(self, file, document_id: int) -> DocumentImage:
        """上传图片文件并入库（支持 FastAPI UploadFile）。"""
        # 读取文件二进制
        if hasattr(file, 'read'):
            # UploadFile: 需要 await
            try:
                data = await file.read()  # type: ignore
            except TypeError:
                # 同步 file-like
                data = file.read()
        else:
            raise ValueError("无效的文件对象")

        # 推断扩展名
        filename = getattr(file, 'filename', None) or 'upload.png'
        _, ext = os.path.splitext(filename)
        ext = ext.lower() if ext else '.png'
        if ext not in ['.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp']:
            ext = '.png'

        image_type = ext.lstrip('.')

        return self.create_image_from_bytes(document_id=document_id, data=data, image_ext=ext, image_type=image_type)