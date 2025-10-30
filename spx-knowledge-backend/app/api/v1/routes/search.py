from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.dependencies.database import get_db
from app.services.search_service import SearchService

router = APIRouter()


@router.get("/mixed")
def mixed_search(
    q: str = Query(..., description="查询文本"),
    top_k: int = Query(10, ge=1, le=100),
    kb_id: int | None = Query(None),
    alpha: float = Query(0.6, ge=0.0, le=1.0),
    use_vector: bool = Query(True),
    use_keywords: bool = Query(True),
    db: Session = Depends(get_db),
):
    svc = SearchService(db)
    items = svc.mixed_search(q, knowledge_base_id=kb_id, top_k=top_k, alpha=alpha, use_keywords=use_keywords, use_vector=use_vector)
    return {"code": 0, "message": "ok", "data": {"list": items, "total": len(items)}}

"""
Search API Routes
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional, Dict, Any
from app.schemas.search import (
    SearchRequest, SearchResponse, SearchSuggestionRequest,
    SearchHistoryResponse, SaveSearchRequest, SearchAdvancedRequest,
    SearchFacetsResponse, SimilarSearchRequest
)
from app.services.search_service import SearchService
from app.dependencies.database import get_db
from sqlalchemy.orm import Session

router = APIRouter()

@router.post("/", response_model=List[SearchResponse])
async def search(
    search_request: SearchRequest,
    db: Session = Depends(get_db)
):
    """基础搜索 - 支持关键词、语义、混合搜索"""
    service = SearchService(db)
    return await service.search(search_request)

@router.post("/vector", response_model=List[SearchResponse])
async def vector_search(
    search_request: SearchRequest,
    db: Session = Depends(get_db)
):
    """向量搜索 - 基于向量相似度的语义搜索"""
    service = SearchService(db)
    search_request.search_type = "vector"
    return await service.vector_search(search_request)

@router.post("/hybrid", response_model=List[SearchResponse])
async def hybrid_search(
    search_request: SearchRequest,
    db: Session = Depends(get_db)
):
    """混合搜索 - 结合关键词和语义的混合检索"""
    service = SearchService(db)
    search_request.search_type = "hybrid"
    return await service.hybrid_search(search_request)

@router.get("/suggestions")
async def get_search_suggestions(
    query: str,
    limit: int = 5,
    db: Session = Depends(get_db)
):
    """搜索建议 - 提供搜索建议和自动补全"""
    service = SearchService(db)
    request = SearchSuggestionRequest(query=query, limit=limit)
    return await service.get_suggestions(request)

@router.get("/history", response_model=List[SearchHistoryResponse])
async def get_search_history(
    user_id: Optional[int] = None,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """获取用户搜索历史"""
    service = SearchService(db)
    return await service.get_search_history(user_id=user_id, limit=limit)

@router.post("/save")
async def save_search(
    save_request: SaveSearchRequest,
    db: Session = Depends(get_db)
):
    """保存常用搜索"""
    service = SearchService(db)
    return await service.save_search(save_request)

@router.delete("/history/{history_id}")
async def delete_search_history(
    history_id: int,
    db: Session = Depends(get_db)
):
    """删除搜索历史"""
    service = SearchService(db)
    await service.delete_search_history(history_id)
    return {"message": "搜索历史已删除"}

@router.post("/advanced", response_model=List[SearchResponse])
async def advanced_search(
    advanced_request: SearchAdvancedRequest,
    db: Session = Depends(get_db)
):
    """高级搜索 - 支持复杂查询语法"""
    service = SearchService(db)
    return await service.advanced_search(advanced_request)

@router.get("/facets", response_model=SearchFacetsResponse)
async def get_search_facets(
    query: str,
    knowledge_base_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """获取搜索分面信息 - 提供搜索结果的分面统计"""
    service = SearchService(db)
    return await service.get_search_facets(query, knowledge_base_id)

@router.post("/similar", response_model=List[SearchResponse])
async def similar_search(
    similar_request: SimilarSearchRequest,
    db: Session = Depends(get_db)
):
    """相似搜索 - 基于文档相似度搜索"""
    service = SearchService(db)
    return await service.similar_search(similar_request)
