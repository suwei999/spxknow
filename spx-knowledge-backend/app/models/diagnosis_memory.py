"""Diagnosis memory model."""

from sqlalchemy import Column, Integer, String, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class DiagnosisMemory(BaseModel):
    """诊断上下文记忆 / 知识沉淀。"""

    __tablename__ = "diagnosis_memories"

    diagnosis_id = Column(Integer, ForeignKey("diagnosis_records.id"), nullable=False, comment="所属诊断记录")
    iteration_id = Column(Integer, ForeignKey("diagnosis_iterations.id"), nullable=True, comment="关联迭代ID")
    iteration_no = Column(Integer, nullable=True, comment="迭代序号")
    memory_type = Column(String(32), nullable=False, comment="记忆类型")
    summary = Column(Text, nullable=True, comment="记忆摘要")
    content = Column(JSON, nullable=True, comment="记忆详细内容")
    meta = Column("metadata", JSON, nullable=True, comment="附加信息")

    diagnosis = relationship("DiagnosisRecord", back_populates="memories")
    iteration = relationship("DiagnosisIteration", back_populates="memories")

    def __repr__(self) -> str:
        return f"<DiagnosisMemory id={self.id} diagnosis_id={self.diagnosis_id} type={self.memory_type}>"
