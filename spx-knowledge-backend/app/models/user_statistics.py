"""
User Statistics Model
用户统计模型
"""

from sqlalchemy import Column, Integer, BigInteger, Date, String, ForeignKey
from app.models.base import BaseModel


class UserStatistics(BaseModel):
    """用户统计模型"""
    __tablename__ = "user_statistics"
    
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="用户ID")
    stat_date = Column(Date, nullable=False, index=True, comment="统计日期")
    stat_type = Column(String(50), nullable=False, comment="统计类型：daily/weekly/monthly")
    
    # 知识库统计
    knowledge_base_count = Column(Integer, default=0, comment="知识库数量")
    document_count = Column(Integer, default=0, comment="文档数量")
    total_file_size = Column(BigInteger, default=0, comment="总文件大小（字节）")
    
    # 使用统计
    search_count = Column(Integer, default=0, comment="搜索次数")
    qa_count = Column(Integer, default=0, comment="问答次数")
    upload_count = Column(Integer, default=0, comment="上传次数")
    
    # 存储统计
    storage_used = Column(BigInteger, default=0, comment="已用存储（字节）")
    storage_limit = Column(BigInteger, default=0, comment="存储限制（字节）")
    
    def __repr__(self):
        return f"<UserStatistics(id={self.id}, user_id={self.user_id}, stat_date={self.stat_date}, stat_type={self.stat_type})>"


class DocumentTypeStatistics(BaseModel):
    """文档类型统计模型"""
    __tablename__ = "document_type_statistics"
    
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="用户ID")
    file_type = Column(String(50), nullable=False, comment="文件类型")
    count = Column(Integer, default=0, comment="数量")
    total_size = Column(BigInteger, default=0, comment="总大小")
    stat_date = Column(Date, nullable=False, index=True, comment="统计日期")
    
    def __repr__(self):
        return f"<DocumentTypeStatistics(id={self.id}, user_id={self.user_id}, file_type={self.file_type}, count={self.count})>"

