"""
Document TOC Model
文档目录模型
"""

from sqlalchemy import Column, String, Integer, ForeignKey
from app.models.base import BaseModel


class DocumentTOC(BaseModel):
    """文档目录模型"""
    __tablename__ = "document_toc"
    
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True, comment="文档ID")
    level = Column(Integer, nullable=False, comment="目录级别（1-6）")
    title = Column(String(500), nullable=False, comment="标题")
    page_number = Column(Integer, comment="页码")
    position = Column(Integer, comment="位置（用于排序）")
    parent_id = Column(Integer, ForeignKey("document_toc.id", ondelete="CASCADE"), comment="父级目录ID")
    element_index = Column(Integer, comment="元素索引（在文档中的位置）")
    paragraph_index = Column(Integer, comment="段落索引（Word文档）")
    start_chunk_id = Column(Integer, ForeignKey("document_chunks.id", ondelete="SET NULL"), comment="起始分块ID（该目录项对应的第一个分块）")
    
    def __repr__(self):
        return f"<DocumentTOC(id={self.id}, document_id={self.document_id}, level={self.level}, title='{self.title[:30]}...')>"
