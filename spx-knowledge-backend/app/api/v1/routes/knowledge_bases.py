"""
Knowledge Base API Routes
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from app.schemas.knowledge_base import KnowledgeBaseCreate, KnowledgeBaseUpdate, KnowledgeBaseResponse
from app.services.knowledge_base_service import KnowledgeBaseService
from app.dependencies.database import get_db
from sqlalchemy.orm import Session

router = APIRouter()

@router.get("/", response_model=List[KnowledgeBaseResponse])
async def get_knowledge_bases(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """获取知识库列表"""
    service = KnowledgeBaseService(db)
    return await service.get_knowledge_bases(skip=skip, limit=limit)

@router.post("/", response_model=KnowledgeBaseResponse)
async def create_knowledge_base(
    knowledge_base: KnowledgeBaseCreate,
    db: Session = Depends(get_db)
):
    """创建知识库"""
    service = KnowledgeBaseService(db)
    return await service.create_knowledge_base(knowledge_base)

@router.get("/{kb_id}", response_model=KnowledgeBaseResponse)
async def get_knowledge_base(
    kb_id: int,
    db: Session = Depends(get_db)
):
    """获取知识库详情"""
    service = KnowledgeBaseService(db)
    kb = await service.get_knowledge_base(kb_id)
    if not kb:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="知识库不存在"
        )
    return kb

@router.put("/{kb_id}", response_model=KnowledgeBaseResponse)
async def update_knowledge_base(
    kb_id: int,
    knowledge_base: KnowledgeBaseUpdate,
    db: Session = Depends(get_db)
):
    """更新知识库"""
    service = KnowledgeBaseService(db)
    kb = await service.update_knowledge_base(kb_id, knowledge_base)
    if not kb:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="知识库不存在"
        )
    return kb

@router.delete("/{kb_id}")
async def delete_knowledge_base(
    kb_id: int,
    db: Session = Depends(get_db)
):
    """删除知识库"""
    service = KnowledgeBaseService(db)
    success = await service.delete_knowledge_base(kb_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="知识库不存在"
        )
    return {"message": "知识库删除成功"}
