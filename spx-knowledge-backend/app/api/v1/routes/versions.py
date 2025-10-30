"""
Version API Routes
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from app.schemas.version import VersionResponse
from app.services.version_service import VersionService
from app.dependencies.database import get_db
from sqlalchemy.orm import Session
from app.tasks.document_tasks import reprocess_document_task

router = APIRouter()

@router.get("/", response_model=List[VersionResponse])
async def get_versions(
    skip: int = 0,
    limit: int = 100,
    document_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """获取版本列表"""
    service = VersionService(db)
    return await service.get_versions(
        skip=skip, 
        limit=limit, 
        document_id=document_id
    )

@router.get("/{version_id}", response_model=VersionResponse)
async def get_version(
    version_id: int,
    db: Session = Depends(get_db)
):
    """获取版本详情"""
    service = VersionService(db)
    version = await service.get_version(version_id)
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="版本不存在"
        )
    return version

@router.post("/{version_id}/restore")
async def restore_version(
    version_id: int,
    db: Session = Depends(get_db)
):
    """恢复版本"""
    service = VersionService(db)
    success = await service.restore_version(version_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="版本不存在"
        )
    return {"message": "版本恢复成功"}

@router.post("/documents/{document_id}/rechunk")
async def rechunk_document(
    document_id: int,
    db: Session = Depends(get_db)
):
    """触发文档重处理（仅变化块将由任务层处理）。
    这里复用现有 Celery 任务，不新增 Service 方法，保持项目风格。
    """
    # 异步触发；实际重建逻辑在任务中依据当前实现执行
    try:
        reprocess_document_task.delay(document_id)
        return {"message": "已接受重处理请求", "document_id": document_id}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
