"""Diagnosis iteration model."""

from sqlalchemy import Column, Integer, String, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class DiagnosisIteration(BaseModel):
    """单次诊断 Reasoning + Acting 迭代记录。"""

    __tablename__ = "diagnosis_iterations"

    diagnosis_id = Column(Integer, ForeignKey("diagnosis_records.id"), nullable=False, comment="所属诊断记录")
    iteration_no = Column(Integer, nullable=False, comment="迭代序号")
    stage = Column(String(64), nullable=True, comment="迭代阶段")
    status = Column(String(32), default="pending", comment="迭代状态")
    reasoning_prompt = Column(Text, nullable=True, comment="推理提示")
    reasoning_summary = Column(Text, nullable=True, comment="推理摘要")
    reasoning_output = Column(JSON, nullable=True, comment="推理原始输出")
    action_plan = Column(JSON, nullable=True, comment="执行计划")
    action_result = Column(JSON, nullable=True, comment="执行结果")
    meta = Column("metadata", JSON, nullable=True, comment="扩展信息")

    diagnosis = relationship("DiagnosisRecord", back_populates="iterations")
    memories = relationship("DiagnosisMemory", back_populates="iteration")

    def __repr__(self) -> str:
        return f"<DiagnosisIteration id={self.id} diagnosis_id={self.diagnosis_id} iteration={self.iteration_no}>"

