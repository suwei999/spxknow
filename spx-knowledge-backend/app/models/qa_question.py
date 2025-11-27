"""
QA Question Model
根据知识问答系统设计文档实现问答记录模型
"""

from sqlalchemy import Column, String, Integer, DateTime, JSON, Text, Float, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.models.base import BaseModel


class QAQuestion(BaseModel):
    """问答记录模型 - 根据设计文档实现"""
    
    __tablename__ = "qa_questions"
    
    # 基础信息
    question_id = Column(String(100), unique=True, nullable=False, index=True, comment="问题ID")
    session_id = Column(String(100), ForeignKey("qa_sessions.session_id"), nullable=False, index=True, comment="会话ID")
    question_content = Column(Text, nullable=True, comment="问题内容摘要（完整内容存储在OpenSearch）")
    
    # 答案信息
    answer_content = Column(Text, nullable=True, comment="答案内容摘要（完整内容存储在OpenSearch）")
    source_info = Column(JSON, comment="来源信息JSON")
    processing_info = Column(JSON, comment="处理信息JSON")
    
    # 质量评估
    similarity_score = Column(Float, comment="相似度分数")
    answer_quality = Column(String(20), comment="答案质量")
    user_feedback = Column(JSON, comment="用户反馈JSON")
    
    # 输入类型
    input_type = Column(String(50), default="text", comment="输入类型：text/image/multimodal")
    
    # 处理时间
    processing_time = Column(Float, comment="处理时间（秒）")
    token_usage = Column(Integer, comment="Token使用量")
    
    def __repr__(self):
        return f"<QAQuestion(question_id='{self.question_id}', session_id='{self.session_id}')>"


class QAStatistics(BaseModel):
    """问答统计模型 - 根据设计文档实现"""
    
    __tablename__ = "qa_statistics"
    
    # 基础信息
    knowledge_base_id = Column(Integer, nullable=False, index=True, comment="知识库ID")
    date = Column(DateTime, nullable=False, index=True, comment="统计日期")
    
    # 统计信息
    total_questions = Column(Integer, default=0, comment="总问题数")
    answered_questions = Column(Integer, default=0, comment="已回答数")
    unanswered_questions = Column(Integer, default=0, comment="未回答数")
    
    # 性能指标
    avg_similarity_score = Column(Float, comment="平均相似度分数")
    avg_response_time = Column(Float, comment="平均响应时间")
    
    # 分析数据
    hot_questions = Column(JSON, comment="热门问题JSON")
    query_method_stats = Column(JSON, comment="查询方式统计JSON")
    
    # 唯一性约束
    __table_args__ = (
        {'comment': '问答统计数据'},
    )
    
    def __repr__(self):
        return f"<QAStatistics(knowledge_base_id={self.knowledge_base_id}, date='{self.date}')>"

