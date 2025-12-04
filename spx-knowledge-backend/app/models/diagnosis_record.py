"""
Diagnosis Record Model
"""

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    JSON,
    DateTime,
    ForeignKey,
    Numeric,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.base import BaseModel


class DiagnosisRecord(BaseModel):
    """运维诊断记录"""

    __tablename__ = "diagnosis_records"

    cluster_id = Column(Integer, ForeignKey("cluster_configs.id"), nullable=False, comment="所属集群")
    namespace = Column(String(255), comment="命名空间")
    resource_type = Column(String(64), comment="资源类型")
    resource_name = Column(String(255), comment="资源名称")
    trigger_source = Column(String(32), default="manual", comment="触发来源")
    trigger_payload = Column(JSON, comment="触发上下文")
    symptoms = Column(JSON, comment="症状摘要")
    status = Column(String(32), default="pending", comment="诊断状态")
    summary = Column(Text, comment="概述")
    conclusion = Column(Text, comment="诊断结论")
    confidence = Column(Numeric(5, 2), comment="置信度(0-1)")
    metrics = Column(JSON, comment="关键指标数据")
    logs = Column(JSON, comment="关键日志片段")
    recommendations = Column(JSON, comment="建议措施或知识条目")
    events = Column(JSON, comment="诊断事件时间线")
    feedback = Column(JSON, comment="用户反馈")
    knowledge_refs = Column(JSON, comment="关联知识库条目")
    knowledge_source = Column(String(32), comment="知识来源")
    started_at = Column(DateTime(timezone=True), server_default=func.now(), comment="开始时间")
    completed_at = Column(DateTime(timezone=True), comment="完成时间")

    cluster = relationship("ClusterConfig", back_populates="diagnosis_records")
    iterations = relationship(
        "DiagnosisIteration",
        back_populates="diagnosis",
        cascade="all, delete-orphan",
        order_by="DiagnosisIteration.iteration_no",
    )
    memories = relationship(
        "DiagnosisMemory",
        back_populates="diagnosis",
        cascade="all, delete-orphan",
        order_by="DiagnosisMemory.created_at",
    )
