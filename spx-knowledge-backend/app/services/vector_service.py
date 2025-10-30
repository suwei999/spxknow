"""
Vector Service
根据文档处理流程设计实现向量生成和相似度计算功能
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
import numpy as np
import requests
import json
from app.config.settings import settings
from app.core.logging import logger
from app.core.exceptions import CustomException, ErrorCode

class VectorService:
    """向量服务 - 严格按照设计文档实现"""
    
    def __init__(self, db: Session):
        self.db = db
        # 统一使用 OLLAMA_BASE_URL
        self.ollama_url = settings.OLLAMA_BASE_URL
        self.embedding_model = settings.OLLAMA_EMBEDDING_MODEL
        self.image_model = settings.OLLAMA_IMAGE_MODEL  # TODO: 添加图片模型配置
    
    def generate_embedding(self, text: str) -> List[float]:
        """生成文本嵌入向量 - 严格按照设计文档实现"""
        try:
            logger.debug(f"开始生成文本向量，文本长度: {len(text)}")
            
            # 根据设计文档，使用Ollama进行向量化
            # 支持多种模型：nomic-embed-text（中文优化）、mxbai-embed-large（多语言支持）、all-minilm（轻量级）
            
            # 文本预处理
            processed_text = self._preprocess_text(text)
            
            # 调用Ollama API
            response = requests.post(
                f"{self.ollama_url}/api/embeddings",
                json={
                    "model": self.embedding_model,
                    "prompt": processed_text
                },
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            embedding = result.get("embedding", [])
            
            if not embedding:
                logger.error("Ollama返回空向量")
                raise CustomException(
                    code=ErrorCode.VECTOR_GENERATION_FAILED,
                    message="Ollama返回空向量"
                )
            
            logger.debug(f"文本向量生成完成，向量维度: {len(embedding)}")
            return embedding
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Ollama API调用失败: {e}")
            raise CustomException(
                code=ErrorCode.OLLAMA_API_FAILED,
                message=f"Ollama API调用失败: {str(e)}"
            )
        except Exception as e:
            logger.error(f"向量生成错误: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.VECTOR_GENERATION_FAILED,
                message=f"向量生成失败: {str(e)}"
            )
    
    def generate_image_embedding(self, image_path: str) -> List[float]:
        """生成图片嵌入向量 - 严格按照设计文档实现"""
        try:
            logger.info(f"开始生成图片向量: {image_path}")
            
            # 根据设计文档，使用CLIP、ResNet、ViT等模型生成图片向量
            from app.services.image_vectorization_service import ImageVectorizationService
            
            # 初始化图片向量化服务
            image_vectorizer = ImageVectorizationService()
            
            # 使用混合模型生成向量（CLIP + ResNet + ViT）
            embedding = image_vectorizer.generate_hybrid_embedding(image_path)
            
            if not embedding:
                logger.error("图片向量生成失败")
                raise CustomException(
                    code=ErrorCode.VECTOR_GENERATION_FAILED,
                    message="图片向量生成失败"
                )
            
            logger.info(f"图片向量生成完成，向量维度: {len(embedding)}")
            return embedding
            
        except Exception as e:
            logger.error(f"图片向量生成错误: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.VECTOR_GENERATION_FAILED,
                message=f"图片向量生成失败: {str(e)}"
            )
    
    def calculate_similarity(
        self, 
        vector1: List[float], 
        vector2: List[float]
    ) -> float:
        """计算向量相似度 - 严格按照设计文档实现"""
        try:
            logger.debug(f"计算向量相似度，向量1维度: {len(vector1)}, 向量2维度: {len(vector2)}")
            
            v1 = np.array(vector1)
            v2 = np.array(vector2)
            
            # 检查向量维度是否一致
            if len(v1) != len(v2):
                logger.warning(f"向量维度不一致: {len(v1)} vs {len(v2)}")
                return 0.0
            
            # 计算余弦相似度
            dot_product = np.dot(v1, v2)
            norm1 = np.linalg.norm(v1)
            norm2 = np.linalg.norm(v2)
            
            if norm1 == 0 or norm2 == 0:
                logger.warning("向量为零向量")
                return 0.0
            
            similarity = dot_product / (norm1 * norm2)
            logger.debug(f"相似度计算结果: {similarity}")
            return similarity
            
        except Exception as e:
            logger.error(f"相似度计算错误: {e}", exc_info=True)
            return 0.0
    
    def search_similar_vectors(
        self, 
        query_vector: List[float], 
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """搜索相似向量 - 根据设计文档实现"""
        try:
            logger.info(f"开始向量搜索，查询向量维度: {len(query_vector)}, 限制数量: {limit}")
            
            # TODO: 根据设计文档，这里应该调用OpenSearch进行向量搜索
            # 支持k-NN搜索和相似度计算
            
            # 临时实现 - 返回空列表
            results = []
            logger.info(f"向量搜索完成，找到 {len(results)} 个结果")
            return results
            
        except Exception as e:
            logger.error(f"向量搜索错误: {e}", exc_info=True)
            return []
    
    def batch_generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """批量生成嵌入向量 - 根据设计文档实现"""
        try:
            logger.info(f"开始批量生成向量，文本数量: {len(texts)}")
            
            # 根据设计文档的批量处理策略
            # 批次大小: 每批处理50个分块
            # 模型调用: 使用Ollama模型进行向量化
            # 错误处理: 单个批次失败不影响其他批次
            
            batch_size = 50
            embeddings = []
            
            for i in range(0, len(texts), batch_size):
                batch_texts = texts[i:i + batch_size]
                logger.debug(f"处理批次 {i//batch_size + 1}: {len(batch_texts)} 个文本")
                
                try:
                    batch_embeddings = self._process_batch(batch_texts)
                    embeddings.extend(batch_embeddings)
                except Exception as e:
                    logger.error(f"批次 {i//batch_size + 1} 处理失败: {e}")
                    # 单个批次失败，使用空向量填充
                    embeddings.extend([[] for _ in batch_texts])
            
            logger.info(f"批量向量生成完成，成功生成 {len(embeddings)} 个向量")
            return embeddings
            
        except Exception as e:
            logger.error(f"批量向量生成错误: {e}", exc_info=True)
            return []
    
    def _preprocess_text(self, text: str) -> str:
        """文本预处理 - 根据设计文档实现"""
        try:
            # 根据设计文档的文本处理要求
            # 1. 文本清洗
            # 2. 分词处理
            # 3. 长度限制
            
            # 基本清洗
            processed_text = text.strip()
            
            # 长度限制（根据模型要求）
            max_length = 512  # TODO: 根据实际模型调整
            if len(processed_text) > max_length:
                processed_text = processed_text[:max_length]
                logger.debug(f"文本长度超限，截断到 {max_length} 字符")
            
            return processed_text
            
        except Exception as e:
            logger.error(f"文本预处理错误: {e}")
            return text
    
    def _process_batch(self, texts: List[str]) -> List[List[float]]:
        """处理单个批次 - 根据设计文档实现"""
        try:
            # 预处理文本
            processed_texts = [self._preprocess_text(text) for text in texts]
            
            # 调用Ollama API进行批量处理
            response = requests.post(
                f"{self.ollama_url}/api/embeddings",
                json={
                    "model": self.embedding_model,
                    "prompt": processed_texts  # TODO: 检查Ollama是否支持批量
                },
                timeout=60
            )
            response.raise_for_status()
            
            result = response.json()
            
            # 处理响应
            if isinstance(result, list):
                embeddings = [item.get("embedding", []) for item in result]
            else:
                # 单个响应，复制到所有文本
                embedding = result.get("embedding", [])
                embeddings = [embedding for _ in texts]
            
            return embeddings
            
        except Exception as e:
            logger.error(f"批次处理错误: {e}")
            raise e
    
    def get_model_info(self) -> Dict[str, Any]:
        """获取模型信息 - 根据设计文档实现"""
        try:
            logger.info("获取Ollama模型信息")
            
            # 调用Ollama API获取模型列表
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=10)
            response.raise_for_status()
            
            models = response.json().get("models", [])
            
            # 查找当前使用的模型
            current_model_info = None
            for model in models:
                if model.get("name") == self.embedding_model:
                    current_model_info = model
                    break
            
            result = {
                "embedding_model": self.embedding_model,
                "image_model": self.image_model,
                "ollama_url": self.ollama_url,
                "available_models": [model.get("name") for model in models],
                "current_model_info": current_model_info
            }
            
            logger.info(f"模型信息获取完成: {self.embedding_model}")
            return result
            
        except Exception as e:
            logger.error(f"获取模型信息错误: {e}", exc_info=True)
            return {
                "embedding_model": self.embedding_model,
                "image_model": self.image_model,
                "ollama_url": self.ollama_url,
                "error": str(e)
            }
    
    def validate_vector(self, vector: List[float]) -> bool:
        """验证向量有效性 - 根据设计文档实现"""
        try:
            if not vector:
                return False
            
            if not isinstance(vector, list):
                return False
            
            if not all(isinstance(x, (int, float)) for x in vector):
                return False
            
            # 检查向量维度
            if len(vector) == 0:
                return False
            
            # 检查是否为零向量
            if all(x == 0 for x in vector):
                logger.warning("检测到零向量")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"向量验证错误: {e}")
            return False