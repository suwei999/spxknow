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
from app.services.qa_history_service import QAHistoryService
from app.services.search_service import SearchService
from app.schemas.search import SearchRequest
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
        self.ollama_service = OllamaService(db)
        self.multimodal_service = MultimodalProcessingService(db)
        self.history_service = QAHistoryService(db)
        self.search_service = SearchService(db)
    
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
            # 使用布尔字段 is_active 映射到状态
            if status in ("active", "inactive"):
                is_active_flag = True if status == "active" else False
                query = query.filter(KnowledgeBase.is_active == is_active_flag)
            
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
                    "status": "active" if getattr(kb, 'is_active', False) else "inactive",
                    "is_active": bool(getattr(kb, 'is_active', False)),
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

            # 校验名称
            name = (session_data.session_name or "").strip()
            if not name:
                raise CustomException(
                    code=ErrorCode.VALIDATION_ERROR,
                    message="会话名称不能为空"
                )
            # 唯一性：全局唯一（无用户体系）
            exists = self.db.query(QASession).filter(
                QASession.session_name == name,
                QASession.status == "active"
            ).first()
            if exists:
                raise CustomException(
                    code=ErrorCode.VALIDATION_ERROR,
                    message="会话名称已存在，请更换名称"
                )
            
            # 生成会话ID
            session_id = str(uuid.uuid4())
            
            # 创建会话记录
            db_session = QASession(
                session_id=session_id,
                session_name=name,
                knowledge_base_id=session_data.knowledge_base_id,
                query_method=session_data.search_type,
                search_config={
                    "max_sources": session_data.max_sources,
                    "similarity_threshold": session_data.similarity_threshold,
                    "search_type": session_data.search_type
                },
                llm_config={},
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
            ).order_by(QAQuestion.created_at.desc()).limit(settings.QA_DEFAULT_MAX_RESULTS).all()
            
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
                search_config = db_session.search_config or {}
                search_config["search_type"] = config_update.search_type
                db_session.search_config = search_config
            if config_update.max_sources:
                search_config = db_session.search_config or {}
                search_config["max_sources"] = config_update.max_sources
                db_session.search_config = search_config
            if config_update.similarity_threshold:
                search_config = db_session.search_config or {}
                search_config["similarity_threshold"] = config_update.similarity_threshold
                db_session.search_config = search_config
            
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
        max_history: int = settings.QA_DEFAULT_MAX_HISTORY,
        similarity_threshold: float = settings.SEARCH_VECTOR_THRESHOLD,
        max_sources: int = settings.QA_DEFAULT_MAX_SOURCES,
        search_type: str = "hybrid"
    ) -> QAMultimodalQuestionResponse:
        """多模态问答 - 根据设计文档实现"""
        try:
            logger.info(
                "[QA] exec multimodal QA session=%s input_type=%s search_type=%s "
                "threshold=%s max_sources=%s include_history=%s max_history=%s text_len=%s image=%s",
                session_id,
                processed_input.get("input_type"),
                search_type,
                similarity_threshold,
                max_sources,
                include_history,
                max_history,
                len((processed_input.get("text_data") or {}).get("cleaned_text", "")) if processed_input else 0,
                "yes" if processed_input.get("image_data") else "no"
            )
            
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
            session_search_config = (db_session.search_config or {}) if db_session else {}
            search_results = await self._perform_search(
                question_content,
                processed_input,
                search_type,
                max_sources,
                similarity_threshold=similarity_threshold,
                min_rerank_score=session_search_config.get("min_rerank_score") if isinstance(session_search_config, dict) else None
            )
            
            # 降级策略处理
            answer_type = "knowledge_base"
            confidence = 0.85
            citations = self._build_citations_from_results(search_results)

            kb_context = self._build_knowledge_context(search_results)
            # 如果检索为空，仍尝试调用模型回答
            if not kb_context.strip():
                answer_type = "llm_only"
                confidence = 0.5
                llm_model = session_info.get("llm_config", {}).get("model") or settings.OLLAMA_MODEL
                raw_answer = await self.ollama_service.chat_completion(
                    [
                        {"role": "system", "content": "你是企业知识库问答助手，请尽可能给出准确、可靠的答案。"},
                        {"role": "user", "content": question_content}
                    ],
                    model=llm_model
                ) or ""
                answer_content = self._post_process_llm_answer(raw_answer)
            else:
                llm_model = session_info.get("llm_config", {}).get("model") or settings.OLLAMA_MODEL
                raw_answer = await self.ollama_service.generate_text(
                    self._build_kb_prompt(question_content, kb_context),
                    model=llm_model
                ) or ""
                answer_content = self._post_process_llm_answer(raw_answer)

            if not answer_content.strip():
                answer_type = "no_info"
                confidence = 0.0
                answer_content = "抱歉，知识库中没有找到相关答案。"
                citations = []
            
            # 构建来源信息
            source_info = self._build_source_info(citations)
            
            # 构建处理信息
            processing_info = {
                "input_type": processed_input.get("input_type"),
                "search_type": search_type,
                "similarity_threshold": similarity_threshold,
                "max_sources": max_sources,
                "processing_steps": processed_input.get("processing_steps"),
                "answer_strategy": answer_type,
                "retrieved_count": len(search_results)
            }
            
            # 构建质量评估（基于最终回答类型）
            if answer_type == "knowledge_base":
                relevance_level = "high"
            elif answer_type == "llm_only":
                relevance_level = "medium"
            else:
                relevance_level = "none"
            quality_assessment = {
                "overall_score": confidence,
                "relevance_level": relevance_level,
                "confidence": confidence,
                "answer_length": len(answer_content),
                "source_count": len(citations)
            }
            
            # 存储历史记录到OpenSearch（暂时没有用户概念，user_id设为空字符串）
            try:
                await self.history_service.store_qa_history(
                    question_id=question_id,
                    session_id=session_id,
                    user_id="",  # 暂时没有用户概念，设为空字符串
                    knowledge_base_id=session_info["knowledge_base_id"],
                    question_content=question_content,
                    answer_content=answer_content,
                    source_info=source_info,
                    processing_info=processing_info,
                    quality_assessment=quality_assessment
                )
            except Exception as history_err:
                logger.error(
                    "[QA] store history failed question=%s session=%s err=%s",
                    question_id,
                    session_id,
                    history_err,
                    exc_info=True
                )
            
            # 存储历史记录到MySQL的QAQuestion表（用于会话详情查询）
            try:
                qa_question = QAQuestion(
                    question_id=question_id,
                    session_id=session_id,
                    question_content=question_content,
                    answer_content=answer_content,
                    similarity_score=quality_assessment.get("overall_score", 0.0),
                    answer_quality=str(quality_assessment.get("overall_score", 0.0)),  # 转换为字符串（模型字段为String类型）
                    input_type=processed_input["input_type"],
                    source_info=source_info,
                    processing_info=processing_info,
                    created_at=datetime.now()
                )
                self.db.add(qa_question)
                self.db.commit()  # 确保立即提交
                logger.info(f"问答记录已保存到MySQL，问题ID: {question_id}")
            except Exception as e:
                self.db.rollback()  # 回滚事务
                logger.error(f"保存问答记录到MySQL失败: {e}", exc_info=True)
                # 不中断流程，继续执行
            
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
                code=ErrorCode.SEARCH_FAILED,
                message=f"多模态问答失败: {str(e)}"
            )
    
    # 4. 图片搜索功能
    
    async def search_images(
        self,
        session_id: str,
        processed_image: Dict[str, Any],
        search_type: str = "image-to-image",
        similarity_threshold: float = settings.SEARCH_VECTOR_THRESHOLD,
        max_results: int = settings.QA_DEFAULT_MAX_RESULTS,
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
                search_time=0.0,  # TODO: 可按实际测量赋值
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
                question_content,
                {"session_id": session_id},
                "hybrid",
                settings.QA_DEFAULT_MAX_SOURCES,
                similarity_threshold=settings.SEARCH_VECTOR_THRESHOLD,
                min_rerank_score=None
            )
            
            # 生成流式答案
            async for chunk in self._generate_streaming_answer(
                question_content, search_results, session_info
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
        max_sources: int,
        similarity_threshold: Optional[float] = None,
        min_rerank_score: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """执行检索"""
        try:
            # 关联会话，获取知识库等信息
            session_id = processed_input.get("session_id")
            db_session = None
            if session_id:
                db_session = self.db.query(QASession).filter(QASession.session_id == session_id).first()
            kb_id = db_session.knowledge_base_id if db_session else None
            session_search_config = (db_session.search_config if db_session else {}) or {}

            # 构建搜索请求，复用 SearchService 逻辑（与搜索页保持一致）
            req = SearchRequest(
                query=question_content,
                knowledge_base_id=kb_id,
                search_type=search_type or "hybrid",
                limit=max_sources,
                similarity_threshold=similarity_threshold if similarity_threshold is not None else session_search_config.get("similarity_threshold"),
                min_rerank_score=min_rerank_score
            )
            
            results = await self.search_service.search(req)

            # SearchService 返回 SearchResponse，如果是 pydantic 对象，转换为 dict
            formatted_results = []
            from app.services.document_service import DocumentService
            from app.models.chunk import DocumentChunk
            import json
            
            doc_service = DocumentService(self.db)
            
            for hit in results:
                data = hit.dict() if hasattr(hit, "dict") else dict(hit)
                meta = data.get("metadata") or {}
                document_id = data.get("document_id")
                chunk_id = data.get("chunk_id")
                similarity_score = (
                    data.get("rerank_score")
                    or meta.get("rerank_score")
                    or data.get("score")
                    or meta.get("knn_score")
                    or meta.get("bm25_score")
                    or 0.0
                )
                
                # 查找关联图片
                associated_images = []
                if document_id and chunk_id:
                    try:
                        # 获取 chunk 对象
                        chunk = self.db.query(DocumentChunk).filter(
                            DocumentChunk.id == chunk_id
                        ).first()
                        
                        if chunk:
                            images = doc_service.get_images_for_chunk(document_id, chunk)
                            
                            # 格式化图片信息
                            for img in images:
                                img_meta = {}
                                if img.meta:
                                    try:
                                        img_meta = json.loads(img.meta) if isinstance(img.meta, str) else img.meta
                                    except:
                                        pass
                                
                                associated_images.append({
                                    "image_id": img.id,
                                    "image_path": img.image_path,
                                    "thumbnail_path": img.thumbnail_path,
                                    "image_type": img.image_type,
                                    "ocr_text": img.ocr_text or "",
                                    "page_number": img_meta.get('page_number'),
                                    "metadata": img_meta
                                })
                    except Exception as e:
                        logger.warning(f"查找文本块关联图片失败: {e}")
                
                formatted_results.append({
                    "content": data.get("content", ""),
                    "similarity_score": similarity_score,
                    "document_id": str(document_id) if document_id is not None else "",
                    "document_title": meta.get("document_title") or "",
                    "knowledge_base_name": meta.get("knowledge_base_name", ""),
                    "chunk_index": meta.get("chunk_index", 0),
                    "page_number": meta.get("page_number", 0),
                    "url_link": meta.get("url_link", ""),
                    "chunk_id": chunk_id,
                    # ✅ 新增：关联图片信息
                    "associated_images": associated_images,
                    "metadata": meta,
                    "table": data.get("table") or meta.get("table"),
                    "matrix": data.get("matrix"),
                    "cells": data.get("cells") or meta.get("cells"),
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
                "content_snippet": citation.get("content_snippet", "") or citation.get("content", ""),
                "similarity_score": citation.get("similarity_score", 0.0),
                "position_info": citation.get("position_info", {}),
                # ✅ 新增：关联图片信息（从检索结果中提取）
                "associated_images": citation.get("associated_images", [])
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
            
            # 转换结果格式，并查找上下文文本块
            formatted_results = []
            from app.services.document_service import DocumentService
            from app.services.minio_storage_service import MinioStorageService
            from app.models.image import DocumentImage
            import json
            
            for hit in results:
                image_id = hit.get("image_id") or hit.get("_source", {}).get("image_id")
                document_id = hit.get("document_id") or hit.get("_source", {}).get("document_id")
                
                # 查找上下文文本块
                context_chunks = []
                context_info = {}
                
                if document_id and image_id:
                    try:
                        # 获取图片对象
                        image = self.db.query(DocumentImage).filter(
                            DocumentImage.id == image_id
                        ).first()
                        
                        if image:
                            doc_service = DocumentService(self.db)
                            chunks = doc_service.get_chunks_for_image(document_id, image)
                            
                            # 格式化上下文文本块信息
                            minio = MinioStorageService()
                            for chunk in chunks:
                                chunk_meta = {}
                                if chunk.meta:
                                    try:
                                        chunk_meta = json.loads(chunk.meta) if isinstance(chunk.meta, str) else chunk.meta
                                    except:
                                        pass
                                
                                # 获取 chunk 内容（可能需要从 MinIO 读取）
                                chunk_content = chunk.content or ""
                                if not chunk_content:
                                    # 尝试从 MinIO 读取
                                    try:
                                        from app.models.document import Document
                                        import datetime
                                        import gzip
                                        doc = self.db.query(Document).filter(Document.id == document_id).first()
                                        if doc:
                                            created = getattr(doc, 'created_at', None) or datetime.datetime.utcnow()
                                            year = created.strftime('%Y')
                                            month = created.strftime('%m')
                                            object_name = f"documents/{year}/{month}/{document_id}/parsed/chunks/chunks.jsonl.gz"
                                            obj = minio.client.get_object(minio.bucket_name, object_name)
                                            try:
                                                with gzip.GzipFile(fileobj=obj, mode='rb') as gz:
                                                    for line in gz:
                                                        try:
                                                            item = json.loads(line.decode('utf-8'))
                                                            if item.get('index') == chunk.chunk_index or item.get('chunk_index') == chunk.chunk_index:
                                                                chunk_content = item.get('content', '')
                                                                break
                                                        except:
                                                            continue
                                            finally:
                                                try:
                                                    obj.close()
                                                    obj.release_conn()
                                                except:
                                                    pass
                                    except Exception as e:
                                        logger.debug(f"从MinIO读取chunk内容失败: {e}")
                                
                                context_chunks.append({
                                    "chunk_id": chunk.id,
                                    "chunk_index": chunk.chunk_index,
                                    "content": chunk_content[:500] if chunk_content else "",  # 限制长度
                                    "chunk_type": chunk.chunk_type or "text",
                                    "page_number": chunk_meta.get('page_number'),
                                    "metadata": chunk_meta
                                })
                            
                            # 构建上下文信息
                            context_info = {
                                "chunks": context_chunks,
                                "chunk_count": len(context_chunks),
                                "document_id": document_id
                            }
                    except Exception as e:
                        logger.warning(f"查找图片上下文文本块失败: {e}")
                
                formatted_results.append({
                    "image_id": str(image_id) if image_id else "",
                    "image_path": hit.get("image_path") or hit.get("_source", {}).get("image_path", ""),
                    "similarity_score": hit.get("_score", 0) or hit.get("similarity_score", 0),
                    "image_info": hit.get("_source", {}).get("image_info", {}),
                    "source_document": hit.get("_source", {}).get("source_document", {}),
                    # ✅ 新增：上下文文本块信息
                    "context_info": context_info
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
            
            # 4. 转换结果格式，并查找上下文文本块（复用 _search_similar_images 的逻辑）
            formatted_results = []
            from app.services.document_service import DocumentService
            from app.services.minio_storage_service import MinioStorageService
            from app.models.image import DocumentImage
            import json
            
            for hit in results:
                image_id = hit.get("image_id") or hit.get("_source", {}).get("image_id")
                document_id = hit.get("document_id") or hit.get("_source", {}).get("document_id")
                
                # 查找上下文文本块（与 _search_similar_images 相同的逻辑）
                context_chunks = []
                context_info = {}
                
                if document_id and image_id:
                    try:
                        # 获取图片对象
                        image = self.db.query(DocumentImage).filter(
                            DocumentImage.id == image_id
                        ).first()
                        
                        if image:
                            doc_service = DocumentService(self.db)
                            chunks = doc_service.get_chunks_for_image(document_id, image)
                            
                            # 格式化上下文文本块信息
                            minio = MinioStorageService()
                            for chunk in chunks:
                                chunk_meta = {}
                                if chunk.meta:
                                    try:
                                        chunk_meta = json.loads(chunk.meta) if isinstance(chunk.meta, str) else chunk.meta
                                    except:
                                        pass
                                
                                # 获取 chunk 内容（可能需要从 MinIO 读取）
                                chunk_content = chunk.content or ""
                                if not chunk_content:
                                    # 尝试从 MinIO 读取
                                    try:
                                        from app.models.document import Document
                                        import datetime
                                        import gzip
                                        doc = self.db.query(Document).filter(Document.id == document_id).first()
                                        if doc:
                                            created = getattr(doc, 'created_at', None) or datetime.datetime.utcnow()
                                            year = created.strftime('%Y')
                                            month = created.strftime('%m')
                                            object_name = f"documents/{year}/{month}/{document_id}/parsed/chunks/chunks.jsonl.gz"
                                            obj = minio.client.get_object(minio.bucket_name, object_name)
                                            try:
                                                with gzip.GzipFile(fileobj=obj, mode='rb') as gz:
                                                    for line in gz:
                                                        try:
                                                            item = json.loads(line.decode('utf-8'))
                                                            if item.get('index') == chunk.chunk_index or item.get('chunk_index') == chunk.chunk_index:
                                                                chunk_content = item.get('content', '')
                                                                break
                                                        except:
                                                            continue
                                            finally:
                                                try:
                                                    obj.close()
                                                    obj.release_conn()
                                                except:
                                                    pass
                                    except Exception as e:
                                        logger.debug(f"从MinIO读取chunk内容失败: {e}")
                                
                                context_chunks.append({
                                    "chunk_id": chunk.id,
                                    "chunk_index": chunk.chunk_index,
                                    "content": chunk_content[:500] if chunk_content else "",
                                    "chunk_type": chunk.chunk_type or "text",
                                    "page_number": chunk_meta.get('page_number'),
                                    "metadata": chunk_meta
                                })
                            
                            # 构建上下文信息
                            context_info = {
                                "chunks": context_chunks,
                                "chunk_count": len(context_chunks),
                                "document_id": document_id
                            }
                    except Exception as e:
                        logger.warning(f"查找图片上下文文本块失败: {e}")
                
                formatted_results.append({
                    "image_id": str(image_id) if image_id else "",
                    "image_path": hit.get("image_path") or hit.get("_source", {}).get("image_path", ""),
                    "similarity_score": hit.get("_score", 0) or hit.get("similarity_score", 0),
                    "image_info": hit.get("_source", {}).get("image_info", {}),
                    "source_document": hit.get("_source", {}).get("source_document", {}),
                    # ✅ 新增：上下文文本块信息
                    "context_info": context_info
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
        search_results: List[Dict[str, Any]],
        session_info: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """生成流式答案"""
        try:
            # 构建上下文
            context = self._build_knowledge_context(search_results)
            
            # 获取LLM模型配置
            model = settings.OLLAMA_MODEL
            if session_info and session_info.get("llm_config"):
                model = session_info["llm_config"].get("model", model)
            
            # 构建消息列表
            if context.strip():
                user_prompt = self._build_kb_prompt(question_content, context)
            else:
                user_prompt = question_content

            messages = [
                {
                    "role": "system",
                    "content": "你是一个智能知识库助手，基于提供的知识库内容回答用户问题。请确保回答准确、详细，并明确引用来源信息。"
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
            ]
            
            # 调用Ollama流式API
            try:
                async for chunk_content in self.ollama_service.stream_chat_completion(messages, model):
                    yield {
                        "type": "content_chunk",
                        "data": {
                            "content": chunk_content,
                            "timestamp": datetime.now().isoformat()
                        }
                    }
            except Exception as e:
                logger.error(f"Ollama流式生成失败，降级到非流式: {e}")
                # 降级到非流式生成
                answer = await self.ollama_service.chat_completion(messages, model)
                # 将答案分块返回
                chunk_size = 10
                for i in range(0, len(answer), chunk_size):
                    chunk = answer[i:i+chunk_size]
                    yield {
                        "type": "content_chunk",
                        "data": {
                            "content": chunk,
                            "timestamp": datetime.now().isoformat()
                        }
                    }
                    await asyncio.sleep(0.05)
            
        except Exception as e:
            logger.error(f"生成流式答案失败: {e}", exc_info=True)
            yield {
                "type": "error",
                "data": {"message": str(e)}
            }

    def _post_process_llm_answer(self, answer: str) -> str:
        """清洗LLM返回的答案，去掉<think>等头脑风暴标记并格式化"""
        if not answer:
            return ""

        cleaned = answer.strip()

        # 去掉<think>...</think>结构
        lower = cleaned.lower()
        think_start = lower.find("<think>")
        think_end = lower.find("</think>")
        if think_start != -1 and think_end != -1:
            front = cleaned[:think_start]
            tail = cleaned[think_end + len("</think>") :]
            cleaned = (front + tail).strip()

        # 如果仍包含裸的<think>起始标签（无闭合），也一并去掉
        cleaned = cleaned.replace("<think>", "").replace("</think>", "")

        # 规范中文段落，保证可读性
        cleaned = cleaned.replace("\r\n", "\n")
        while "\n\n\n" in cleaned:
            cleaned = cleaned.replace("\n\n\n", "\n\n")

        return cleaned.strip()
    
    def _extract_result_text(self, result: Dict[str, Any]) -> str:
        """提取检索结果的文本内容（支持表格数据）"""
        def _serialize_matrix(matrix: Any) -> str:
            lines: List[str] = []
            if isinstance(matrix, list):
                for row in matrix:
                    if isinstance(row, (list, tuple)):
                        lines.append(" | ".join(str(cell) for cell in row))
                    elif isinstance(row, dict):
                        lines.append(" | ".join(f"{k}:{v}" for k, v in row.items()))
                    else:
                        lines.append(str(row))
            elif isinstance(matrix, dict):
                lines.append(" | ".join(f"{k}:{v}" for k, v in matrix.items()))
            else:
                lines.append(str(matrix))
            return "\n".join(lines).strip()

        text = (result.get("content") or "").strip()
        if text:
            return text

        metadata = result.get("metadata") or {}
        for key in ("content", "text", "summary"):
            meta_text = (metadata.get(key) or "").strip()
            if meta_text:
                return meta_text

        table = result.get("table") or metadata.get("table")
        if table:
            headers = table.get("headers") or []
            rows = table.get("rows") or table.get("data") or []
            lines: List[str] = []
            if headers:
                lines.append(" | ".join(str(h) for h in headers))
            if isinstance(rows, list):
                for row in rows:
                    if isinstance(row, dict):
                        if headers:
                            lines.append(" | ".join(str(row.get(h, "")) for h in headers))
                        else:
                            lines.append(" | ".join(f"{k}:{v}" for k, v in row.items()))
                    elif isinstance(row, (list, tuple)):
                        lines.append(" | ".join(str(cell) for cell in row))
                    else:
                        lines.append(str(row))
            return "\n".join(lines).strip()

        for matrix_key in ("matrix", "cells"):
            matrix = result.get(matrix_key) or metadata.get(matrix_key)
            if matrix:
                serialized = _serialize_matrix(matrix)
                if serialized:
                    return serialized

        return ""

    def _build_knowledge_context(self, search_results: List[Dict[str, Any]]) -> str:
        """构建知识库上下文"""
        context_parts = []
        for i, result in enumerate(search_results[:5]):
            snippet = self._extract_result_text(result)
            if not snippet:
                continue
            context_parts.append(f"[来源{i+1}]\n{snippet}\n")
        return "\n".join(context_parts)

    def _build_citations_from_results(self, search_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """根据检索结果构建引用信息"""
        citations: List[Dict[str, Any]] = []
        for idx, result in enumerate(search_results[:settings.QA_DEFAULT_MAX_SOURCES], start=1):
            snippet = self._extract_result_text(result)
            citations.append({
                "document_id": result.get("document_id"),
                "document_title": result.get("document_title") or f"文档{idx}",
                "knowledge_base_name": result.get("knowledge_base_name") or "",
                "content_snippet": (snippet or "")[:200],
                "content": snippet,
                "similarity_score": result.get("similarity_score", 0.0),
                "position_info": {
                    "chunk_index": result.get("chunk_index"),
                    "page_number": result.get("page_number")
                },
                "associated_images": result.get("associated_images", [])
            })
        return citations

    def _build_kb_prompt(self, question_content: str, kb_context: str) -> str:
        """构建知识库回答提示词"""
        return (
            "基于以下知识库内容回答用户问题：\n\n"
            f"知识库内容：\n{kb_context}\n\n"
            f"用户问题：{question_content}\n\n"
            "请基于知识库内容提供准确、详细的回答，并在回答中引用来源（例如：来源1）。"
        )
    
    def _session_to_dict(self, session: QASession) -> dict:
        """将QASession对象转换为字典"""
        return {
            "session_id": session.session_id,
            "session_name": session.session_name,
            "knowledge_base_id": session.knowledge_base_id,
            "knowledge_base_name": f"知识库{session.knowledge_base_id}",
            "search_type": session.query_method or "hybrid",
            "search_config": session.search_config or {},
            # LLM 模型配置统一从全局 settings 读取，此处不返回数据库中的旧缓存
            "llm_config": {},
            "question_count": session.question_count,
            "last_question": session.last_question,
            "last_activity": session.last_activity_time.isoformat() if session.last_activity_time else None,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "status": session.status
        }