"""
User Model
用户认证系统数据模型
"""

from sqlalchemy import Column, String, Integer, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.base import BaseModel


class User(BaseModel):
    """用户模型"""
    __tablename__ = "users"
    
    username = Column(String(50), nullable=False, unique=True, index=True, comment="用户名")
    email = Column(String(100), nullable=False, unique=True, index=True, comment="邮箱")
    password_hash = Column(String(255), nullable=False, comment="密码哈希")
    nickname = Column(String(100), comment="昵称")
    avatar_url = Column(String(500), comment="头像URL")
    phone = Column(String(20), comment="手机号")
    status = Column(String(20), default="active", index=True, comment="状态：active/inactive/locked")
    email_verified = Column(Boolean, default=False, index=True, comment="邮箱是否已验证")
    last_login_at = Column(DateTime, comment="最后登录时间")
    last_login_ip = Column(String(50), comment="最后登录IP")
    login_count = Column(Integer, default=0, comment="登录次数")
    failed_login_attempts = Column(Integer, default=0, comment="失败登录次数")
    locked_until = Column(DateTime, comment="锁定到期时间")
    preferences = Column(Text, comment="用户偏好设置JSON")
    
    # 关系
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    email_verifications = relationship("EmailVerification", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', email='{self.email}')>"


class RefreshToken(BaseModel):
    """刷新Token模型"""
    __tablename__ = "refresh_tokens"
    
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="用户ID")
    token = Column(String(255), nullable=False, unique=True, index=True, comment="刷新Token")
    expires_at = Column(DateTime, nullable=False, index=True, comment="过期时间")
    device_info = Column(String(200), comment="设备信息")
    ip_address = Column(String(50), comment="IP地址")
    is_revoked = Column(Boolean, default=False, comment="是否已撤销")
    
    # 关系
    user = relationship("User", back_populates="refresh_tokens")
    
    def __repr__(self):
        return f"<RefreshToken(id={self.id}, user_id={self.user_id}, expires_at={self.expires_at})>"


class EmailVerification(BaseModel):
    """邮箱验证模型"""
    __tablename__ = "email_verifications"
    
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, comment="用户ID")
    email = Column(String(100), nullable=False, comment="邮箱")
    verification_code = Column(String(10), nullable=False, index=True, comment="验证码")
    expires_at = Column(DateTime, nullable=False, comment="过期时间")
    is_used = Column(Boolean, default=False, comment="是否已使用")
    
    # 关系
    user = relationship("User", back_populates="email_verifications")
    
    def __repr__(self):
        return f"<EmailVerification(id={self.id}, user_id={self.user_id}, email='{self.email}')>"

