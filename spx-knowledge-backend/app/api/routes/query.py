from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Any, Dict

from app.config.database import SessionLocal
from sqlalchemy.orm import Session
from app.services.query_service import QueryService

router = APIRouter(prefix="/query", tags=["query"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class ContextResponse(BaseModel):
    data: Dict[str, Any]


@router.get("/documents/{document_id}/chunks/{chunk_id}/context", response_model=ContextResponse)
def get_chunk_context(
    document_id: int,
    chunk_id: int,
    neighbor_pre: int = 1,
    neighbor_next: int = 1,
    parent_group_max_chars: int = 1500,
    db: Session = Depends(get_db),
):
    service = QueryService(db)
    result = service.get_context_for_hit(
        document_id=document_id,
        hit_chunk_id=chunk_id,
        neighbor_pre=neighbor_pre,
        neighbor_next=neighbor_next,
        parent_group_max_chars=parent_group_max_chars,
    )
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return {"data": result}
