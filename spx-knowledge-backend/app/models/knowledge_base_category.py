"""
Knowledge Base Category Model
"""

from sqlalchemy import Column, String, Text, Integer, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.models.base import BaseModel

class KnowledgeBaseCategory(BaseModel):
    """知识库分类模�?- 根据文档处理流程设计"""
    __tablename__ = "knowledge_base_categories"
    
    name = Column(String(255), nullable=False, comment="分类名称")
    description = Column(Text, comment="分类描述")
    parent_id = Column(Integer, ForeignKey("knowledge_base_categories.id"), comment="父分类ID")
    sort_order = Column(Integer, default=0, comment="排序")
    is_active = Column(Boolean, default=True, comment="是否激�?)
    
    # 根据设计文档添加的字�?
    level = Column(Integer, default=1, comment="分类层级")
    icon = Column(String(100), comment="分类图标")
    color = Column(String(20), comment="分类颜色")
    
    # 关系
    knowledge_bases = relationship("KnowledgeBase", back_populates="category")
    # 自关联：显式引用远端主键列，避免将内置函�?id 误用为列
    parent = relationship(
        "KnowledgeBaseCategory",
        remote_side="KnowledgeBaseCategory.id",
        back_populates="children",
    )
    children = relationship("KnowledgeBaseCategory", back_populates="parent")
