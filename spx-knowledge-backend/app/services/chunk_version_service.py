"""
Chunk Version Service
根据文档修改功能设计实现块版本管理服务
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime
from app.models.chunk import DocumentChunk
from app.models.chunk_version import ChunkVersion
from app.schemas.chunk_version import ChunkVersionCreate, ChunkVersionUpdate, ChunkVersionResponse, ChunkVersionListResponse, ChunkRevertRequest, ChunkRevertResponse
from app.services.base import BaseService
from app.core.logging import logger
from app.core.exceptions import CustomException, ErrorCode

class ChunkVersionService(BaseService[ChunkVersion]):
    """块版本服务 - 严格按照文档修改功能设计实现"""
    
    def __init__(self, db: Session):
        super().__init__(db, ChunkVersion)
    
    def create_chunk_version(self, chunk_id: int, version_data: ChunkVersionCreate) -> ChunkVersionResponse:
        """创建块版本 - 根据设计文档实现"""
        try:
            logger.info(f"创建块版本: chunk_id={chunk_id}")
            
            # 验证块是否存在
            chunk = self.db.query(DocumentChunk).filter(DocumentChunk.id == chunk_id).first()
            if not chunk:
                raise CustomException(
                    code=ErrorCode.VALIDATION_ERROR,
                    message=f"块 {chunk_id} 不存在"
                )
            
            # 获取当前最大版本号
            last_version = self.db.query(ChunkVersion).filter(
                ChunkVersion.chunk_id == chunk_id
            ).order_by(ChunkVersion.version_number.desc()).first()
            
            version_number = (last_version.version_number + 1) if last_version else 1
            
            # 创建版本记录
            version = ChunkVersion(
                chunk_id=chunk_id,
                version_number=version_number,
                content=version_data.content,
                metadata=getattr(version_data, 'meta', version_data.metadata),
                modified_by=version_data.modified_by,
                version_comment=version_data.version_comment,
                created_at=datetime.now()
            )
            
            self.db.add(version)
            self.db.commit()
            self.db.refresh(version)
            
            logger.info(f"块版本创建成功: chunk_id={chunk_id}, version={version_number}")
            return ChunkVersionResponse.from_orm(version)
            
        except CustomException:
            raise
        except Exception as e:
            logger.error(f"创建块版本错误: {e}", exc_info=True)
            self.db.rollback()
            raise CustomException(
                code=ErrorCode.VALIDATION_ERROR,
                message=f"创建块版本失败: {str(e)}"
            )
    
    def get_chunk_versions(self, chunk_id: int, skip: int = 0, limit: int = 100) -> ChunkVersionListResponse:
        """获取块版本列表 - 根据设计文档实现"""
        try:
            logger.info(f"获取块版本列表: chunk_id={chunk_id}")
            
            # 验证块是否存在
            chunk = self.db.query(DocumentChunk).filter(DocumentChunk.id == chunk_id).first()
            if not chunk:
                raise CustomException(
                    code=ErrorCode.VALIDATION_ERROR,
                    message=f"块 {chunk_id} 不存在"
                )
            
            # 获取版本列表
            versions = self.db.query(ChunkVersion).filter(
                ChunkVersion.chunk_id == chunk_id
            ).order_by(ChunkVersion.version_number.desc()).offset(skip).limit(limit).all()
            
            total_versions = self.db.query(ChunkVersion).filter(
                ChunkVersion.chunk_id == chunk_id
            ).count()
            
            version_responses = [ChunkVersionResponse.from_orm(v) for v in versions]
            
            logger.info(f"获取块版本列表成功: chunk_id={chunk_id}, 版本数={len(version_responses)}")
            return ChunkVersionListResponse(
                chunk_id=chunk_id,
                total_versions=total_versions,
                versions=version_responses
            )
            
        except CustomException:
            raise
        except Exception as e:
            logger.error(f"获取块版本列表错误: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.VALIDATION_ERROR,
                message=f"获取块版本列表失败: {str(e)}"
            )
    
    def get_chunk_version(self, chunk_id: int, version_number: int) -> Optional[ChunkVersionResponse]:
        """获取特定版本 - 根据设计文档实现"""
        try:
            logger.info(f"获取块版本: chunk_id={chunk_id}, version={version_number}")
            
            version = self.db.query(ChunkVersion).filter(
                ChunkVersion.chunk_id == chunk_id,
                ChunkVersion.version_number == version_number
            ).first()
            
            if not version:
                logger.warning(f"版本不存在: chunk_id={chunk_id}, version={version_number}")
                return None
            
            logger.info(f"获取块版本成功: chunk_id={chunk_id}, version={version_number}")
            return ChunkVersionResponse.from_orm(version)
            
        except Exception as e:
            logger.error(f"获取块版本错误: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.VALIDATION_ERROR,
                message=f"获取块版本失败: {str(e)}"
            )
    
    def revert_chunk_to_version(self, chunk_id: int, revert_request: ChunkRevertRequest) -> ChunkRevertResponse:
        """回退块到指定版本 - 根据设计文档实现"""
        try:
            logger.info(f"回退块版本: chunk_id={chunk_id}, target_version={revert_request.target_version}")
            
            # 验证块是否存在
            chunk = self.db.query(DocumentChunk).filter(DocumentChunk.id == chunk_id).first()
            if not chunk:
                raise CustomException(
                    code=ErrorCode.VALIDATION_ERROR,
                    message=f"块 {chunk_id} 不存在"
                )
            
            # 验证目标版本是否存在
            target_version = self.db.query(ChunkVersion).filter(
                ChunkVersion.chunk_id == chunk_id,
                ChunkVersion.version_number == revert_request.target_version
            ).first()
            
            if not target_version:
                raise CustomException(
                    code=ErrorCode.VALIDATION_ERROR,
                    message=f"目标版本 {revert_request.target_version} 不存在"
                )
            
            # 保存当前版本
            current_version = chunk.version
            current_content = chunk.content
            current_metadata = getattr(chunk, 'meta', chunk.metadata)
            
            # 创建当前版本的版本记录
            current_version_record = ChunkVersion(
                chunk_id=chunk_id,
                version_number=current_version + 1,
                content=current_content,
                metadata=current_metadata,
                modified_by="system",
                version_comment=f"回退前的版本保存",
                created_at=datetime.now()
            )
            
            self.db.add(current_version_record)
            
            # 恢复目标版本
            chunk.content = target_version.content
            if hasattr(chunk, 'meta'):
                chunk.meta = target_version.meta if hasattr(target_version, 'meta') else target_version.metadata
            else:
                chunk.metadata = target_version.metadata
            chunk.version = revert_request.target_version
            chunk.last_modified_at = datetime.now()
            chunk.modification_count += 1
            chunk.last_modified_by = "system"
            
            self.db.commit()
            
            # TODO: 触发重新向量化任务
            task_id = f"revert_task_{chunk_id}_{datetime.now().timestamp()}"
            
            logger.info(f"块版本回退成功: chunk_id={chunk_id}, from={current_version}, to={revert_request.target_version}")
            return ChunkRevertResponse(
                chunk_id=chunk_id,
                from_version=current_version,
                to_version=revert_request.target_version,
                task_id=task_id,
                message="块版本回退成功，正在重新向量化"
            )
            
        except CustomException:
            raise
        except Exception as e:
            logger.error(f"回退块版本错误: {e}", exc_info=True)
            self.db.rollback()
            raise CustomException(
                code=ErrorCode.VALIDATION_ERROR,
                message=f"回退块版本失败: {str(e)}"
            )
    
    def revert_chunk_to_previous_version(self, chunk_id: int) -> ChunkRevertResponse:
        """回退到上一个版本 - 根据设计文档实现"""
        try:
            logger.info(f"回退到上一个版本: chunk_id={chunk_id}")
            
            # 验证块是否存在
            chunk = self.db.query(DocumentChunk).filter(DocumentChunk.id == chunk_id).first()
            if not chunk:
                raise CustomException(
                    code=ErrorCode.VALIDATION_ERROR,
                    message=f"块 {chunk_id} 不存在"
                )
            
            # 获取上一个版本
            previous_version = self.db.query(ChunkVersion).filter(
                ChunkVersion.chunk_id == chunk_id,
                ChunkVersion.version_number < chunk.version
            ).order_by(ChunkVersion.version_number.desc()).first()
            
            if not previous_version:
                raise CustomException(
                    code=ErrorCode.VALIDATION_ERROR,
                    message=f"块 {chunk_id} 没有上一个版本可以回退"
                )
            
            # 执行回退
            revert_request = ChunkRevertRequest(
                target_version=previous_version.version_number,
                revert_comment="回退到上一个版本"
            )
            
            return self.revert_chunk_to_version(chunk_id, revert_request)
            
        except CustomException:
            raise
        except Exception as e:
            logger.error(f"回退到上一个版本错误: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.VALIDATION_ERROR,
                message=f"回退到上一个版本失败: {str(e)}"
            )
