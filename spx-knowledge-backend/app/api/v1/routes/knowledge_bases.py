"""
Knowledge Base API Routes
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from app.schemas.knowledge_base import KnowledgeBaseCreate, KnowledgeBaseUpdate, KnowledgeBaseResponse, KnowledgeBaseListResponse
from app.core.response import success_response
from app.services.knowledge_base_service import KnowledgeBaseService
from app.services.knowledge_base_category_service import KnowledgeBaseCategoryService
from app.models.knowledge_base_category import KnowledgeBaseCategory
from app.dependencies.database import get_db
from sqlalchemy.orm import Session

router = APIRouter()

@router.get("/")
async def get_knowledge_bases(
    page: int = 1,
    size: int = 20,
    db: Session = Depends(get_db)
):
    """获取知识库列表（分页）"""
    service = KnowledgeBaseService(db)
    items, total = await service.get_knowledge_bases_paginated(page=page, size=size)
    # 兼容部分前端对 {code, message, data} 的期望结构
    return {
        "code": 0,
        "message": "ok",
        "data": {"list": items, "total": total, "page": page, "size": size}
    }

@router.post("/")
async def create_knowledge_base(
    knowledge_base: KnowledgeBaseCreate,
    db: Session = Depends(get_db)
):
    """创建知识库"""
    # 允许通过 category_name 动态创建或复用分类；分类为必填
    kb_data = knowledge_base.dict(exclude_unset=True)
    # 校验分类
    if not kb_data.get("category_id") and not (kb_data.get("category_name") and kb_data.get("category_name").strip()):
        return {"code": 400, "message": "分类必填", "data": None}
    # 保留名称（创建时必填）
    if not kb_data.get("category_id") and kb_data.get("category_name"):
        name = kb_data.get("category_name").strip()
        if name:
            existing = db.query(KnowledgeBaseCategory).filter(
                KnowledgeBaseCategory.name == name,
                KnowledgeBaseCategory.is_deleted == False
            ).first()
            if existing:
                kb_data["category_id"] = existing.id
            else:
                cat_service = KnowledgeBaseCategoryService(db)
                created = cat_service.create_category({"name": name})
                kb_data["category_id"] = created["id"]
    kb_data.pop("category_name", None)
    service = KnowledgeBaseService(db)
    kb = await service.create_knowledge_base(KnowledgeBaseCreate.parse_obj(kb_data))
    return {"code": 0, "message": "ok", "data": kb}

@router.get("/{kb_id}")
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
    return {"code": 0, "message": "ok", "data": kb}

@router.put("/{kb_id}")
async def update_knowledge_base(
    kb_id: int,
    knowledge_base: KnowledgeBaseUpdate,
    db: Session = Depends(get_db)
):
    """更新知识库"""
    kb_data = knowledge_base.dict(exclude_unset=True)
    if not kb_data.get("category_id") and kb_data.get("category_name"):
        name = kb_data.get("category_name").strip()
        if name:
            existing = db.query(KnowledgeBaseCategory).filter(
                KnowledgeBaseCategory.name == name,
                KnowledgeBaseCategory.is_deleted == False
            ).first()
            if existing:
                kb_data["category_id"] = existing.id
            else:
                cat_service = KnowledgeBaseCategoryService(db)
                created = cat_service.create_category({"name": name})
                kb_data["category_id"] = created["id"]
    kb_data.pop("category_name", None)
    service = KnowledgeBaseService(db)
    kb = await service.update_knowledge_base(kb_id, KnowledgeBaseUpdate.parse_obj(kb_data))
    if not kb:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="知识库不存在"
        )
    return {"code": 0, "message": "ok", "data": kb}

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
    return {"code": 0, "message": "ok", "data": {"id": kb_id}}
