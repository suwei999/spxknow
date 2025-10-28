"""
Image Search Service
根据文档处理流程设计实现图片搜索功能
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from fastapi import UploadFile
from app.models.image import DocumentImage
from app.schemas.image import ImageSearchRequest, ImageSearchResponse
from app.services.vector_service import VectorService
from app.services.opensearch_service import OpenSearchService
from app.core.logging import logger
from app.config.settings import settings
from app.core.exceptions import CustomException, ErrorCode

class ImageSearchService:
    """图片搜索服务 - 严格按照设计文档实现"""
    
    def __init__(self, db: Session):
        self.db = db
        self.vector_service = VectorService(db)
        self.opensearch_service = OpenSearchService()
    
    async def search_by_image(
        self,
        file: UploadFile,
        similarity_threshold: float = 0.7,
        limit: int = 10,
        knowledge_base_id: Optional[int] = None
    ) -> List[ImageSearchResponse]:
        """以图找图搜索 - 根据设计文档实现"""
        try:
            logger.info(f"开始以图找图搜索: {file.filename}")
            
            # 根据设计文档的以图找图流程：
            # 用户上传图片 → 图片验证 → 图片预处理 → 特征提取 → 向量生成 → 向量搜索 → 相似度计算 → 结果排序 → 结果过滤 → 结果返回
            
            # 1. 图片验证和预处理
            logger.info("步骤1: 图片验证和预处理")
            processed_image = await self._preprocess_image(file)
            
            # 2. 特征提取和向量生成
            logger.info("步骤2: 特征提取和向量生成")
            image_vector = self.vector_service.generate_image_embedding(processed_image["path"])
            
            if not image_vector:
                logger.error("图片向量生成失败")
                raise CustomException(
                    code=ErrorCode.VECTOR_GENERATION_FAILED,
                    message="图片向量生成失败"
                )
            
            # 3. 向量搜索
            logger.info("步骤3: 向量搜索")
            search_results = await self.opensearch_service.search_image_vectors(
                query_vector=image_vector,
                similarity_threshold=similarity_threshold,
                limit=limit,
                knowledge_base_id=knowledge_base_id
            )
            
            # 4. 结果处理和排序
            logger.info("步骤4: 结果处理和排序")
            results = []
            for result in search_results:
                image_response = ImageSearchResponse(
                    image_id=result["image_id"],
                    document_id=result["document_id"],
                    knowledge_base_id=result["knowledge_base_id"],
                    image_path=result["image_path"],
                    similarity_score=result["similarity_score"],
                    image_type=result.get("image_type", "unknown"),
                    page_number=result.get("page_number"),
                    coordinates=result.get("coordinates"),
                    ocr_text=result.get("ocr_text", ""),
                    description=result.get("description", ""),
                    source_document=result.get("source_document", "")
                )
                results.append(image_response)
            
            # 按相似度排序
            results.sort(key=lambda x: x.similarity_score, reverse=True)
            
            logger.info(f"以图找图搜索完成，找到 {len(results)} 个结果")
            return results
            
        except CustomException:
            raise
        except Exception as e:
            logger.error(f"以图找图搜索错误: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.SEARCH_FAILED,
                message=f"以图找图搜索失败: {str(e)}"
            )
    
    async def search_by_text(
        self,
        search_request: ImageSearchRequest
    ) -> List[ImageSearchResponse]:
        """以文找图搜索 - 根据设计文档实现"""
        try:
            logger.info(f"开始以文找图搜索: {search_request.query_text}")
            
            # 根据设计文档的以文找图流程：
            # 用户输入文本 → 文本处理 → 意图识别 → 向量化 → 多路搜索 → 结果融合 → 相关性评分 → 结果排序 → 结果过滤 → 结果返回
            
            # 1. 文本处理和意图识别
            logger.info("步骤1: 文本处理和意图识别")
            processed_text = await self._process_search_text(search_request.query_text)
            
            # 2. 文本向量化
            logger.info("步骤2: 文本向量化")
            text_vector = self.vector_service.generate_embedding(processed_text)
            
            if not text_vector:
                logger.error("文本向量生成失败")
                raise CustomException(
                    code=ErrorCode.VECTOR_GENERATION_FAILED,
                    message="文本向量生成失败"
                )
            
            # 3. 多路搜索（向量搜索 + 关键词搜索）
            logger.info("步骤3: 多路搜索")
            
            # 向量搜索
            vector_results = await self.opensearch_service.search_image_vectors(
                query_vector=text_vector,
                similarity_threshold=search_request.similarity_threshold,
                limit=search_request.limit,
                knowledge_base_id=search_request.knowledge_base_id
            )
            
            # 关键词搜索
            keyword_results = await self.opensearch_service.search_image_keywords(
                query_text=processed_text,
                limit=search_request.limit,
                knowledge_base_id=search_request.knowledge_base_id
            )
            
            # 4. 结果融合和相关性评分
            logger.info("步骤4: 结果融合和相关性评分")
            merged_results = await self._merge_search_results(
                vector_results, keyword_results, processed_text
            )
            
            # 5. 结果排序和过滤
            logger.info("步骤5: 结果排序和过滤")
            results = []
            for result in merged_results:
                if result["relevance_score"] >= search_request.similarity_threshold:
                    image_response = ImageSearchResponse(
                        image_id=result["image_id"],
                        document_id=result["document_id"],
                        knowledge_base_id=result["knowledge_base_id"],
                        image_path=result["image_path"],
                        similarity_score=result["relevance_score"],
                        image_type=result.get("image_type", "unknown"),
                        page_number=result.get("page_number"),
                        coordinates=result.get("coordinates"),
                        ocr_text=result.get("ocr_text", ""),
                        description=result.get("description", ""),
                        source_document=result.get("source_document", "")
                    )
                    results.append(image_response)
            
            # 按相关性排序
            results.sort(key=lambda x: x.similarity_score, reverse=True)
            
            logger.info(f"以文找图搜索完成，找到 {len(results)} 个结果")
            return results
            
        except CustomException:
            raise
        except Exception as e:
            logger.error(f"以文找图搜索错误: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.SEARCH_FAILED,
                message=f"以文找图搜索失败: {str(e)}"
            )
    
    async def get_similar_images(
        self,
        image_id: int,
        similarity_threshold: float = 0.7,
        limit: int = 10
    ) -> List[ImageSearchResponse]:
        """获取相似图片 - 根据设计文档实现"""
        try:
            logger.info(f"开始获取相似图片: {image_id}")
            
            # 1. 获取图片信息
            image = self.db.query(DocumentImage).filter(DocumentImage.id == image_id).first()
            if not image:
                raise CustomException(
                    code=ErrorCode.IMAGE_NOT_FOUND,
                    message=f"图片 {image_id} 不存在"
                )
            
            # 2. 获取图片向量
            image_vector = await self.opensearch_service.get_image_vector(image_id)
            if not image_vector:
                logger.error(f"图片 {image_id} 的向量不存在")
                raise CustomException(
                    code=ErrorCode.VECTOR_NOT_FOUND,
                    message=f"图片 {image_id} 的向量不存在"
                )
            
            # 3. 搜索相似图片
            search_results = await self.opensearch_service.search_image_vectors(
                query_vector=image_vector,
                similarity_threshold=similarity_threshold,
                limit=limit + 1,  # +1 因为会包含自己
                exclude_image_id=image_id  # 排除自己
            )
            
            # 4. 构建结果
            results = []
            for result in search_results:
                image_response = ImageSearchResponse(
                    image_id=result["image_id"],
                    document_id=result["document_id"],
                    knowledge_base_id=result["knowledge_base_id"],
                    image_path=result["image_path"],
                    similarity_score=result["similarity_score"],
                    image_type=result.get("image_type", "unknown"),
                    page_number=result.get("page_number"),
                    coordinates=result.get("coordinates"),
                    ocr_text=result.get("ocr_text", ""),
                    description=result.get("description", ""),
                    source_document=result.get("source_document", "")
                )
                results.append(image_response)
            
            logger.info(f"获取相似图片完成，找到 {len(results)} 个相似图片")
            return results
            
        except CustomException:
            raise
        except Exception as e:
            logger.error(f"获取相似图片错误: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.SEARCH_FAILED,
                message=f"获取相似图片失败: {str(e)}"
            )
    
    async def extract_ocr_text(self, file: UploadFile) -> str:
        """提取OCR文字 - 根据设计文档实现"""
        try:
            logger.info(f"开始OCR文字识别: {file.filename}")
            
            # 根据设计文档，使用Tesseract + EasyOCR进行OCR识别
            # 支持中英文文字识别
            
            import tempfile
            import shutil
            import pytesseract
            import easyocr
            
            # 创建临时文件
            with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
                temp_path = temp_file.name
            
            # 保存上传的图片到临时文件
            with open(temp_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            ocr_text = ""
            
            try:
                # 使用Tesseract进行OCR识别
                logger.debug("使用Tesseract进行OCR识别")
                tesseract_text = pytesseract.image_to_string(temp_path, lang='chi_sim+eng')
                if tesseract_text.strip():
                    ocr_text += f"[Tesseract] {tesseract_text.strip()}\n"
                
            except Exception as e:
                logger.warning(f"Tesseract OCR识别失败: {e}")
            
            try:
                # 使用EasyOCR进行OCR识别
                logger.debug("使用EasyOCR进行OCR识别")
                reader = easyocr.Reader(['ch_sim', 'en'])
                easyocr_results = reader.readtext(temp_path)
                
                easyocr_text = ""
                for (bbox, text, confidence) in easyocr_results:
                    if confidence > 0.5:  # 置信度阈值
                        easyocr_text += text + " "
                
                if easyocr_text.strip():
                    ocr_text += f"[EasyOCR] {easyocr_text.strip()}\n"
                
            except Exception as e:
                logger.warning(f"EasyOCR识别失败: {e}")
            
            # 清理临时文件
            try:
                os.unlink(temp_path)
            except:
                pass
            
            # 清理和格式化OCR文本
            ocr_text = ocr_text.strip()
            if not ocr_text:
                ocr_text = ""
            
            logger.info(f"OCR文字识别完成: {file.filename}, 识别文字长度: {len(ocr_text)}")
            return ocr_text
            
        except Exception as e:
            logger.error(f"OCR文字识别错误: {e}", exc_info=True)
            return ""
    
    async def get_image_vectors(self, image_id: int) -> Dict[str, Any]:
        """获取图片向量信息 - 根据设计文档实现"""
        try:
            logger.info(f"开始获取图片向量信息: {image_id}")
            
            # 1. 获取图片基本信息
            image = self.db.query(DocumentImage).filter(DocumentImage.id == image_id).first()
            if not image:
                raise CustomException(
                    code=ErrorCode.IMAGE_NOT_FOUND,
                    message=f"图片 {image_id} 不存在"
                )
            
            # 2. 获取向量信息
            vector_info = await self.opensearch_service.get_image_vector_info(image_id)
            
            result = {
                "image_id": image_id,
                "document_id": image.document_id,
                "image_path": image.image_path,
                "image_type": image.image_type,
                "vector_dimension": vector_info.get("dimension", settings.IMAGE_EMBEDDING_DIMENSION),
                "vector_model": vector_info.get("model", "CLIP"),
                "vector_version": vector_info.get("version", "1.0"),
                "created_at": vector_info.get("created_at"),
                "updated_at": vector_info.get("updated_at")
            }
            
            logger.info(f"获取图片向量信息完成: {image_id}")
            return result
            
        except CustomException:
            raise
        except Exception as e:
            logger.error(f"获取图片向量信息错误: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.SEARCH_FAILED,
                message=f"获取图片向量信息失败: {str(e)}"
            )
    
    async def _preprocess_image(self, file: UploadFile) -> Dict[str, Any]:
        """图片预处理 - 根据设计文档实现"""
        try:
            logger.info(f"开始图片预处理: {file.filename}")
            
            # 根据设计文档，实现图片预处理：
            # 1. 图片格式转换
            # 2. 尺寸调整
            # 3. 质量优化
            # 4. 保存到临时文件
            
            import tempfile
            import shutil
            from PIL import Image
            
            # 创建临时文件
            with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
                temp_path = temp_file.name
            
            # 保存上传的图片到临时文件
            with open(temp_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            # 使用PIL处理图片
            with Image.open(temp_path) as img:
                # 转换为RGB格式
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # 调整尺寸（保持宽高比）
                img.thumbnail((224, 224), Image.Resampling.LANCZOS)
                
                # 保存处理后的图片
                img.save(temp_path, 'JPEG', quality=95)
                
                result = {
                    "path": temp_path,
                    "format": "JPEG",
                    "width": img.width,
                    "height": img.height,
                    "quality": 95,
                    "file_size": os.path.getsize(temp_path)
                }
            
            logger.info(f"图片预处理完成: {file.filename}, 尺寸: {result['width']}x{result['height']}")
            return result
            
        except Exception as e:
            logger.error(f"图片预处理错误: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.IMAGE_PROCESSING_FAILED,
                message=f"图片预处理失败: {str(e)}"
            )
    
    async def _process_search_text(self, text: str) -> str:
        """文本处理 - 根据设计文档实现"""
        try:
            logger.info(f"开始文本处理: {text[:50]}...")
            
            # TODO: 根据设计文档，这里应该实现：
            # 1. 文本清洗
            # 2. 分词处理
            # 3. 意图识别
            # 4. 问题分类
            
            # 临时实现 - 简单清洗
            processed_text = text.strip().lower()
            
            logger.info(f"文本处理完成: {processed_text[:50]}...")
            return processed_text
            
        except Exception as e:
            logger.error(f"文本处理错误: {e}", exc_info=True)
            return text
    
    async def _merge_search_results(
        self,
        vector_results: List[Dict[str, Any]],
        keyword_results: List[Dict[str, Any]],
        query_text: str
    ) -> List[Dict[str, Any]]:
        """结果融合 - 根据设计文档实现"""
        try:
            logger.info("开始结果融合")
            
            # TODO: 根据设计文档，这里应该实现：
            # 1. 多路结果合并
            # 2. 相关性评分
            # 3. 去重处理
            # 4. 权重计算
            
            # 临时实现 - 简单合并
            merged_results = []
            
            # 添加向量搜索结果
            for result in vector_results:
                result["relevance_score"] = result["similarity_score"]
                result["search_type"] = "vector"
                merged_results.append(result)
            
            # 添加关键词搜索结果
            for result in keyword_results:
                result["relevance_score"] = result.get("keyword_score", 0.5)
                result["search_type"] = "keyword"
                merged_results.append(result)
            
            # 简单去重（基于image_id）
            seen_ids = set()
            unique_results = []
            for result in merged_results:
                if result["image_id"] not in seen_ids:
                    seen_ids.add(result["image_id"])
                    unique_results.append(result)
            
            logger.info(f"结果融合完成，合并后 {len(unique_results)} 个结果")
            return unique_results
            
        except Exception as e:
            logger.error(f"结果融合错误: {e}", exc_info=True)
            return vector_results  # 返回向量搜索结果作为备选
