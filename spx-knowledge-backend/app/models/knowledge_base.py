"""
Knowledge Base Model
"""

from sqlalchemy import Column, String, Text, Integer, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.models.base import BaseModel

class KnowledgeBase(BaseModel):
    """知识库模型"""
    __tablename__ = "knowledge_bases"
    
    name = Column(String(255), nullable=False, comment="知识库名称")
    description = Column(Text, comment="知识库描述")
    category_id = Column(Integer, ForeignKey("knowledge_base_categories.id"), comment="分类ID")
    is_active = Column(Boolean, default=True, comment="是否激活")
    
    # 关系
    documents = relationship("Document", back_populates="knowledge_base")
    category = relationship("KnowledgeBaseCategory", back_populates="knowledge_bases")
