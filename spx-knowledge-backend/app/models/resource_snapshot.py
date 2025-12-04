"""
Resource Snapshot Model
"""

from sqlalchemy import Column, Integer, String, JSON, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.base import BaseModel


class ResourceSnapshot(BaseModel):
    """Kubernetes 资源快照"""

    __tablename__ = "resource_snapshots"

    cluster_id = Column(Integer, ForeignKey("cluster_configs.id"), nullable=False, comment="所属集群")
    resource_uid = Column(String(128), nullable=False, comment="资源UID")
    resource_type = Column(String(64), nullable=False, comment="资源类型")
    namespace = Column(String(255), comment="命名空间")
    resource_name = Column(String(255), nullable=False, comment="资源名称")
    labels = Column(JSON, comment="资源标签")
    annotations = Column(JSON, comment="资源注解")
    spec = Column(JSON, comment="资源规格")
    status = Column(JSON, comment="资源状态")
    resource_version = Column(String(64), comment="资源版本号")
    snapshot = Column(JSON, nullable=False, comment="资源快照数据")
    collected_at = Column(DateTime(timezone=True), server_default=func.now(), comment="采集时间")

    cluster = relationship("ClusterConfig", back_populates="resource_snapshots")
