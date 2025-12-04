"""
Task Model
"""

from sqlalchemy import Column, String, Text, Integer, DateTime, Boolean, ForeignKey, Float
from sqlalchemy.orm import relationship
from app.models.base import BaseModel

class CeleryTask(BaseModel):
    """Celery任务模型"""
    __tablename__ = "celery_tasks"
    
    task_id = Column(String(100), nullable=False, unique=True, comment="任务ID")
    task_name = Column(String(100), nullable=False, comment="任务名称")
    status = Column(String(50), default="pending", comment="任务状态")
    progress = Column(Float, default=0.0, comment="任务进度")
    result = Column(Text, comment="任务结果")
    error_message = Column(Text, comment="错误信息")
    started_at = Column(DateTime, comment="开始时间")
    completed_at = Column(DateTime, comment="完成时间")
    
    # 关系
    # 可以根据需要添加关系
