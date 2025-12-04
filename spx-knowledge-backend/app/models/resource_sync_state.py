"""
Resource sync state model.
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.sql import func

from app.models.base import BaseModel


class ResourceSyncState(BaseModel):
    """记录每个资源类型的最新 resourceVersion"""

    __tablename__ = "resource_sync_states"

    cluster_id = Column(Integer, ForeignKey("cluster_configs.id"), nullable=False, comment="集群ID")
    resource_type = Column(String(64), nullable=False, comment="资源类型")
    namespace = Column(String(255), comment="命名空间")
    resource_version = Column(String(64), comment="最新资源版本")
    # 注意：created_at, updated_at, is_deleted 字段由 BaseModel 提供
    # 但为了明确，这里显式覆盖 updated_at 以使用数据库的 ON UPDATE 功能
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="更新时间")
