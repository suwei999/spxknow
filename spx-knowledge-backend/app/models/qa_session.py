"""
QA Session Model
根据知识问答系统设计文档实现问答会话模型
"""

from sqlalchemy import Column, String, Integer, DateTime, JSON, Text, Float, Boolean
from sqlalchemy.sql import func
from app.models.base import BaseModel


class QASession(BaseModel):
    """问答会话模型 - 根据设计文档实现"""
    
    __tablename__ = "qa_sessions"
    
    # 基础信息
    session_id = Column(String(100), unique=True, nullable=False, index=True, comment="会话ID")
    session_name = Column(String(200), comment="会话名称")
    knowledge_base_id = Column(Integer, nullable=False, index=True, comment="知识库ID")
    user_id = Column(Integer, index=True, comment="用户ID")
    
    # 配置信息
    query_method = Column(String(50), default="hybrid", comment="查询方式")
    search_config = Column(JSON, comment="搜索配置JSON")
    llm_config = Column(JSON, comment="LLM配置JSON")
    
    # 统计信息
    question_count = Column(Integer, default=0, comment="问题数量")
    last_question = Column(Text, comment="最后问题")
    last_activity_time = Column(DateTime, index=True, comment="最后活动时间")
    
    # 状态信息
    status = Column(String(20), default="active", comment="状态：active/inactive/deleted")
    
    def __repr__(self):
        return f"<QASession(session_id='{self.session_id}', name='{self.session_name}')>"

