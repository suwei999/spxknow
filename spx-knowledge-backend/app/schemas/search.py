"""
Search Schemas
"""

from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
from app.schemas.base import BaseResponseSchema

class SearchRequest(BaseModel):
    """搜索请求模式"""
    query: str
    knowledge_base_id: Optional[int] = None
    search_type: str = "hybrid"  # vector, keyword, hybrid
    limit: int = 10
    offset: int = 0
    filters: Optional[Dict[str, Any]] = None  # 过滤条件
    sort_by: Optional[str] = None  # 排序方式
    sort_order: Optional[str] = "desc"  # 排序顺序

class SearchResponse(BaseResponseSchema):
    """搜索响应模式"""
    document_id: int
    chunk_id: Optional[int] = None
    content: str
    score: float
    metadata: Optional[dict] = None

class SearchSuggestionRequest(BaseModel):
    """搜索建议请求模式"""
    query: str
    limit: int = 5

class SearchSuggestionResponse(BaseModel):
    """搜索建议响应模式"""
    suggestions: List[str]
    query: str

class SearchHistoryResponse(BaseResponseSchema):
    """搜索历史响应模式"""
    id: int
    user_id: Optional[int] = None
    query: str
    search_type: str
    result_count: int
    created_at: datetime

class SaveSearchRequest(BaseModel):
    """保存搜索请求模式"""
    query: str
    search_type: str
    name: Optional[str] = None
    description: Optional[str] = None

class SearchAdvancedRequest(BaseModel):
    """高级搜索请求模式"""
    query: str
    bool_query: Optional[str] = None  # 布尔查询
    exact_phrase: Optional[str] = None  # 精确短语
    wildcard: Optional[str] = None  # 通配符
    regex: Optional[str] = None  # 正则表达式
    filters: Optional[Dict[str, Any]] = None
    knowledge_base_id: Optional[int] = None
    limit: int = 10
    offset: int = 0

class SearchFacetsResponse(BaseModel):
    """搜索分面响应模式"""
    facets: Dict[str, Dict[str, int]]  # 分面统计
    total: int

class SimilarSearchRequest(BaseModel):
    """相似搜索请求模式"""
    document_id: int
    chunk_id: Optional[int] = None
    similarity_threshold: float = 0.7
    limit: int = 10
