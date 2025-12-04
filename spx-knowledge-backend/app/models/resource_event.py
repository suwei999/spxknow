"""
Resource change event model.
"""

from sqlalchemy import Column, Integer, String, JSON, DateTime, ForeignKey
from sqlalchemy.sql import func

from app.models.base import BaseModel


class ResourceEvent(BaseModel):
    """记录资源级别变更事件"""

    __tablename__ = "resource_events"

    cluster_id = Column(Integer, ForeignKey("cluster_configs.id"), nullable=False, comment="集群ID")
    resource_type = Column(String(64), nullable=False, comment="资源类型")
    namespace = Column(String(255), comment="命名空间")
    resource_uid = Column(String(128), nullable=False, comment="资源UID")
    event_type = Column(String(32), nullable=False, comment="事件类型")
    diff = Column(JSON, comment="变更摘要")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="事件时间")
