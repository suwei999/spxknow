"""
Document Upload Batch Model
"""

from sqlalchemy import Column, String, Text, Integer, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.models.base import BaseModel

class DocumentUploadBatch(BaseModel):
    """文档上传批次模型 - 根据批量上传设计实现"""
    __tablename__ = "document_upload_batches"
    
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, comment="用户ID（数据隔离）")
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_bases.id"), nullable=False, comment="知识库ID")
    total_files = Column(Integer, default=0, nullable=False, comment="总文件数")
    processed_files = Column(Integer, default=0, nullable=False, comment="已处理文件数")
    success_files = Column(Integer, default=0, nullable=False, comment="成功文件数")
    failed_files = Column(Integer, default=0, nullable=False, comment="失败文件数")
    status = Column(String(50), default="pending", nullable=False, comment="批次状态: pending/processing/completed/failed/completed_with_errors")
    error_summary = Column(Text, comment="错误摘要（JSON格式）")
    
    # 关系
    documents = relationship("Document", back_populates="batch")
    knowledge_base = relationship("KnowledgeBase")

