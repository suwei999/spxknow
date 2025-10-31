"""
Document Chunk Model
"""

from sqlalchemy import Column, String, Text, Integer, DateTime, Boolean, ForeignKey, Float
from sqlalchemy.orm import relationship
from app.models.base import BaseModel

class DocumentChunk(BaseModel):
    """文档分块模型"""
    __tablename__ = "document_chunks"
    
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, comment="文档ID")
    content = Column(Text, nullable=True, comment="分块内容（可选存储，受配置控制）")
    chunk_index = Column(Integer, nullable=False, comment="分块索引")
    chunk_type = Column(String(50), default="text", comment="分块类型")
    # SQLAlchemy 保留名冲突：列名 metadata、属性名 meta
    meta = Column('metadata', Text, comment="元数据JSON")
    # 版本管理字段 - 根据文档修改功能设计添加
    version = Column(Integer, default=1, comment="版本号")
    chunk_version_id = Column(Integer, ForeignKey("chunk_versions.id"), nullable=True, comment="当前块版本ID")
    last_modified_at = Column(DateTime, comment="最后修改时间")
    modification_count = Column(Integer, default=0, comment="修改次数")
    last_modified_by = Column(String(100), comment="最后修改者")
    
    # 关系
    document = relationship("Document", back_populates="chunks")
    versions = relationship(
        "ChunkVersion",
        back_populates="chunk",
        primaryjoin="ChunkVersion.chunk_id==DocumentChunk.id",
        foreign_keys="ChunkVersion.chunk_id",
    )
    current_version = relationship(
        "ChunkVersion",
        primaryjoin="ChunkVersion.id==DocumentChunk.chunk_version_id",
        foreign_keys="DocumentChunk.chunk_version_id",
        uselist=False,
    )
