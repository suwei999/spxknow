"""QA External Search Record Model"""

from sqlalchemy import Column, String, Text, Float, Boolean, JSON

from app.models.base import BaseModel


class QAExternalSearchRecord(BaseModel):
    """存储外部搜索的摘要与结果"""

    __tablename__ = "qa_external_searches"

    question = Column(Text, nullable=False, comment="用户原始问题")
    search_query = Column(Text, nullable=True, comment="发送到SearxNG的查询语句")
    session_id = Column(String(100), nullable=True, comment="会话ID")
    user_id = Column(String(100), nullable=True, comment="用户ID")
    summary = Column(Text, nullable=True, comment="模型生成的总结")
    results = Column(JSON, nullable=True, comment="外部搜索结果JSON")
    trigger_metadata = Column(JSON, nullable=True, comment="触发元数据")
    from_cache = Column(Boolean, default=False, comment="是否命中缓存")
    latency = Column(Float, nullable=True, comment="耗时（秒）")

    def __repr__(self) -> str:
        return f"<QAExternalSearchRecord(id={self.id}, session_id={self.session_id})>"

