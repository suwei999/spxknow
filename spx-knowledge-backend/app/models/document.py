"""
Document Model
"""

from sqlalchemy import Column, String, Text, Integer, DateTime, Boolean, ForeignKey, Float, JSON
from sqlalchemy.orm import relationship
from app.models.base import BaseModel

class Document(BaseModel):
    """文档模型 - 根据文档处理流程设计"""
    __tablename__ = "documents"
    
    original_filename = Column(String(255), nullable=False, comment="原始文件名")
    file_type = Column(String(50), comment="文件类型")
    file_size = Column(Integer, comment="文件大小")
    file_hash = Column(String(64), comment="文件哈希")
    file_path = Column(String(500), comment="文件路径")
    converted_pdf_url = Column(String(500), comment="转换后的PDF文件路径（MinIO对象键），用于预览")
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_bases.id"), nullable=False, comment="知识库ID")
    batch_id = Column(Integer, ForeignKey("document_upload_batches.id"), nullable=True, comment="批次ID")
    category_id = Column(Integer, ForeignKey("knowledge_base_categories.id"), comment="分类ID")
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, comment="用户ID（数据隔离）")
    tags = Column(JSON, comment="标签列表JSON")
    # SQLAlchemy Declarative 保留名冲突，使用列名 metadata、属性名 meta
    meta = Column('metadata', JSON, comment="元数据JSON")
    status = Column(String(50), default="uploaded", comment="处理状态")
    processing_progress = Column(Float, default=0.0, comment="处理进度")
    error_message = Column(Text, comment="错误信息")
    retry_count = Column(Integer, default=0, comment="重试次数")
    # 安全扫描字段
    security_scan_status = Column(String(50), default="pending", comment="安全扫描状态: pending(待扫描), scanning(扫描中), safe(安全), infected(感染), error(错误), skipped(跳过)")
    security_scan_method = Column(String(50), comment="扫描方法: clamav, pattern_only, none")
    security_scan_result = Column(JSON, comment="安全扫描结果JSON")
    security_scan_timestamp = Column(DateTime, comment="安全扫描时间")
    # 版本管理字段 - 根据文档修改功能设计添加
    last_modified_at = Column(DateTime, comment="最后修改时间")
    modification_count = Column(Integer, default=0, comment="修改次数")
    last_modified_by = Column(String(100), comment="最后修改者")
    
    # 关系
    knowledge_base = relationship("KnowledgeBase", back_populates="documents")
    batch = relationship("DocumentUploadBatch", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document")
    versions = relationship("DocumentVersion", back_populates="document")
    images = relationship("DocumentImage", back_populates="document")
