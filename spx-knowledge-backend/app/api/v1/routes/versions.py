"""
Version API Routes
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from app.schemas.version import VersionResponse
from app.services.version_service import VersionService
from app.dependencies.database import get_db
from sqlalchemy.orm import Session

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
