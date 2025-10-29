"""
QA Service
根据知识问答系统设计文档实现问答服务
"""

import asyncio
import uuid
from typing import Dict, List, Optional, Any, AsyncGenerator
from datetime import datetime
from sqlalchemy.orm import Session

from app.core.logging import logger
from app.config.settings import settings
from app.models.qa_session import QASession
from app.models.qa_question import QAQuestion, QAStatistics
from app.services.opensearch_service import OpenSearchService
from app.services.ollama_service import OllamaService
from app.services.multimodal_processing_service import MultimodalProcessingService
from app.services.fallback_strategy_service import FallbackStrategyService
from app.services.qa_history_service import QAHistoryService
from app.schemas.qa import (
    QASessionCreate, QASessionResponse, QASessionListResponse,
    QAMultimodalQuestionResponse, QAImageSearchResponse,
    QASessionConfigUpdate
)
from app.core.exceptions import CustomException, ErrorCode

class QAService:
    """问答服务 - 根据设计文档实现"""
    
    def __init__(self, db: Session):
        self.db = db
        self.opensearch_service = OpenSearchService()
        self.ollama_service = OllamaService()
        self.multimodal_service = MultimodalProcessingService(db)
        self.fallback_service = FallbackStrategyService(db)
        self.history_service = QAHistoryService(db)
    
    # 1. 知识库选择功能
    
    def get_knowledge_bases(
        self,
        category_id: Optional[int] = None,
        status: str = "active",
        page: int = 1,
        size: int = 20
    ) -> QASessionListResponse:
        """获取知识库列表 - 根据设计文档实现"""
        try:
            logger.info(f"获取知识库列表，分类ID: {category_id}, 状态: {status}")
            
            # 从MySQL数据库获取知识库列表
            from app.models.knowledge_base import KnowledgeBase
            query = self.db.query(KnowledgeBase)
            
            if category_id:
                query = query.filter(KnowledgeBase.category_id == category_id)
            query = query.filter(KnowledgeBase.status == status)
            
            db_kbs = query.offset((page - 1) * size).limit(size).all()
            
            knowledge_bases = [
                {
                    "id": kb.id,
                    "name": kb.name,
                    "description": kb.description,
                    "category_id": kb.category_id,
                    "category_name": getattr(kb, 'category_name', ''),
                    "document_count": 0,  # TODO: 统计文档数量
                    "storage_size": 0,  # TODO: 统计存储大小
                    "tags": [],  # TODO: 获取标签
                    "status": kb.status,
                    "created_at": kb.created_at
                }
                for kb in db_kbs
            ]
            
            # 临时模拟数据（用于测试）
            """knowledge_bases = [
                {
                    "id": 1,
                    "name": "技术文档知识库",
                    "description": "包含技术文档和API说明",
                    "category_id": 1,
                    "category_name": "技术",
                    "document_count": 150,
                    "storage_size": 1024000,
                    "tags": ["技术", "API", "文档"],
                    "status": "active",
                    "created_at": datetime.now()
                },
                {
                    "id": 2,
                    "name": "产品手册知识库",
                    "description": "包含产品使用手册和说明",
                    "category_id": 2,
                    "category_name": "产品",
                    "document_count": 80,
                    "storage_size": 512000,
                    "tags": ["产品", "手册", "使用"],
                    "status": "active",
                    "created_at": datetime.now()
                }
            ]"""
            
            # 过滤和分页
            filtered_bases = knowledge_bases
            if category_id:
                filtered_bases = [kb for kb in filtered_bases if kb["category_id"] == category_id]
            
            start_idx = (page - 1) * size
            end_idx = start_idx + size
            paginated_bases = filtered_bases[start_idx:end_idx]
            
            return QASessionListResponse(
                knowledge_bases=paginated_bases,
                pagination={
                    "page": page,
                    "size": size,
                    "total": len(filtered_bases),
                    "total_pages": (len(filtered_bases) + size - 1) // size
                }
            )
            
        except Exception as e:
            logger.error(f"获取知识库列表失败: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.KNOWLEDGE_BASE_QUERY_FAILED,
                message=f"获取知识库列表失败: {str(e)}"
            )
    
    def get_knowledge_base_detail(self, kb_id: int) -> Optional[QASessionResponse]:
        """获取知识库详情 - 根据设计文档实现"""
        try:
            logger.info(f"获取知识库详情，ID: {kb_id}")
            
            # 从MySQL数据库获取知识库详情
            from app.models.knowledge_base import KnowledgeBase
            
            kb = self.db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
            
            if not kb:
                return None
            
            kb_detail = {
                "id": kb_id,
                "name": f"知识库{kb_id}",
                "description": kb.description,
                "category_id": kb.category_id,
                "category_name": getattr(kb, 'category_name', ''),
                "document_count": 0,  # TODO: 统计文档数量
                "storage_size": 0,  # TODO: 统计存储大小
                "tags": [],  # TODO: 获取标签
                "status": kb.status,
                "created_at": kb.created_at
            }
            
            return kb_detail
            
        except Exception as e:
            logger.error(f"获取知识库详情失败: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.KNOWLEDGE_BASE_DETAIL_FAILED,
                message=f"获取知识库详情失败: {str(e)}"
            )
    
    # 2. 会话管理功能
    
    def create_qa_session(self, session_data: QASessionCreate) -> QASessionResponse:
        """创建问答会话 - 根据设计文档实现，使用MySQL持久化"""
        try:
            logger.info(f"创建问答会话，知识库ID: {session_data.knowledge_base_id}")
            
            # 生成会话ID
            session_id = str(uuid.uuid4())
            
            # 创建会话记录
            db_session = QASession(
                session_id=session_id,
                session_name=session_data.session_name,
                knowledge_base_id=session_data.knowledge_base_id,
                query_method=session_data.search_type,
                search_config={
                    "max_sources": session_data.max_sources,
                    "similarity_threshold": session_data.similarity_threshold
                },
                llm_config={
                    "model": session_data.llm_model,
                    "temperature": session_data.temperature
                },
                question_count=0,
                status="active",
                last_activity_time=datetime.now()
            )
            
            self.db.add(db_session)
            self.db.commit()
            self.db.refresh(db_session)
            
            logger.info(f"问答会话创建成功，会话ID: {session_id}")
            
            return self._session_to_dict(db_session)
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"创建问答会话失败: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.SESSION_CREATE_FAILED,
                message=f"创建问答会话失败: {str(e)}"
            )
    
    def get_qa_sessions(
        self,
        page: int = 1,
        size: int = 20,
        knowledge_base_id: Optional[int] = None
    ) -> QASessionListResponse:
        """获取会话列表 - 根据设计文档实现，使用MySQL"""
        try:
            logger.info(f"获取会话列表，页码: {page}, 大小: {size}")
            
            # 查询会话
            query = self.db.query(QASession)
            
            if knowledge_base_id:
                query = query.filter(QASession.knowledge_base_id == knowledge_base_id)
            
            query = query.filter(QASession.status == "active")
            
            # 总数
            total = query.count()
            
            # 分页
            sessions = query.offset((page - 1) * size).limit(size).all()
            
            session_list = [self._session_to_dict(s) for s in sessions]
            
            return QASessionListResponse(
                sessions=session_list,
                pagination={
                    "page": page,
                    "size": size,
                    "total": total,
                    "total_pages": (total + size - 1) // size
                }
            )
            
        except Exception as e:
            logger.error(f"获取会话列表失败: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.SESSION_QUERY_FAILED,
                message=f"获取会话列表失败: {str(e)}"
            )
    
    def get_qa_session_detail(self, session_id: str) -> Optional[QASessionResponse]:
        """获取会话详情 - 根据设计文档实现，使用MySQL"""
        try:
            logger.info(f"获取会话详情，会话ID: {session_id}")
            
            # 查询会话
            db_session = self.db.query(QASession).filter(
                QASession.session_id == session_id,
                QASession.status == "active"
            ).first()
            
            if not db_session:
                return None
            
            session_dict = self._session_to_dict(db_session)
            
            # 获取问题列表
            questions = self.db.query(QAQuestion).filter(
                QAQuestion.session_id == session_id
            ).order_by(QAQuestion.created_at.desc()).limit(10).all()
            
            session_dict["questions"] = [
                {
                    "question_id": q.question_id,
                    "question_content": q.question_content,
                    "answer_content": q.answer_content,
                    "created_at": q.created_at.isoformat() if q.created_at else None,
                    "similarity_score": q.similarity_score,
                    "answer_quality": q.answer_quality
                }
                for q in questions
            ]
            
            return session_dict
            
        except Exception as e:
            logger.error(f"获取会话详情失败: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.SESSION_DETAIL_FAILED,
                message=f"获取会话详情失败: {str(e)}"
            )
    
    def delete_qa_session(self, session_id: str) -> bool:
        """删除会话 - 根据设计文档实现，使用MySQL"""
        try:
            logger.info(f"删除会话，会话ID: {session_id}")
            
            # 查询会话
            db_session = self.db.query(QASession).filter(
                QASession.session_id == session_id
            ).first()
            
            if not db_session:
                return False
            
            # 软删除
            db_session.status = "deleted"
            self.db.commit()
            
            logger.info(f"会话删除成功，会话ID: {session_id}")
            return True
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"删除会话失败: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.SESSION_DELETE_FAILED,
                message=f"删除会话失败: {str(e)}"
            )
    
    def update_session_config(
        self,
        session_id: str,
        config_update: QASessionConfigUpdate
    ) -> Optional[QASessionResponse]:
        """更新会话配置 - 根据设计文档实现，使用MySQL"""
        try:
            logger.info(f"更新会话配置，会话ID: {session_id}")
            
            # 查询会话
            db_session = self.db.query(QASession).filter(
                QASession.session_id == session_id,
                QASession.status == "active"
            ).first()
            
            if not db_session:
                return None
            
            # 更新配置
            if config_update.search_type:
                db_session.query_method = config_update.search_type
            if config_update.max_sources:
                search_config = db_session.search_config or {}
                search_config["max_sources"] = config_update.max_sources
                db_session.search_config = search_config
            if config_update.similarity_threshold:
                search_config = db_session.search_config or {}
                search_config["similarity_threshold"] = config_update.similarity_threshold
                db_session.search_config = search_config
            if config_update.llm_model:
                llm_config = db_session.llm_config or {}
                llm_config["model"] = config_update.llm_model
                db_session.llm_config = llm_config
            if config_update.temperature:
                llm_config = db_session.llm_config or {}
                llm_config["temperature"] = config_update.temperature
                db_session.llm_config = llm_config
            
            self.db.commit()
            self.db.refresh(db_session)
            
            logger.info(f"会话配置更新成功，会话ID: {session_id}")
            return self._session_to_dict(db_session)
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"更新会话配置失败: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.SESSION_CONFIG_UPDATE_FAILED,
                message=f"更新会话配置失败: {str(e)}"
            )
    
    # 3. 多模态问答功能
    
    async def ask_multimodal_question(
        self,
        session_id: str,
        processed_input: Dict[str, Any],
        include_history: bool = True,
        max_history: int = 5,
        similarity_threshold: float = 0.7,
        max_sources: int = 10,
        search_type: str = "hybrid"
    ) -> QAMultimodalQuestionResponse:
        """多模态问答 - 根据设计文档实现"""
        try:
            logger.info(f"执行多模态问答，会话ID: {session_id}")
            
            # 获取会话信息 - 从MySQL数据库
            db_session = self.db.query(QASession).filter(
                QASession.session_id == session_id,
                QASession.status == "active"
            ).first()
            
            if not db_session:
                raise CustomException(
                    code=ErrorCode.SESSION_NOT_FOUND,
                    message=f"会话不存在: {session_id}"
                )
            
            session_info = self._session_to_dict(db_session)
            
            # 添加session_id到processed_input
            processed_input["session_id"] = session_id
            
            # 生成问题ID
            question_id = str(uuid.uuid4())
            
            # 构建问题内容
            question_content = self._build_question_content(processed_input)
            
            # 执行检索
            search_results = await self._perform_search(
                question_content, processed_input, search_type, max_sources
            )
            
            # 降级策略处理
            fallback_result = await self.fallback_service.evaluate_relevance_and_decide_strategy(
                search_results, question_content, processed_input
            )
            
            # 生成答案
            answer_content = fallback_result["processing_result"]["answer"]
            answer_type = fallback_result["processing_result"]["answer_type"]
            confidence = fallback_result["processing_result"]["confidence"]
            citations = fallback_result["processing_result"]["citations"]
            
            # 构建来源信息
            source_info = self._build_source_info(citations)
            
            # 构建处理信息
            processing_info = {
                "input_type": processed_input["input_type"],
                "search_type": search_type,
                "similarity_threshold": similarity_threshold,
                "max_sources": max_sources,
                "processing_steps": processed_input["processing_steps"],
                "fallback_strategy": fallback_result["strategy"]
            }
            
            # 构建质量评估
            quality_assessment = {
                "overall_score": fallback_result["relevance_score"],
                "relevance_level": fallback_result["relevance_level"],
                "confidence": confidence,
                "answer_length": len(answer_content),
                "source_count": len(citations)
            }
            
            # 存储历史记录
            await self.history_service.store_qa_history(
                question_id=question_id,
                session_id=session_id,
                user_id="user",  # TODO: 从认证信息获取
                knowledge_base_id=session_info["knowledge_base_id"],
                question_content=question_content,
                answer_content=answer_content,
                source_info=source_info,
                processing_info=processing_info,
                quality_assessment=quality_assessment
            )
            
            # 更新会话信息 - 更新MySQL数据库
            db_session = self.db.query(QASession).filter(QASession.session_id == session_id).first()
            if db_session:
                db_session.question_count += 1
                db_session.last_question = question_content[:100]
                db_session.last_activity_time = datetime.now()
                self.db.commit()
                self.db.refresh(db_session)
            
            # 构建响应
            response = QAMultimodalQuestionResponse(
                question_id=question_id,
                input_type=processed_input["input_type"],
                answer_content=answer_content,
                answer_type=answer_type,
                confidence=confidence,
                source_info=source_info,
                processing_info=processing_info,
                image_info=processed_input.get("image_data"),
                created_at=datetime.now()
            )
            
            logger.info(f"多模态问答完成，问题ID: {question_id}")
            return response
            
        except Exception as e:
            logger.error(f"多模态问答失败: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.MULTIMODAL_QA_FAILED,
                message=f"多模态问答失败: {str(e)}"
            )
    
    # 4. 图片搜索功能
    
    async def search_images(
        self,
        session_id: str,
        processed_image: Dict[str, Any],
        search_type: str = "image-to-image",
        similarity_threshold: float = 0.7,
        max_results: int = 10,
        knowledge_base_id: Optional[int] = None
    ) -> QAImageSearchResponse:
        """图片搜索 - 根据设计文档实现"""
        try:
            logger.info(f"执行图片搜索，会话ID: {session_id}, 搜索类型: {search_type}")
            
            # 获取会话信息 - 从MySQL数据库
            db_session = self.db.query(QASession).filter(
                QASession.session_id == session_id,
                QASession.status == "active"
            ).first()
            
            if not db_session:
                raise CustomException(
                    code=ErrorCode.SESSION_NOT_FOUND,
                    message=f"会话不存在: {session_id}"
                )
            
            session_info = self._session_to_dict(db_session)
            
            # 执行图片搜索
            if search_type == "image-to-image":
                results = await self._search_similar_images(
                    processed_image, similarity_threshold, max_results, knowledge_base_id
                )
            elif search_type == "text-to-image":
                results = await self._search_images_by_text(
                    processed_image, similarity_threshold, max_results, knowledge_base_id
                )
            else:
                raise CustomException(
                    code=ErrorCode.INVALID_SEARCH_TYPE,
                    message=f"无效的搜索类型: {search_type}"
                )
            
            # 构建响应
            response = QAImageSearchResponse(
                search_type=search_type,
                results=results,
                results_count=len(results),
                search_time=0.5,  # TODO: 实际计算搜索时间
                similarity_threshold=similarity_threshold
            )
            
            logger.info(f"图片搜索完成，找到 {len(results)} 个结果")
            return response
            
        except Exception as e:
            logger.error(f"图片搜索失败: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.IMAGE_SEARCH_FAILED,
                message=f"图片搜索失败: {str(e)}"
            )
    
    # 5. 流式问答功能
    
    async def stream_answer(
        self,
        session_id: str,
        question_data: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """流式问答 - 根据设计文档实现"""
        try:
            logger.info(f"开始流式问答，会话ID: {session_id}")
            
            # 获取会话信息 - 从MySQL数据库
            db_session = self.db.query(QASession).filter(
                QASession.session_id == session_id,
                QASession.status == "active"
            ).first()
            
            if not db_session:
                yield {
                    "type": "error",
                    "data": {"message": f"会话不存在: {session_id}"}
                }
                return
            
            session_info = self._session_to_dict(db_session)
            
            # 构建问题内容
            question_content = question_data.get("text_content", "")
            
            # 执行检索
            search_results = await self._perform_search(
                question_content, {}, "hybrid", 10
            )
            
            # 生成流式答案
            async for chunk in self._generate_streaming_answer(
                question_content, search_results
            ):
                yield chunk
            
        except Exception as e:
            logger.error(f"流式问答失败: {e}", exc_info=True)
            yield {
                "type": "error",
                "data": {"message": str(e)}
            }
    
    # 辅助方法实现
    
    def _build_question_content(self, processed_input: Dict[str, Any]) -> str:
        """构建问题内容"""
        if processed_input["input_type"] == "text":
            return processed_input["text_data"]["cleaned_text"]
        elif processed_input["input_type"] == "image":
            return processed_input["image_data"]["content_understanding"]["description"]
        elif processed_input["input_type"] == "multimodal":
            text_content = processed_input["text_data"]["cleaned_text"]
            image_description = processed_input["image_data"]["content_understanding"]["description"]
            return f"{text_content} [图片描述: {image_description}]"
        else:
            return "未知输入类型"
    
    async def _perform_search(
        self,
        question_content: str,
        processed_input: Dict[str, Any],
        search_type: str,
        max_sources: int
    ) -> List[Dict[str, Any]]:
        """执行检索"""
        try:
            # 实现实际的检索逻辑 - 使用OpenSearch
            from app.services.vector_service import VectorService
            
            # 1. 生成问题向量
            vector_service = VectorService(self.db)
            question_vector = vector_service.generate_embedding(question_content)
            
            # 2. 从会话获取知识库ID
            db_session = self.db.query(QASession).filter(QASession.session_id == processed_input.get("session_id")).first()
            kb_id = db_session.knowledge_base_id if db_session else None
            
            # 3. 执行向量搜索
            results = await self.opensearch_service.search_document_vectors(
                query_vector=question_vector,
                similarity_threshold=0.7,
                limit=max_sources,
                knowledge_base_id=kb_id
            )
            
            # 转换结果格式
            formatted_results = []
            for hit in results:
                formatted_results.append({
                    "content": hit.get("_source", {}).get("content", ""),
                    "similarity_score": hit.get("_score", 0),
                    "document_id": hit.get("_source", {}).get("document_id", ""),
                    "document_title": hit.get("_source", {}).get("document_title", ""),
                    "knowledge_base_name": hit.get("_source", {}).get("knowledge_base_name", ""),
                    "chunk_index": hit.get("_source", {}).get("chunk_index", 0),
                    "page_number": hit.get("_source", {}).get("page_number", 0),
                    "url_link": hit.get("_source", {}).get("url_link", "")
                })
            
            return formatted_results
            
            # 备用模拟数据（当OpenSearch不可用时）
            """mock_results = [
                {
                    "content": f"这是关于'{question_content}'的相关内容片段1",
                    "similarity_score": 0.85,
                    "document_id": "doc1",
                    "document_title": "相关文档1",
                    "knowledge_base_name": "技术文档知识库",
                    "chunk_index": 1,
                    "page_number": 1,
                    "url_link": "http://example.com/doc1"
                },
                {
                    "content": f"这是关于'{question_content}'的相关内容片段2",
                    "similarity_score": 0.78,
                    "document_id": "doc2",
                    "document_title": "相关文档2",
                    "knowledge_base_name": "技术文档知识库",
                    "chunk_index": 2,
                    "page_number": 1,
                    "url_link": "http://example.com/doc2"
                }
            ]
            
            return mock_results[:max_sources]"""
            
        except Exception as e:
            logger.error(f"执行检索失败: {e}")
            return []
    
    def _build_source_info(self, citations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """构建来源信息"""
        source_info = []
        for i, citation in enumerate(citations):
            source_info.append({
                "document_id": citation.get("document_id", f"doc{i+1}"),
                "document_title": citation.get("document_title", f"文档{i+1}"),
                "knowledge_base_name": citation.get("knowledge_base_name", "知识库"),
                "content_snippet": citation.get("content_snippet", ""),
                "similarity_score": citation.get("similarity_score", 0.0),
                "position_info": citation.get("position_info", {})
            })
        return source_info
    
    async def _search_similar_images(
        self,
        processed_image: Dict[str, Any],
        similarity_threshold: float,
        max_results: int,
        knowledge_base_id: Optional[int]
    ) -> List[Dict[str, Any]]:
        """搜索相似图片"""
        try:
            # 实现实际的图片相似度搜索 - 使用ImageSearchService
            from app.services.image_search_service import ImageSearchService
            
            image_search_service = ImageSearchService()
            
            # 提取图片向量
            image_vector = processed_image.get("image_vector", [])
            
            if not image_vector:
                # 如果没有向量，返回空结果
                return []
            
            # 使用OpenSearch搜索相似图片
            results = await self.opensearch_service.search_image_vectors(
                query_vector=image_vector,
                similarity_threshold=similarity_threshold,
                limit=max_results,
                knowledge_base_id=knowledge_base_id
            )
            
            # 转换结果格式
            formatted_results = []
            for hit in results:
                formatted_results.append({
                    "image_id": hit.get("_source", {}).get("image_id", ""),
                    "image_path": hit.get("_source", {}).get("image_path", ""),
                    "similarity_score": hit.get("_score", 0),
                    "image_info": hit.get("_source", {}).get("image_info", {}),
                    "source_document": hit.get("_source", {}).get("source_document", {}),
                    "context_info": hit.get("_source", {}).get("context_info", {})
                })
            
            return formatted_results
            
            # 备用模拟数据
            """mock_results = [
                {
                    "image_id": "img1",
                    "image_path": "/images/similar1.jpg",
                    "similarity_score": 0.85,
                    "image_info": {
                        "width": 800,
                        "height": 600,
                        "format": "JPEG"
                    },
                    "source_document": {
                        "document_id": "doc1",
                        "document_title": "包含相似图片的文档1"
                    },
                    "context_info": {
                        "surrounding_text": "这是图片周围的文本内容"
                    }
                }
            ]
            
            return mock_results[:max_results]"""
            
        except Exception as e:
            logger.error(f"搜索相似图片失败: {e}", exc_info=True)
            return []
    
    async def _search_images_by_text(
        self,
        processed_image: Dict[str, Any],
        similarity_threshold: float,
        max_results: int,
        knowledge_base_id: Optional[int]
    ) -> List[Dict[str, Any]]:
        """基于文本搜索图片"""
        try:
            # 实现实际的文本搜索图片 - 使用ImageSearchService
            from app.services.image_search_service import ImageSearchService
            
            image_search_service = ImageSearchService()
            
            # 1. 提取搜索文本
            search_text = processed_image.get("search_text", "")
            
            if not search_text:
                return []
            
            # 2. 生成文本向量
            from app.services.vector_service import VectorService
            vector_service = VectorService(self.db)
            text_vector = vector_service.generate_embedding(search_text)
            
            # 3. 搜索图片
            results = await self.opensearch_service.search_image_vectors(
                query_vector=text_vector,
                similarity_threshold=similarity_threshold,
                limit=max_results,
                knowledge_base_id=knowledge_base_id
            )
            
            # 4. 转换结果格式
            formatted_results = []
            for hit in results:
                formatted_results.append({
                    "image_id": hit.get("_source", {}).get("image_id", ""),
                    "image_path": hit.get("_source", {}).get("image_path", ""),
                    "similarity_score": hit.get("_score", 0),
                    "image_info": hit.get("_source", {}).get("image_info", {}),
                    "source_document": hit.get("_source", {}).get("source_document", {}),
                    "context_info": hit.get("_source", {}).get("context_info", {})
                })
            
            return formatted_results
            
            # 备用模拟数据
            """mock_results = [
                {
                    "image_id": "img2",
                    "image_path": "/images/text_match1.jpg",
                    "similarity_score": 0.78,
                    "image_info": {
                        "width": 1024,
                        "height": 768,
                        "format": "PNG"
                    },
                    "source_document": {
                        "document_id": "doc2",
                        "document_title": "包含匹配图片的文档2"
                    },
                    "context_info": {
                        "surrounding_text": "这是匹配图片的文本描述"
                    }
                }
            ]
            
            return mock_results[:max_results]"""
            
        except Exception as e:
            logger.error(f"基于文本搜索图片失败: {e}", exc_info=True)
            return []
    
    async def _generate_streaming_answer(
        self,
        question_content: str,
        search_results: List[Dict[str, Any]]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """生成流式答案"""
        try:
            # 构建上下文
            context = self._build_knowledge_context(search_results)
            
            # 生成答案提示
            prompt = f"""基于以下知识库内容回答用户问题：

知识库内容：
{context}

用户问题：{question_content}

请基于知识库内容提供准确、详细的回答。"""

            # 模拟流式生成
            answer_chunks = [
                "根据知识库内容，",
                "我可以为您提供以下信息：",
                "\n\n1. 首先，",
                "这个问题涉及到多个方面。",
                "\n\n2. 其次，",
                "需要特别注意以下几点。",
                "\n\n3. 最后，",
                "建议您参考相关文档获取更多详细信息。"
            ]
            
            for chunk in answer_chunks:
                yield {
                    "type": "content_chunk",
                    "data": {
                        "content": chunk,
                        "timestamp": datetime.now().isoformat()
                    }
                }
                await asyncio.sleep(0.1)  # 模拟生成延迟
            
        except Exception as e:
            logger.error(f"生成流式答案失败: {e}")
            yield {
                "type": "error",
                "data": {"message": str(e)}
            }
    
    def _build_knowledge_context(self, search_results: List[Dict[str, Any]]) -> str:
        """构建知识库上下文"""
        context_parts = []
        for i, result in enumerate(search_results[:5]):
            context_parts.append(f"[来源{i+1}]\n{result['content']}\n")
        return "\n".join(context_parts)
    
    def _session_to_dict(self, session: QASession) -> dict:
        """将QASession对象转换为字典"""
        return {
            "session_id": session.session_id,
            "session_name": session.session_name,
            "knowledge_base_id": session.knowledge_base_id,
            "knowledge_base_name": f"知识库{session.knowledge_base_id}",
            "search_config": session.search_config or {},
            "llm_config": session.llm_config or {},
            "question_count": session.question_count,
            "last_question": session.last_question,
            "last_activity": session.last_activity_time.isoformat() if session.last_activity_time else None,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "status": session.status
        }