"""
Document Version Model
"""

from sqlalchemy import Column, String, Text, Integer, DateTime, Boolean, ForeignKey, Float
from sqlalchemy.orm import relationship
from app.models.base import BaseModel

class DocumentVersion(BaseModel):
    """文档版本模型"""
    __tablename__ = "document_versions"
    
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, comment="文档ID")
    version_number = Column(Integer, nullable=False, comment="版本号")
    version_type = Column(String(50), default="auto", comment="版本类型")
    description = Column(Text, comment="版本描述")
    file_path = Column(String(500), nullable=False, comment="文件路径")
    file_size = Column(Integer, comment="文件大小")
    file_hash = Column(String(64), comment="文件哈希")
    
    # 关系
    document = relationship("Document", back_populates="versions")
