"""
Search History Model
搜索历史模型
"""

from sqlalchemy import Column, String, Integer, DateTime, Boolean, ForeignKey
from app.models.base import BaseModel


class SearchHistory(BaseModel):
    """搜索历史模型"""
    __tablename__ = "search_history"
    
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="用户ID")
    query_text = Column(String(500), nullable=False, comment="搜索关键词")
    search_type = Column(String(50), comment="搜索类型：vector/keyword/hybrid/exact")
    knowledge_base_id = Column(Integer, comment="知识库ID（可选）")
    result_count = Column(Integer, default=0, comment="结果数量")
    search_time_ms = Column(Integer, comment="搜索耗时（毫秒）")
    
    def __repr__(self):
        return f"<SearchHistory(id={self.id}, user_id={self.user_id}, query='{self.query_text[:50]}...')>"


class SearchHotword(BaseModel):
    """搜索热词模型"""
    __tablename__ = "search_hotwords"
    
    keyword = Column(String(200), nullable=False, unique=True, index=True, comment="关键词")
    search_count = Column(Integer, default=1, comment="搜索次数")
    last_searched_at = Column(DateTime, index=True, comment="最后搜索时间")
    
    def __repr__(self):
        return f"<SearchHotword(id={self.id}, keyword='{self.keyword}', count={self.search_count})>"
