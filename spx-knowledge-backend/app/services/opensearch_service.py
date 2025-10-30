"""
OpenSearch Service
根据文档处理流程设计实现OpenSearch集成功能
"""

from typing import List, Optional, Dict, Any
import json
from opensearchpy import OpenSearch, RequestsHttpConnection
from opensearchpy.helpers import bulk as os_bulk
from opensearchpy.exceptions import OpenSearchException
from app.config.settings import settings
from app.core.logging import logger
from app.core.exceptions import CustomException, ErrorCode

class OpenSearchService:
    """OpenSearch服务 - 严格按照设计文档实现"""
    
    def __init__(self):
        self.client = self._create_client()
        self.document_index = "documents"
        self.image_index = "images"
        self.qa_index = "qa_history"
        self._ensure_indices_exist()
    
    def _create_client(self) -> OpenSearch:
        """创建OpenSearch客户端"""
        try:
            logger.info("创建OpenSearch客户端")
            
            # 根据设计文档的OpenSearch配置
            client = OpenSearch(
                hosts=[settings.OPENSEARCH_URL],
                use_ssl=settings.OPENSEARCH_USE_SSL,
                verify_certs=settings.OPENSEARCH_VERIFY_CERTS,
                connection_class=RequestsHttpConnection,
                timeout=30,
                max_retries=3,
                retry_on_timeout=True
            )
            
            logger.info("OpenSearch客户端创建成功")
            return client
            
        except Exception as e:
            logger.error(f"创建OpenSearch客户端失败: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.OPENSEARCH_CONNECTION_FAILED,
                message=f"OpenSearch连接失败: {str(e)}"
            )
    
    def _ensure_indices_exist(self):
        """确保索引存在 - 根据设计文档的索引设计"""
        try:
            logger.info("检查并创建OpenSearch索引")
            
            # 创建文档内容索引
            if not self.client.indices.exists(index=self.document_index):
                self._create_document_index()
            
            # 创建图片专用索引
            if not self.client.indices.exists(index=self.image_index):
                self._create_image_index()
            
            # 创建问答历史索引
            if not self.client.indices.exists(index=self.qa_index):
                self._create_qa_index()
            
            logger.info("OpenSearch索引检查完成")
            
        except Exception as e:
            logger.error(f"创建OpenSearch索引失败: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.OPENSEARCH_INDEX_FAILED,
                message=f"OpenSearch索引创建失败: {str(e)}"
            )
    
    def _create_document_index(self):
        """创建文档内容索引 - 根据设计文档实现"""
        try:
            logger.info(f"创建文档索引: {self.document_index}")
            
            # 根据设计文档的索引配置
            index_mapping = {
                "settings": {
                    "number_of_shards": 3,
                    "number_of_replicas": 1,
                    "analysis": {
                        "analyzer": {
                            "ik_max_word": {
                                "type": "ik_max_word"
                            }
                        }
                    }
                },
                "mappings": {
                    "properties": {
                        # 基础字段
                        "document_id": {"type": "integer"},
                        "knowledge_base_id": {"type": "integer"},
                        "category_id": {"type": "integer"},
                        "chunk_id": {"type": "integer"},
                        
                        # 内容字段
                        "content": {
                            "type": "text",
                            "analyzer": "ik_max_word",
                            "search_analyzer": "ik_max_word"
                        },
                        "chunk_type": {"type": "keyword"},
                        "tags": {"type": "keyword"},
                        "metadata": {"type": "text"},
                        
                        # 时间字段
                        "created_at": {"type": "date"},
                        
                        # 向量字段 - 768维文本向量，HNSW算法
                        "content_vector": {
                            "type": "knn_vector",
                            "dimension": 768,
                            "method": {
                                "name": "hnsw",
                                "space_type": "cosinesimil",
                                "engine": "nmslib",
                                "parameters": {
                                    "ef_construction": 128,
                                    "m": 24
                                }
                            }
                        },
                        
                        # 图片字段
                        "image_info": {
                            "type": "object",
                            "properties": {
                                "image_id": {"type": "integer"},
                                "image_path": {"type": "keyword"},
                                "page_number": {"type": "integer"},
                                "coordinates": {"type": "object"},
                                "image_type": {"type": "keyword"},
                                "ocr_text": {"type": "text"},
                                "description": {"type": "text"}
                            }
                        }
                    }
                }
            }
            
            self.client.indices.create(index=self.document_index, body=index_mapping)
            logger.info(f"文档索引创建成功: {self.document_index}")
            
        except Exception as e:
            logger.error(f"创建文档索引失败: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.OPENSEARCH_INDEX_FAILED,
                message=f"文档索引创建失败: {str(e)}"
            )
    
    def _create_image_index(self):
        """创建图片专用索引 - 根据设计文档实现"""
        try:
            logger.info(f"创建图片索引: {self.image_index}")
            
            # 根据设计文档的图片索引配置
            index_mapping = {
                "settings": {
                    "number_of_shards": 3,
                    "number_of_replicas": 1
                },
                "mappings": {
                    "properties": {
                        # 基础字段
                        "image_id": {"type": "integer"},
                        "document_id": {"type": "integer"},
                        "knowledge_base_id": {"type": "integer"},
                        "category_id": {"type": "integer"},
                        
                        # 图片字段
                        "image_path": {"type": "keyword"},
                        "page_number": {"type": "integer"},
                        "coordinates": {"type": "object"},
                        "width": {"type": "integer"},
                        "height": {"type": "integer"},
                        "image_type": {"type": "keyword"},
                        
                        # 内容字段
                        "ocr_text": {
                            "type": "text",
                            "analyzer": "ik_max_word"
                        },
                        "description": {"type": "text"},
                        "feature_tags": {"type": "keyword"},
                        
                        # 向量字段 - 512维图片向量，HNSW算法
                        "image_vector": {
                            "type": "knn_vector",
                            "dimension": 512,
                            "method": {
                                "name": "hnsw",
                                "space_type": "cosinesimil",
                                "engine": "nmslib",
                                "parameters": {
                                    "ef_construction": 128,
                                    "m": 24
                                }
                            }
                        },
                        
                        # 时间字段
                        "created_at": {"type": "date"},
                        "updated_at": {"type": "date"},
                        
                        # 元数据字段
                        "metadata": {"type": "object"},
                        "processing_status": {"type": "keyword"},
                        "model_version": {"type": "keyword"}
                    }
                }
            }
            
            self.client.indices.create(index=self.image_index, body=index_mapping)
            logger.info(f"图片索引创建成功: {self.image_index}")
            
        except Exception as e:
            logger.error(f"创建图片索引失败: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.OPENSEARCH_INDEX_FAILED,
                message=f"图片索引创建失败: {str(e)}"
            )
    
    def _create_qa_index(self):
        """创建问答历史索引 - 根据设计文档实现"""
        try:
            logger.info(f"创建问答历史索引: {self.qa_index}")
            
            index_mapping = {
                "settings": {
                    "number_of_shards": 3,
                    "number_of_replicas": 1
                },
                "mappings": {
                    "properties": {
                        "session_id": {"type": "keyword"},
                        "question_id": {"type": "integer"},
                        "question_text": {"type": "text"},
                        "answer_text": {"type": "text"},
                        "knowledge_base_id": {"type": "integer"},
                        "query_method": {"type": "keyword"},
                        "relevance_score": {"type": "float"},
                        "created_at": {"type": "date"},
                        "question_vector": {
                            "type": "knn_vector",
                            "dimension": 768,
                            "method": {
                                "name": "hnsw",
                                "space_type": "cosinesimil",
                                "engine": "nmslib"
                            }
                        }
                    }
                }
            }
            
            self.client.indices.create(index=self.qa_index, body=index_mapping)
            logger.info(f"问答历史索引创建成功: {self.qa_index}")
            
        except Exception as e:
            logger.error(f"创建问答历史索引失败: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.OPENSEARCH_INDEX_FAILED,
                message=f"问答历史索引创建失败: {str(e)}"
            )
    
    async def index_document_chunk(self, chunk_data: Dict[str, Any]) -> bool:
        """索引文档分块 - 根据设计文档实现"""
        try:
            logger.info(f"开始索引文档分块: {chunk_data.get('chunk_id')}")
            
            # 构建索引文档
            doc = {
                "document_id": chunk_data["document_id"],
                "knowledge_base_id": chunk_data["knowledge_base_id"],
                "category_id": chunk_data.get("category_id"),
                "chunk_id": chunk_data["chunk_id"],
                "content": chunk_data["content"],
                "chunk_type": chunk_data.get("chunk_type", "text"),
                "tags": chunk_data.get("tags", []),
                "metadata": json.dumps(chunk_data.get("metadata", {})),
                "created_at": chunk_data.get("created_at"),
                "content_vector": chunk_data["content_vector"]
            }
            
            # 如果有图片信息，添加图片字段
            if chunk_data.get("image_info"):
                doc["image_info"] = chunk_data["image_info"]
            
            # 索引到OpenSearch
            response = self.client.index(
                index=self.document_index,
                id=f"chunk_{chunk_data['chunk_id']}",
                body=doc,
                refresh="wait_for"
            )
            
            logger.info(f"文档分块索引成功: {chunk_data.get('chunk_id')}")
            return True
            
        except Exception as e:
            logger.error(f"文档分块索引失败: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.OPENSEARCH_INDEX_FAILED,
                message=f"文档分块索引失败: {str(e)}"
            )

    # 同步封装，供 Celery 同步任务直接调用
    def index_document_chunk_sync(self, chunk_data: Dict[str, Any]) -> bool:
        return self.client.index(
            index=self.document_index,
            id=f"chunk_{chunk_data['chunk_id']}",
            body={
                "document_id": chunk_data["document_id"],
                "knowledge_base_id": chunk_data["knowledge_base_id"],
                "category_id": chunk_data.get("category_id"),
                "chunk_id": chunk_data["chunk_id"],
                "content": chunk_data["content"],
                "chunk_type": chunk_data.get("chunk_type", "text"),
                "tags": chunk_data.get("tags", []),
                "metadata": json.dumps(chunk_data.get("metadata", {})),
                "created_at": chunk_data.get("created_at"),
                "content_vector": chunk_data["content_vector"],
                **({"image_info": chunk_data["image_info"]} if chunk_data.get("image_info") else {}),
            },
            refresh="wait_for",
        )
        or True

    def bulk_index_document_chunks_sync(self, docs: List[Dict[str, Any]]) -> int:
        """批量索引分块，返回成功条数。"""
        actions = []
        for d in docs:
            src = {
                "document_id": d["document_id"],
                "knowledge_base_id": d["knowledge_base_id"],
                "category_id": d.get("category_id"),
                "chunk_id": d["chunk_id"],
                "content": d["content"],
                "chunk_type": d.get("chunk_type", "text"),
                "tags": d.get("tags", []),
                "metadata": json.dumps(d.get("metadata", {})),
                "created_at": d.get("created_at"),
                "content_vector": d["content_vector"],
            }
            if d.get("image_info"):
                src["image_info"] = d["image_info"]
            actions.append({
                "_index": self.document_index,
                "_id": f"chunk_{d['chunk_id']}",
                "_source": src,
            })
        success, _ = os_bulk(self.client, actions, refresh=True)
        logger.info(f"批量索引分块完成: {success} 条")
        return success
    
    async def index_image(self, image_data: Dict[str, Any]) -> bool:
        """索引图片 - 根据设计文档实现"""
        try:
            logger.info(f"开始索引图片: {image_data.get('image_id')}")
            
            # 构建索引文档
            doc = {
                "image_id": image_data["image_id"],
                "document_id": image_data["document_id"],
                "knowledge_base_id": image_data["knowledge_base_id"],
                "category_id": image_data.get("category_id"),
                "image_path": image_data["image_path"],
                "page_number": image_data.get("page_number"),
                "coordinates": image_data.get("coordinates"),
                "width": image_data.get("width"),
                "height": image_data.get("height"),
                "image_type": image_data.get("image_type", "unknown"),
                "ocr_text": image_data.get("ocr_text", ""),
                "description": image_data.get("description", ""),
                "feature_tags": image_data.get("feature_tags", []),
                "image_vector": image_data["image_vector"],
                "created_at": image_data.get("created_at"),
                "updated_at": image_data.get("updated_at"),
                "metadata": json.dumps(image_data.get("metadata", {})),
                "processing_status": image_data.get("processing_status", "completed"),
                "model_version": image_data.get("model_version", "1.0")
            }
            
            # 索引到OpenSearch
            response = self.client.index(
                index=self.image_index,
                id=f"image_{image_data['image_id']}",
                body=doc,
                refresh="wait_for"
            )
            
            logger.info(f"图片索引成功: {image_data.get('image_id')}")
            return True
            
        except Exception as e:
            logger.error(f"图片索引失败: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.OPENSEARCH_INDEX_FAILED,
                message=f"图片索引失败: {str(e)}"
            )

    # 同步封装
    def index_image_sync(self, image_data: Dict[str, Any]) -> bool:
        return self.client.index(
            index=self.image_index,
            id=f"image_{image_data['image_id']}",
            body={
                "image_id": image_data["image_id"],
                "document_id": image_data["document_id"],
                "knowledge_base_id": image_data["knowledge_base_id"],
                "category_id": image_data.get("category_id"),
                "image_path": image_data["image_path"],
                "page_number": image_data.get("page_number"),
                "coordinates": image_data.get("coordinates"),
                "width": image_data.get("width"),
                "height": image_data.get("height"),
                "image_type": image_data.get("image_type", "unknown"),
                "ocr_text": image_data.get("ocr_text", ""),
                "description": image_data.get("description", ""),
                "feature_tags": image_data.get("feature_tags", []),
                "image_vector": image_data["image_vector"],
                "created_at": image_data.get("created_at"),
                "updated_at": image_data.get("updated_at"),
                "metadata": json.dumps(image_data.get("metadata", {})),
                "processing_status": image_data.get("processing_status", "completed"),
                "model_version": image_data.get("model_version", "1.0"),
            },
            refresh="wait_for",
        )
        or True
    
    async def search_document_vectors(
        self,
        query_vector: List[float],
        similarity_threshold: float = 0.7,
        limit: int = 10,
        knowledge_base_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """搜索文档向量 - 根据设计文档实现"""
        try:
            logger.info(f"开始文档向量搜索，相似度阈值: {similarity_threshold}")
            
            # 构建搜索查询
            query = {
                "knn": {
                    "field": "content_vector",
                    "query_vector": query_vector,
                    "k": limit,
                    "num_candidates": limit * 2
                }
            }
            
            # 添加知识库过滤
            if knowledge_base_id:
                query["knn"]["filter"] = {
                    "term": {
                        "knowledge_base_id": knowledge_base_id
                    }
                }
            
            # 执行搜索
            response = self.client.search(
                index=self.document_index,
                body={"query": query},
                size=limit
            )
            
            # 处理搜索结果
            results = []
            for hit in response["hits"]["hits"]:
                if hit["_score"] >= similarity_threshold:
                    result = {
                        "chunk_id": hit["_source"]["chunk_id"],
                        "document_id": hit["_source"]["document_id"],
                        "knowledge_base_id": hit["_source"]["knowledge_base_id"],
                        "content": hit["_source"]["content"],
                        "similarity_score": hit["_score"],
                        "chunk_type": hit["_source"].get("chunk_type"),
                        "image_info": hit["_source"].get("image_info")
                    }
                    results.append(result)
            
            logger.info(f"文档向量搜索完成，找到 {len(results)} 个结果")
            return results
            
        except Exception as e:
            logger.error(f"文档向量搜索失败: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.OPENSEARCH_SEARCH_FAILED,
                message=f"文档向量搜索失败: {str(e)}"
            )
    
    async def search_image_vectors(
        self,
        query_vector: List[float],
        similarity_threshold: float = 0.7,
        limit: int = 10,
        knowledge_base_id: Optional[int] = None,
        exclude_image_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """搜索图片向量 - 根据设计文档实现"""
        try:
            logger.info(f"开始图片向量搜索，相似度阈值: {similarity_threshold}")
            
            # 构建搜索查询
            query = {
                "knn": {
                    "field": "image_vector",
                    "query_vector": query_vector,
                    "k": limit,
                    "num_candidates": limit * 2
                }
            }
            
            # 添加过滤条件
            filters = []
            if knowledge_base_id:
                filters.append({"term": {"knowledge_base_id": knowledge_base_id}})
            if exclude_image_id:
                filters.append({"bool": {"must_not": {"term": {"image_id": exclude_image_id}}}})
            
            if filters:
                query["knn"]["filter"] = {"bool": {"must": filters}}
            
            # 执行搜索
            response = self.client.search(
                index=self.image_index,
                body={"query": query},
                size=limit
            )
            
            # 处理搜索结果
            results = []
            for hit in response["hits"]["hits"]:
                if hit["_score"] >= similarity_threshold:
                    result = {
                        "image_id": hit["_source"]["image_id"],
                        "document_id": hit["_source"]["document_id"],
                        "knowledge_base_id": hit["_source"]["knowledge_base_id"],
                        "image_path": hit["_source"]["image_path"],
                        "similarity_score": hit["_score"],
                        "image_type": hit["_source"].get("image_type"),
                        "page_number": hit["_source"].get("page_number"),
                        "coordinates": hit["_source"].get("coordinates"),
                        "ocr_text": hit["_source"].get("ocr_text", ""),
                        "description": hit["_source"].get("description", ""),
                        "source_document": hit["_source"].get("document_id")  # TODO: 获取文档名称
                    }
                    results.append(result)
            
            logger.info(f"图片向量搜索完成，找到 {len(results)} 个结果")
            return results
            
        except Exception as e:
            logger.error(f"图片向量搜索失败: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.OPENSEARCH_SEARCH_FAILED,
                message=f"图片向量搜索失败: {str(e)}"
            )
    
    async def search_image_keywords(
        self,
        query_text: str,
        limit: int = 10,
        knowledge_base_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """搜索图片关键词 - 根据设计文档实现"""
        try:
            logger.info(f"开始图片关键词搜索: {query_text}")
            
            # 构建搜索查询
            query = {
                "bool": {
                    "should": [
                        {
                            "match": {
                                "ocr_text": {
                                    "query": query_text,
                                    "boost": 2.0
                                }
                            }
                        },
                        {
                            "match": {
                                "description": {
                                    "query": query_text,
                                    "boost": 1.5
                                }
                            }
                        },
                        {
                            "match": {
                                "feature_tags": {
                                    "query": query_text,
                                    "boost": 1.0
                                }
                            }
                        }
                    ],
                    "minimum_should_match": 1
                }
            }
            
            # 添加知识库过滤
            if knowledge_base_id:
                query["bool"]["filter"] = [
                    {"term": {"knowledge_base_id": knowledge_base_id}}
                ]
            
            # 执行搜索
            response = self.client.search(
                index=self.image_index,
                body={"query": query},
                size=limit
            )
            
            # 处理搜索结果
            results = []
            for hit in response["hits"]["hits"]:
                result = {
                    "image_id": hit["_source"]["image_id"],
                    "document_id": hit["_source"]["document_id"],
                    "knowledge_base_id": hit["_source"]["knowledge_base_id"],
                    "image_path": hit["_source"]["image_path"],
                    "keyword_score": hit["_score"],
                    "image_type": hit["_source"].get("image_type"),
                    "page_number": hit["_source"].get("page_number"),
                    "coordinates": hit["_source"].get("coordinates"),
                    "ocr_text": hit["_source"].get("ocr_text", ""),
                    "description": hit["_source"].get("description", ""),
                    "source_document": hit["_source"].get("document_id")
                }
                results.append(result)
            
            logger.info(f"图片关键词搜索完成，找到 {len(results)} 个结果")
            return results
            
        except Exception as e:
            logger.error(f"图片关键词搜索失败: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.OPENSEARCH_SEARCH_FAILED,
                message=f"图片关键词搜索失败: {str(e)}"
            )
    
    async def get_image_vector(self, image_id: int) -> Optional[List[float]]:
        """获取图片向量"""
        try:
            response = self.client.get(
                index=self.image_index,
                id=f"image_{image_id}"
            )
            
            return response["_source"].get("image_vector")
            
        except Exception as e:
            logger.error(f"获取图片向量失败: {e}")
            return None
    
    async def get_image_vector_info(self, image_id: int) -> Dict[str, Any]:
        """获取图片向量信息"""
        try:
            response = self.client.get(
                index=self.image_index,
                id=f"image_{image_id}"
            )
            
            source = response["_source"]
            return {
                "dimension": len(source.get("image_vector", [])),
                "model": source.get("model_version", "1.0"),
                "version": source.get("model_version", "1.0"),
                "created_at": source.get("created_at"),
                "updated_at": source.get("updated_at")
            }
            
        except Exception as e:
            logger.error(f"获取图片向量信息失败: {e}")
            return {}
    
    async def delete_document_chunk(self, chunk_id: int) -> bool:
        """删除文档分块索引"""
        try:
            self.client.delete(
                index=self.document_index,
                id=f"chunk_{chunk_id}"
            )
            return True
        except Exception as e:
            logger.error(f"删除文档分块索引失败: {e}")
            return False
    
    async def delete_image(self, image_id: int) -> bool:
        """删除图片索引"""
        try:
            self.client.delete(
                index=self.image_index,
                id=f"image_{image_id}"
            )
            return True
        except Exception as e:
            logger.error(f"删除图片索引失败: {e}")
            return False
