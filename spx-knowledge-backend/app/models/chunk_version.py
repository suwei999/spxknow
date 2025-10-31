"""
Chunk Version Model
根据文档修改功能设计实现块版本管理
"""

from sqlalchemy import Column, String, Text, Integer, DateTime, Boolean, ForeignKey, Float
from sqlalchemy.orm import relationship
from app.models.base import BaseModel

class ChunkVersion(BaseModel):
    """块版本模型 - 根据文档修改功能设计实现"""
    __tablename__ = "chunk_versions"
    
    chunk_id = Column(Integer, ForeignKey("document_chunks.id"), nullable=False, comment="块ID")
    version_number = Column(Integer, nullable=False, comment="版本号（递增）")
    content = Column(Text, nullable=False, comment="版本内容")
    # SQLAlchemy 保留名冲突：列名 metadata、属性名 meta
    meta = Column('metadata', Text, comment="版本元数据")
    modified_by = Column(String(100), comment="修改者")
    version_comment = Column(Text, comment="版本注释")
    created_at = Column(DateTime, nullable=False, comment="创建时间")
    
    # 关系（指定外键，避免与 DocumentChunk.chunk_version_id 产生歧义）
    chunk = relationship(
        "DocumentChunk",
        back_populates="versions",
        primaryjoin="ChunkVersion.chunk_id==DocumentChunk.id",
        foreign_keys="ChunkVersion.chunk_id",
    )
    
    # 索引优化 - 根据设计文档要求
    __table_args__ = (
        # 复合索引：优化版本查询
        {'extend_existing': True}
    )
