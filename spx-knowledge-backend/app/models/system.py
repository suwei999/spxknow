"""
System Model
"""

from sqlalchemy import Column, String, Text, Integer, DateTime, Boolean, ForeignKey, Float
from sqlalchemy.orm import relationship
from app.models.base import BaseModel

class SystemConfig(BaseModel):
    """系统配置模型"""
    __tablename__ = "system_configs"
    
    key = Column(String(100), nullable=False, unique=True, comment="配置键")
    value = Column(Text, comment="配置值")
    description = Column(Text, comment="配置描述")
    config_type = Column(String(50), default="string", comment="配置类型")
    is_active = Column(Boolean, default=True, comment="是否激活")
    
    # 关系
    # 可以根据需要添加关系

class OperationLog(BaseModel):
    """操作日志模型"""
    __tablename__ = "operation_logs"
    
    operation_type = Column(String(50), nullable=False, comment="操作类型")
    operation_description = Column(Text, comment="操作描述")
    user_id = Column(Integer, comment="用户ID")
    resource_type = Column(String(50), comment="资源类型")
    resource_id = Column(Integer, comment="资源ID")
    ip_address = Column(String(50), comment="IP地址")
    user_agent = Column(Text, comment="用户代理")
    
    # 关系
    # 可以根据需要添加关系
