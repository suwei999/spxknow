"""
Cluster Configuration Model
"""

from sqlalchemy import (
    Column,
    String,
    Text,
    Boolean,
    DateTime,
)
from sqlalchemy.orm import relationship
from app.models.base import BaseModel


class ClusterConfig(BaseModel):
    """集群接入配置"""

    __tablename__ = "cluster_configs"

    name = Column(String(128), nullable=False, unique=True, comment="集群名称")
    description = Column(Text, comment="描述")
    api_server = Column(String(255), nullable=False, comment="Kubernetes API Server 地址")
    auth_type = Column(String(32), nullable=False, default="token", comment="认证方式: token|kubeconfig|basic")
    auth_token = Column(Text, comment="Bearer Token")
    kubeconfig = Column(Text, comment="kubeconfig 内容（建议加密）")
    client_cert = Column(Text, comment="客户端证书（PEM）")
    client_key = Column(Text, comment="客户端私钥（PEM）")
    ca_cert = Column(Text, comment="CA 证书（PEM）")
    verify_ssl = Column(Boolean, default=True, comment="是否校验证书")
    prometheus_url = Column(String(255), comment="Prometheus 地址")
    prometheus_auth_type = Column(String(32), default="none", comment="Prometheus 认证方式")
    prometheus_username = Column(String(128), comment="Prometheus 用户名")
    prometheus_password = Column(Text, comment="Prometheus 密码/Token")
    log_system = Column(String(64), comment="日志系统类型: elk|loki|custom")
    log_endpoint = Column(String(255), comment="日志系统入口地址")
    log_auth_type = Column(String(32), default="none", comment="日志系统认证方式")
    log_username = Column(String(128), comment="日志系统用户名")
    log_password = Column(Text, comment="日志系统密码/Token")
    is_active = Column(Boolean, default=True, comment="是否启用")
    last_health_status = Column(String(32), default="unknown", comment="最近一次健康检查状态")
    last_health_message = Column(Text, comment="健康检查结果描述")
    last_health_checked_at = Column(DateTime(timezone=True), comment="最近一次健康检查时间")
    credential_ref = Column(String(255), comment="外部凭证引用")

    resource_snapshots = relationship(
        "ResourceSnapshot",
        back_populates="cluster",
        cascade="all, delete-orphan",
    )
    diagnosis_records = relationship(
        "DiagnosisRecord",
        back_populates="cluster",
        cascade="all, delete-orphan",
    )

