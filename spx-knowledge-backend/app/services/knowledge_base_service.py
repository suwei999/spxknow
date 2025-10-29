"""
Knowledge Base Service
"""

from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy.orm import Session
from app.models.knowledge_base import KnowledgeBase
from app.models.knowledge_base_category import KnowledgeBaseCategory
from app.schemas.knowledge_base import KnowledgeBaseCreate, KnowledgeBaseUpdate
from app.core.exceptions import CustomException, ErrorCode
from app.services.base import BaseService

class KnowledgeBaseService(BaseService[KnowledgeBase]):
    """知识库服务"""
    
    def __init__(self, db: Session):
        super().__init__(db, KnowledgeBase)
    
    async def get_knowledge_bases(
        self, 
        skip: int = 0, 
        limit: int = 100
    ) -> List[KnowledgeBase]:
        """获取知识库列表"""
        return await self.get_multi(skip=skip, limit=limit)

    async def get_knowledge_bases_paginated(
        self,
        page: int = 1,
        size: int = 20,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """分页获取知识库列表，返回 (items(dict), total)
        包含 category_name 以便前端直接展示
        """
        skip = max(page - 1, 0) * max(size, 1)
        base_query = (
            self.db.query(
                KnowledgeBase,
                KnowledgeBaseCategory.name.label("category_name")
            )
            .outerjoin(KnowledgeBaseCategory, KnowledgeBase.category_id == KnowledgeBaseCategory.id)
            .filter(KnowledgeBase.is_deleted == False)
        )
        total = base_query.count()
        rows = base_query.offset(skip).limit(size).all()
        items: List[Dict[str, Any]] = []
        for kb, category_name in rows:
            items.append({
                "id": kb.id,
                "name": kb.name,
                "description": kb.description,
                "category_id": kb.category_id,
                "category_name": category_name,
                "is_active": kb.is_active,
                "created_at": kb.created_at,
                "updated_at": kb.updated_at,
            })
        return items, total
    
    async def get_knowledge_base(self, kb_id: int) -> Optional[KnowledgeBase]:
        """获取知识库详情"""
        return await self.get(kb_id)
    
    async def create_knowledge_base(
        self, 
        kb_data: KnowledgeBaseCreate
    ) -> KnowledgeBase:
        """创建知识库"""
        # 名称唯一性校验
        existing = self.db.query(KnowledgeBase).filter(
            KnowledgeBase.name == kb_data.name,
            KnowledgeBase.is_deleted == False
        ).first()
        if existing:
            raise CustomException(code=ErrorCode.VALIDATION_ERROR, message="知识库名称已存在")
        # 排除 None/未提供的可选字段（如 category_name）
        return await self.create(kb_data.dict(exclude_none=True, exclude_unset=True))
    
    async def update_knowledge_base(
        self, 
        kb_id: int, 
        kb_data: KnowledgeBaseUpdate
    ) -> Optional[KnowledgeBase]:
        """更新知识库"""
        # 如果修改了名称，进行唯一性校验
        if kb_data.name is not None:
            conflict = self.db.query(KnowledgeBase).filter(
                KnowledgeBase.name == kb_data.name,
                KnowledgeBase.id != kb_id,
                KnowledgeBase.is_deleted == False
            ).first()
            if conflict:
                raise CustomException(code=ErrorCode.VALIDATION_ERROR, message="知识库名称已存在")
        # 排除 None/未提供的可选字段（如 category_name）
        return await self.update(kb_id, kb_data.dict(exclude_unset=True, exclude_none=True))
    
    async def delete_knowledge_base(self, kb_id: int) -> bool:
        """删除知识库（硬删除）"""
        # 直接物理删除记录；若存在外键约束导致删除失败，将抛出异常由上层捕获
        obj = self.db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
        if not obj:
            return False
        self.db.delete(obj)
        self.db.commit()
        return True
