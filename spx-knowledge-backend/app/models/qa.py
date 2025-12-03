"""
QA Question Model
"""

from sqlalchemy import Column, String, Text, Integer, DateTime, Boolean, ForeignKey, Float
from sqlalchemy.orm import relationship
from app.models.base import BaseModel

class QAQuestion(BaseModel):
    """问答问题模型"""
    __tablename__ = "qa_questions"
    
    question = Column(Text, nullable=False, comment="问题")
    answer = Column(Text, nullable=False, comment="答案")
    knowledge_base_id = Column(Integer, ForeignKey("knowledge_bases.id"), nullable=False, comment="知识库ID")
    session_id = Column(String(100), comment="会话ID")
    query_method = Column(String(50), default="hybrid", comment="查询方法")
    confidence = Column(Float, comment="置信度")
    references = Column(Text, comment="参考文献JSON")
    
    # 关系
    knowledge_base = relationship("KnowledgeBase", back_populates="qa_questions")
