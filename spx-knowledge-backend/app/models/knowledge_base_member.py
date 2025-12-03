"""
Knowledge Base Member Model
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime

from app.models.base import Base


class KnowledgeBaseMember(Base):
    """知识库成员表"""

    __tablename__ = "knowledge_base_members"
    __table_args__ = (
        UniqueConstraint(
            "knowledge_base_id",
            "user_id",
            name="uk_kb_member",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    knowledge_base_id = Column(
        Integer, ForeignKey("knowledge_bases.id"), nullable=False, comment="知识库ID"
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, comment="用户ID")
    role = Column(
        String(20),
        default="viewer",
        nullable=False,
        comment="角色: owner/viewer/editor/admin",
    )
    invited_by = Column(Integer, ForeignKey("users.id"), comment="邀请人ID")
    invited_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="邀请时间",
    )
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="创建时间",
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="更新时间",
    )

    # 关系
    knowledge_base = relationship("KnowledgeBase", back_populates="members")
    user = relationship("User", foreign_keys=[user_id])
    inviter = relationship("User", foreign_keys=[invited_by])
