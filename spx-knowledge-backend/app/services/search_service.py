"""
Mixed Search Service: 向量 + 关键词 融合检索
"""

from typing import List, Dict, Any, Optional
from app.services.opensearch_service import OpenSearchService
from app.services.vector_service import VectorService
from sqlalchemy.orm import Session
from app.core.logging import logger


class SearchService:
    def __init__(self, db: Session):
        self.db = db
        self.os = OpenSearchService()
        self.vs = VectorService(db)

    def mixed_search(
        self,
        query_text: str,
        knowledge_base_id: Optional[int] = None,
        top_k: int = 10,
        alpha: float = 0.6,
        use_keywords: bool = True,
        use_vector: bool = True,
    ) -> List[Dict[str, Any]]:
        """向量 + 关键词 融合; 简单线性加权融合得分。"""
        results: List[Dict[str, Any]] = []
        vector_hits: List[Dict[str, Any]] = []
        keyword_hits: List[Dict[str, Any]] = []

        try:
            if use_vector:
                qv = self.vs.generate_embedding(query_text)
                vector_hits = self.os.search_document_vectors(
                    query_vector=qv, similarity_threshold=0.0, limit=top_k * 2, knowledge_base_id=knowledge_base_id
                ) or []
        except Exception as e:
            logger.warning(f"向量检索失败: {e}")

        try:
            if use_keywords:
                # 关键词检索：复用 OpenSearchService 的 client
                must: List[Dict[str, Any]] = [
                    {"match": {"content": {"query": query_text}}}
                ]
                if knowledge_base_id:
                    must.append({"term": {"knowledge_base_id": knowledge_base_id}})
                resp = self.os.client.search(
                    index=self.os.document_index,
                    body={
                        "query": {"bool": {"must": must}},
                        "size": top_k * 2,
                    },
                )
                keyword_hits = [
                    {
                        "chunk_id": h["_source"].get("chunk_id"),
                        "document_id": h["_source"].get("document_id"),
                        "knowledge_base_id": h["_source"].get("knowledge_base_id"),
                        "content": h["_source"].get("content"),
                        "bm25_score": h.get("_score", 0.0),
                    }
                    for h in resp.get("hits", {}).get("hits", [])
                ]
        except Exception as e:
            logger.warning(f"关键词检索失败: {e}")

        # 融合
        by_id: Dict[int, Dict[str, Any]] = {}
        for h in vector_hits:
            cid = h.get("chunk_id")
            if cid is None:
                continue
            by_id[cid] = {
                "chunk_id": cid,
                "document_id": h.get("document_id"),
                "knowledge_base_id": h.get("knowledge_base_id"),
                "content": h.get("content"),
                "knn_score": h.get("similarity_score", 0.0),
                "bm25_score": 0.0,
            }
        for h in keyword_hits:
            cid = h.get("chunk_id")
            if cid is None:
                continue
            item = by_id.get(cid)
            if item is None:
                by_id[cid] = {**h, "knn_score": 0.0}
            else:
                item["bm25_score"] = h.get("bm25_score", 0.0)

        for v in by_id.values():
            v["score"] = alpha * v.get("knn_score", 0.0) + (1 - alpha) * v.get("bm25_score", 0.0)
            results.append(v)

        results.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        return results[:top_k]

"""
Search Service
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from app.schemas.search import (
    SearchRequest, SearchResponse, SearchSuggestionRequest,
    SearchHistoryResponse, SaveSearchRequest, SearchAdvancedRequest,
    SearchFacetsResponse, SimilarSearchRequest
)
from app.services.base import BaseService

class SearchService:
    """搜索服务"""
    
    def __init__(self, db: Session):
        self.db = db
    
    async def search(self, search_request: SearchRequest) -> List[SearchResponse]:
        """搜索文档 - 支持关键词、语义、混合搜索"""
        # TODO: 实现基础搜索逻辑
        # 1. 根据search_type调用不同的搜索方法
        # 2. 应用过滤条件和排序
        # 3. 返回搜索结果
        if search_request.search_type == "vector":
            return await self.vector_search(search_request)
        elif search_request.search_type == "hybrid":
            return await self.hybrid_search(search_request)
        else:
            return []
    
    async def vector_search(self, search_request: SearchRequest) -> List[SearchResponse]:
        """向量搜索 - 基于向量相似度的语义搜索"""
        # TODO: 实现向量搜索逻辑
        # 1. 使用OpenSearch向量检索
        # 2. 计算相似度分数
        # 3. 返回排序结果
        return []
    
    async def hybrid_search(self, search_request: SearchRequest) -> List[SearchResponse]:
        """混合搜索 - 结合关键词和语义的混合检索"""
        # TODO: 实现混合搜索逻辑
        # 1. 并行执行关键词和向量搜索
        # 2. 使用学习排序融合结果
        # 3. 去重和多样性保证
        return []
    
    async def get_suggestions(self, request: SearchSuggestionRequest) -> List[str]:
        """获取搜索建议"""
        # TODO: 实现搜索建议逻辑
        # 1. 从Redis或OpenSearch获取热门搜索
        # 2. 基于查询前缀匹配
        # 3. 返回建议列表
        return []
    
    async def get_search_history(self, user_id: Optional[int] = None, limit: int = 20) -> List[SearchHistoryResponse]:
        """获取搜索历史"""
        # TODO: 实现搜索历史逻辑
        # 1. 从数据库查询用户搜索历史
        # 2. 按时间排序
        # 3. 返回历史列表
        return []
    
    async def save_search(self, save_request: SaveSearchRequest) -> Dict[str, Any]:
        """保存搜索"""
        # TODO: 实现保存搜索逻辑
        # 1. 保存到数据库
        # 2. 返回保存结果
        return {"message": "搜索已保存"}
    
    async def delete_search_history(self, history_id: int) -> None:
        """删除搜索历史"""
        # TODO: 实现删除搜索历史逻辑
        # 1. 从数据库删除指定历史记录
        pass
    
    async def advanced_search(self, advanced_request: SearchAdvancedRequest) -> List[SearchResponse]:
        """高级搜索 - 支持复杂查询语法"""
        # TODO: 实现高级搜索逻辑
        # 1. 解析布尔查询、通配符、正则表达式等
        # 2. 构建复杂查询语句
        # 3. 执行搜索并返回结果
        return []
    
    async def get_search_facets(self, query: str, knowledge_base_id: Optional[int] = None) -> SearchFacetsResponse:
        """获取搜索分面信息"""
        # TODO: 实现分面搜索逻辑
        # 1. 执行搜索聚合查询
        # 2. 统计各个分面的数量
        # 3. 返回分面信息
        return SearchFacetsResponse(facets={}, total=0)
    
    async def similar_search(self, similar_request: SimilarSearchRequest) -> List[SearchResponse]:
        """相似搜索 - 基于文档相似度搜索"""
        # TODO: 实现相似搜索逻辑
        # 1. 获取目标文档的向量
        # 2. 使用向量相似度搜索
        # 3. 返回相似文档
        return []
