"""
QA API Routes
根据知识问答系统设计文档实现
"""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime
import json

from app.schemas.qa import (
    QASessionCreate, QASessionResponse, QASessionListResponse,
    QAMultimodalQuestionRequest, QAMultimodalQuestionResponse,
    QAImageSearchRequest, QAImageSearchResponse,
    QAHistoryResponse, QAHistorySearchRequest, QAHistorySearchResponse,
    QAModelResponse, QASessionConfigUpdate
)
from app.services.qa_service import QAService
from app.services.multimodal_processing_service import MultimodalProcessingService
from app.services.fallback_strategy_service import FallbackStrategyService
from app.services.qa_history_service import QAHistoryService
from app.dependencies.database import get_db
from app.core.logging import logger
from app.config.settings import settings

router = APIRouter()

# 1. 知识库选择功能

@router.get("/knowledge-bases", response_model=QASessionListResponse)
def get_knowledge_bases(
    category_id: Optional[int] = None,
    status: str = "active",
    page: int = 1,
    size: int = settings.QA_DEFAULT_PAGE_SIZE,
    db: Session = Depends(get_db)
):
    """获取知识库列表 - 根据设计文档实现"""
    try:
        logger.info(f"API请求: 获取知识库列表，分类ID: {category_id}, 状态: {status}")
        
        service = QAService(db)
        result = service.get_knowledge_bases(
            category_id=category_id,
            status=status,
            page=page,
            size=size
        )
        
        logger.info(f"API响应: 返回 {len(result.knowledge_bases)} 个知识库")
        return result
        
    except Exception as e:
        logger.error(f"获取知识库列表API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取知识库列表失败: {str(e)}"
        )

@router.get("/knowledge-bases/{kb_id}", response_model=QASessionResponse)
def get_knowledge_base_detail(
    kb_id: int,
    db: Session = Depends(get_db)
):
    """获取知识库详情 - 根据设计文档实现"""
    try:
        logger.info(f"API请求: 获取知识库详情 {kb_id}")
        
        service = QAService(db)
        result = service.get_knowledge_base_detail(kb_id)
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="知识库不存在"
            )
        
        logger.info(f"API响应: 成功获取知识库详情 {result.name}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取知识库详情API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取知识库详情失败: {str(e)}"
        )

@router.get("/search-types")
def get_search_types():
    """获取查询方式配置 - 根据设计文档实现"""
    try:
        logger.info("API请求: 获取查询方式配置")
        
        search_types = [
            {
                "type": "vector",
                "name": "向量检索",
                "description": "基于语义相似度的向量搜索",
                "icon": "vector-search",
                "recommended": True
            },
            {
                "type": "keyword",
                "name": "关键词检索", 
                "description": "基于BM25算法的关键词搜索",
                "icon": "keyword-search",
                "recommended": False
            },
            {
                "type": "hybrid",
                "name": "混合检索",
                "description": "向量检索和关键词检索的加权融合",
                "icon": "hybrid-search",
                "recommended": True
            },
            {
                "type": "exact",
                "name": "精确匹配",
                "description": "精确的文本匹配搜索",
                "icon": "exact-search",
                "recommended": False
            },
            {
                "type": "fuzzy",
                "name": "模糊搜索",
                "description": "支持通配符和正则表达式的搜索",
                "icon": "fuzzy-search",
                "recommended": False
            },
            {
                "type": "image",
                "name": "图片搜索",
                "description": "以图找图和以文找图搜索",
                "icon": "image-search",
                "recommended": True
            }
        ]
        
        logger.info("API响应: 成功获取查询方式配置")
        return {"search_types": search_types}
        
    except Exception as e:
        logger.error(f"获取查询方式配置API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取查询方式配置失败: {str(e)}"
        )

# 2. 会话管理功能

@router.post("/sessions", response_model=QASessionResponse)
def create_qa_session(
    session_data: QASessionCreate,
    db: Session = Depends(get_db)
):
    """创建问答会话 - 根据设计文档实现"""
    try:
        logger.info(f"API请求: 创建问答会话，知识库ID: {session_data.knowledge_base_id}")
        
        service = QAService(db)
        result = service.create_qa_session(session_data)

        # 兼容服务层返回 Pydantic 模型或 dict
        try:
            sid = getattr(result, 'session_id', None) or (result.get('session_id') if isinstance(result, dict) else None)
        except Exception:
            sid = None
        logger.info(f"API响应: 成功创建会话 {sid if sid else '[unknown]'}")
        return result
        
    except Exception as e:
        logger.error(f"创建问答会话API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建问答会话失败: {str(e)}"
        )

@router.get("/sessions", response_model=QASessionListResponse)
def get_qa_sessions(
    page: int = 1,
    size: int = settings.QA_DEFAULT_PAGE_SIZE,
    knowledge_base_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """获取会话列表 - 根据设计文档实现"""
    try:
        logger.info(f"API请求: 获取会话列表，页码: {page}, 大小: {size}")
        
        service = QAService(db)
        result = service.get_qa_sessions(
            page=page,
            size=size,
            knowledge_base_id=knowledge_base_id
        )
        
        logger.info(f"API响应: 返回 {len(result.sessions)} 个会话")
        return result
        
    except Exception as e:
        logger.error(f"获取会话列表API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取会话列表失败: {str(e)}"
        )

@router.get("/sessions/{session_id}", response_model=QASessionResponse)
def get_qa_session_detail(
    session_id: str,
    db: Session = Depends(get_db)
):
    """获取会话详情 - 根据设计文档实现"""
    try:
        logger.info(f"API请求: 获取会话详情 {session_id}")
        
        service = QAService(db)
        result = service.get_qa_session_detail(session_id)
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="会话不存在"
            )
        
        # 兼容 dict / 模型
        try:
            sname = getattr(result, 'session_name', None) or (result.get('session_name') if isinstance(result, dict) else None)
        except Exception:
            sname = None
        logger.info(f"API响应: 成功获取会话详情 {sname if sname else '[unknown]'}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取会话详情API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取会话详情失败: {str(e)}"
        )

@router.delete("/sessions/{session_id}")
def delete_qa_session(
    session_id: str,
    db: Session = Depends(get_db)
):
    """删除会话 - 根据设计文档实现"""
    try:
        logger.info(f"API请求: 删除会话 {session_id}")
        
        service = QAService(db)
        success = service.delete_qa_session(session_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="会话不存在"
            )
        
        logger.info(f"API响应: 成功删除会话 {session_id}")
        return {"message": "会话删除成功"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除会话API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除会话失败: {str(e)}"
        )

# 3. 多模态问答功能

@router.post("/sessions/{session_id}/multimodal-questions", response_model=QAMultimodalQuestionResponse)
async def ask_multimodal_question(
    session_id: str,
    text_content: Optional[str] = Form(None),
    image_file: Optional[UploadFile] = File(None),
    input_type: str = Form("text"),
    include_history: bool = Form(True),
    max_history: int = Form(settings.QA_DEFAULT_MAX_HISTORY),
    similarity_threshold: float = Form(settings.SEARCH_VECTOR_THRESHOLD),
    max_sources: int = Form(settings.QA_DEFAULT_MAX_SOURCES),
    search_type: str = Form("hybrid"),
    db: Session = Depends(get_db)
):
    """多模态问答接口 - 根据设计文档实现"""
    try:
        logger.info(f"API请求: 多模态问答，会话ID: {session_id}, 输入类型: {input_type}")
        
        # 验证输入类型
        if input_type not in ["text", "image", "multimodal"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="输入类型必须是 text、image 或 multimodal"
            )
        
        # 验证输入内容
        if input_type == "text" and not text_content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="文本输入类型需要提供文本内容"
            )
        
        if input_type == "image" and not image_file:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="图片输入类型需要提供图片文件"
            )
        
        if input_type == "multimodal" and (not text_content or not image_file):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="图文混合输入类型需要同时提供文本内容和图片文件"
            )
        
        # 多模态处理服务
        multimodal_service = MultimodalProcessingService(db)
        
        # 处理多模态输入
        processed_input = await multimodal_service.process_multimodal_input(
            text_content=text_content,
            image_file=image_file,
            input_type=input_type
        )
        logger.debug(
            "[QA][API] processed_input summary: session=%s text_len=%s image=%s steps=%s",
            session_id,
            len((processed_input.get("text_data") or {}).get("cleaned_text", "")) if processed_input else 0,
            "yes" if processed_input.get("image_data") else "no",
            (processed_input or {}).get("processing_steps")
        )
        
        # 问答服务
        qa_service = QAService(db)
        
        # 执行问答
        result = await qa_service.ask_multimodal_question(
            session_id=session_id,
            processed_input=processed_input,
            include_history=include_history,
            max_history=max_history,
            similarity_threshold=similarity_threshold,
            max_sources=max_sources,
            search_type=search_type
        )
        
        logger.info(f"API响应: 多模态问答完成，问题ID: {result.question_id}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"多模态问答API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"多模态问答失败: {str(e)}"
        )

# 4. 图片搜索功能

@router.post("/sessions/{session_id}/image-search", response_model=QAImageSearchResponse)
async def search_images(
    session_id: str,
    image_file: UploadFile = File(...),
    search_type: str = "image-to-image",
    similarity_threshold: float = settings.SEARCH_VECTOR_THRESHOLD,
    max_results: int = settings.QA_DEFAULT_MAX_RESULTS,
    knowledge_base_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """图片搜索接口 - 根据设计文档实现"""
    try:
        logger.info(f"API请求: 图片搜索，会话ID: {session_id}, 搜索类型: {search_type}")
        
        # 验证搜索类型
        if search_type not in ["image-to-image", "text-to-image"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="搜索类型必须是 image-to-image 或 text-to-image"
            )
        
        # 多模态处理服务
        multimodal_service = MultimodalProcessingService(db)
        
        # 处理图片输入
        processed_image = await multimodal_service.process_image_input(image_file)
        
        # 图片搜索服务
        qa_service = QAService(db)
        
        # 执行图片搜索
        result = await qa_service.search_images(
            session_id=session_id,
            processed_image=processed_image,
            search_type=search_type,
            similarity_threshold=similarity_threshold,
            max_results=max_results,
            knowledge_base_id=knowledge_base_id
        )
        
        logger.info(f"API响应: 图片搜索完成，找到 {len(result.results)} 个结果")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"图片搜索API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"图片搜索失败: {str(e)}"
        )

# 5. 流式问答功能

@router.websocket("/sessions/{session_id}/stream")
async def websocket_stream(
    websocket: WebSocket,
    session_id: str,
    db: Session = Depends(get_db)
):
    """流式问答WebSocket接口 - 根据设计文档实现"""
    await websocket.accept()
    
    try:
        logger.info(f"WebSocket连接: 流式问答，会话ID: {session_id}")
        
        qa_service = QAService(db)
        
        while True:
            # 接收客户端消息
            data = await websocket.receive_json()
            
            if data.get("type") == "question":
                # 处理问答请求
                question_data = data.get("data", {})
                
                # 执行流式问答
                async for chunk in qa_service.stream_answer(
                    session_id=session_id,
                    question_data=question_data
                ):
                    await websocket.send_json({
                        "type": "content_chunk",
                        "data": chunk
                    })
                
                # 发送完成通知
                await websocket.send_json({
                    "type": "completion",
                    "data": {"status": "completed"}
                })
            
            elif data.get("type") == "close":
                break
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket断开: 会话ID {session_id}")
    except Exception as e:
        logger.error(f"WebSocket流式问答错误: {e}", exc_info=True)
        await websocket.send_json({
            "type": "error",
            "data": {"message": str(e)}
        })

# 6. 配置管理功能

@router.get("/models", response_model=List[QAModelResponse])
def get_available_models():
    """获取可用模型 - 根据设计文档实现"""
    try:
        logger.info("API请求: 获取可用模型")
        
        models = {
            "llm_models": [
                {
                    "name": "llama2",
                    "display_name": "Llama 2",
                    "description": "Meta的Llama 2大语言模型",
                    "language": "multilingual",
                    "size": "7B",
                    "status": "available"
                },
                {
                    "name": "codellama",
                    "display_name": "Code Llama",
                    "description": "专门用于代码生成的Llama模型",
                    "language": "multilingual",
                    "size": "7B",
                    "status": "available"
                }
            ],
            "embedding_models": [
                {
                    "name": "nomic-embed-text",
                    "display_name": "Nomic Embed Text",
                    "description": "Nomic的文本嵌入模型",
                    "dimension": settings.TEXT_EMBEDDING_DIMENSION,
                    "language": "multilingual",
                    "status": "available"
                },
                {
                    "name": "mxbai-embed-large",
                    "display_name": "MXBai Embed Large",
                    "description": "MXBai的大规模嵌入模型",
                    "dimension": settings.IMAGE_EMBEDDING_DIMENSION,
                    "language": "multilingual",
                    "status": "available"
                }
            ]
        }
        
        logger.info("API响应: 成功获取可用模型")
        return models
        
    except Exception as e:
        logger.error(f"获取可用模型API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取可用模型失败: {str(e)}"
        )

@router.put("/sessions/{session_id}/config")
def update_session_config(
    session_id: str,
    config_update: QASessionConfigUpdate,
    db: Session = Depends(get_db)
):
    """更新会话配置 - 根据设计文档实现"""
    try:
        logger.info(f"API请求: 更新会话配置 {session_id}")
        
        service = QAService(db)
        result = service.update_session_config(session_id, config_update)
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="会话不存在"
            )
        
        logger.info(f"API响应: 成功更新会话配置 {session_id}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新会话配置API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新会话配置失败: {str(e)}"
        )

# 7. 历史记录查询功能

@router.post("/history/search", response_model=QAHistorySearchResponse)
def search_qa_history(
    search_request: QAHistorySearchRequest,
    db: Session = Depends(get_db)
):
    """搜索历史问答 - 根据设计文档实现"""
    try:
        logger.info(f"API请求: 搜索历史问答，关键词: {search_request.search_keyword}")
        
        history_service = QAHistoryService(db)
        result = history_service.search_qa_history(search_request)
        
        logger.info(f"API响应: 找到 {len(result.search_results)} 个搜索结果")
        return result
        
    except Exception as e:
        logger.error(f"搜索历史问答API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"搜索历史问答失败: {str(e)}"
        )

@router.get("/history/{question_id}", response_model=Dict[str, Any])
def get_qa_detail(
    question_id: str,
    db: Session = Depends(get_db)
):
    """获取问答详情 - 根据设计文档实现"""
    try:
        logger.info(f"API请求: 获取问答详情 {question_id}")
        
        history_service = QAHistoryService(db)
        result = history_service.get_qa_detail(question_id)
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="问答记录不存在"
            )
        
        logger.info(f"API响应: 成功获取问答详情 {question_id}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取问答详情API错误: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取问答详情失败: {str(e)}"
        )

@router.get("/history", response_model=List[QAHistoryResponse])
async def get_qa_history(
    skip: int = 0,
    limit: int = settings.QA_MAX_PAGE_SIZE,
    session_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """获取问答历史"""
    service = QAService(db)
    return await service.get_qa_history(
        skip=skip, 
        limit=limit, 
        session_id=session_id
    )
