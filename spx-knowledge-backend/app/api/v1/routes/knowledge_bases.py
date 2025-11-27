"""
Knowledge Base API Routes
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import List, Optional
from app.schemas.knowledge_base import KnowledgeBaseCreate, KnowledgeBaseUpdate, KnowledgeBaseResponse, KnowledgeBaseListResponse
from app.core.response import success_response
from app.services.knowledge_base_service import KnowledgeBaseService
from app.services.knowledge_base_category_service import KnowledgeBaseCategoryService
from app.models.knowledge_base_category import KnowledgeBaseCategory
from app.dependencies.database import get_db
from sqlalchemy.orm import Session

router = APIRouter()

def get_current_user_id(request: Request) -> int:
    """从请求中获取当前用户ID（由中间件设置）"""
    user = getattr(request.state, 'user', None)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未认证")
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的用户信息")
    try:
        return int(user_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的用户ID")

@router.get("/")
async def get_knowledge_bases(
    request: Request,
    page: int = 1,
    size: int = 20,
    db: Session = Depends(get_db)
):
    """获取知识库列表（分页）"""
    # 获取当前用户ID
    user_id = get_current_user_id(request)
    service = KnowledgeBaseService(db)
    items, total = await service.get_knowledge_bases_paginated(page=page, size=size, user_id=user_id)
    # 兼容部分前端对 {code, message, data} 的期望结构
    return {
        "code": 0,
        "message": "ok",
        "data": {"list": items, "total": total, "page": page, "size": size}
    }

@router.post("/")
async def create_knowledge_base(
    request: Request,
    knowledge_base: KnowledgeBaseCreate,
    db: Session = Depends(get_db)
):
    """创建知识库"""
    # 获取当前用户ID
    user_id = get_current_user_id(request)
    # 允许通过 category_name 动态创建或复用分类；分类为必填
    kb_data = knowledge_base.dict(exclude_unset=True)
    # 设置用户ID（数据隔离）
    kb_data["user_id"] = user_id
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
    kb = await service.create_knowledge_base(KnowledgeBaseCreate.parse_obj(kb_data), user_id=user_id)
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
