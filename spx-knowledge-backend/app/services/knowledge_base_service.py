"""
Knowledge Base Service
"""

from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.knowledge_base import KnowledgeBase
from app.schemas.knowledge_base import KnowledgeBaseCreate, KnowledgeBaseUpdate
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
    
    async def get_knowledge_base(self, kb_id: int) -> Optional[KnowledgeBase]:
        """获取知识库详情"""
        return await self.get(kb_id)
    
    async def create_knowledge_base(
        self, 
        kb_data: KnowledgeBaseCreate
    ) -> KnowledgeBase:
        """创建知识库"""
        return await self.create(kb_data.dict())
    
    async def update_knowledge_base(
        self, 
        kb_id: int, 
        kb_data: KnowledgeBaseUpdate
    ) -> Optional[KnowledgeBase]:
        """更新知识库"""
        return await self.update(kb_id, kb_data.dict(exclude_unset=True))
    
    async def delete_knowledge_base(self, kb_id: int) -> bool:
        """删除知识库"""
        return await self.delete(kb_id)
