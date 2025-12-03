"""
Document Image Model
"""

from sqlalchemy import Column, String, Text, Integer, DateTime, Boolean, ForeignKey, Float
from sqlalchemy.orm import relationship
from app.models.base import BaseModel

class DocumentImage(BaseModel):
    """文档图片模型"""
    __tablename__ = "document_images"
    
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, comment="文档ID")
    image_path = Column(String(500), nullable=False, comment="图片路径")
    thumbnail_path = Column(String(500), comment="缩略图路�?)
    image_type = Column(String(50), comment="图片类型")
    file_size = Column(Integer, comment="图片大小")
    width = Column(Integer, comment="图片宽度")
    height = Column(Integer, comment="图片高度")
    sha256_hash = Column(String(64), comment="图片哈希")
    ocr_text = Column(Text, comment="OCR识别文本")
    # SQLAlchemy 保留名冲突：列名 metadata、属性名 meta
    meta = Column('metadata', Text, comment="元数据JSON")
    vector_model = Column(String(50), comment="向量模型")
    vector_dim = Column(Integer, comment="向量维度")
    status = Column(String(50), default="pending", comment="处理状�?)
    retry_count = Column(Integer, default=0, comment="重试次数")
    last_processed_at = Column(DateTime, comment="最近处理时�?)
    error_message = Column(Text, comment="错误信息")
    
    # 关系
    document = relationship("Document", back_populates="images")
