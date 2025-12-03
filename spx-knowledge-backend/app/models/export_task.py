"""
Export Task Model
导出任务模型
"""

from sqlalchemy import Column, String, Integer, BigInteger, DateTime, Text, ForeignKey
from app.models.base import BaseModel


class ExportTask(BaseModel):
    """导出任务模型"""
    __tablename__ = "export_tasks"
    
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="用户ID")
    export_type = Column(String(50), nullable=False, comment="导出类型：knowledge_base/document/qa_history")
    target_id = Column(Integer, comment="目标ID（知识库ID/文档ID）")
    export_format = Column(String(50), nullable=False, comment="导出格式：markdown/pdf/json")
    status = Column(String(50), default="pending", index=True, comment="状态：pending/processing/completed/failed")
    file_path = Column(String(500), comment="导出文件路径")
    file_size = Column(BigInteger, comment="文件大小")
    error_message = Column(Text, comment="错误信息")
    completed_at = Column(DateTime, comment="完成时间")
    
    def __repr__(self):
        return f"<ExportTask(id={self.id}, user_id={self.user_id}, export_type={self.export_type}, status={self.status})>"

