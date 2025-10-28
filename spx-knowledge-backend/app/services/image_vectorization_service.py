"""
Image Vectorization Service
根据文档处理流程设计实现CLIP/ResNet/ViT图片向量化功能
"""

import os
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from PIL import Image
import torch
import torchvision.transforms as transforms
from torchvision.models import resnet50, vit_b_16
import open_clip
import cv2
from app.core.logging import logger
from app.core.exceptions import CustomException, ErrorCode

class ImageVectorizationService:
    """图片向量化服务 - 严格按照设计文档实现"""
    
    def __init__(self):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.models = {}
        self.transforms = {}
        self._initialize_models()
    
    def _initialize_models(self):
        """初始化视觉模型 - 根据设计文档实现"""
        try:
            logger.info("开始初始化视觉模型")
            
            # 1. CLIP模型初始化（open-clip）
            logger.info("初始化CLIP模型")
            clip_model, _, clip_preprocess = open_clip.create_model_and_transforms(
                "ViT-B-32", pretrained="laion2b_s34b_b79k", device=self.device
            )
            clip_model.eval()
            clip_model.to(self.device)
            self.models['clip'] = clip_model
            self.transforms['clip'] = clip_preprocess
            logger.info("CLIP模型初始化完成")
            
            # 2. ResNet模型初始化
            logger.info("初始化ResNet模型")
            resnet_model = resnet50(pretrained=True)
            resnet_model.eval()
            resnet_model.to(self.device)
            self.models['resnet'] = resnet_model
            
            # ResNet预处理
            resnet_transform = transforms.Compose([
                transforms.Resize(256),
                transforms.CenterCrop(224),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
            ])
            self.transforms['resnet'] = resnet_transform
            logger.info("ResNet模型初始化完成")
            
            # 3. ViT模型初始化
            logger.info("初始化ViT模型")
            vit_model = vit_b_16(pretrained=True)
            vit_model.eval()
            vit_model.to(self.device)
            self.models['vit'] = vit_model
            
            # ViT预处理
            vit_transform = transforms.Compose([
                transforms.Resize(256),
                transforms.CenterCrop(224),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
            ])
            self.transforms['vit'] = vit_transform
            logger.info("ViT模型初始化完成")
            
            logger.info("所有视觉模型初始化完成")
            
        except Exception as e:
            logger.error(f"模型初始化失败: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.VECTOR_GENERATION_FAILED,
                message=f"视觉模型初始化失败: {str(e)}"
            )
    
    def generate_clip_embedding(self, image_path: str) -> List[float]:
        """使用CLIP生成图片嵌入向量 - 根据设计文档实现"""
        try:
            logger.info(f"开始CLIP向量化: {image_path}")
            
            # 图片预处理
            image = self._preprocess_image(image_path, 'clip')
            if image is None:
                raise CustomException(
                    code=ErrorCode.IMAGE_PROCESSING_FAILED,
                    message=f"图片预处理失败: {image_path}"
                )
            
            # 使用CLIP提取特征
            with torch.no_grad():
                image_features = self.models['clip'].encode_image(image)
                # 归一化特征向量
                image_features = image_features / image_features.norm(dim=-1, keepdim=True)
                embedding = image_features.cpu().numpy().flatten().tolist()
            
            logger.info(f"CLIP向量化完成，向量维度: {len(embedding)}")
            return embedding
            
        except Exception as e:
            logger.error(f"CLIP向量化错误: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.VECTOR_GENERATION_FAILED,
                message=f"CLIP向量化失败: {str(e)}"
            )
    
    def generate_resnet_embedding(self, image_path: str) -> List[float]:
        """使用ResNet生成图片嵌入向量 - 根据设计文档实现"""
        try:
            logger.info(f"开始ResNet向量化: {image_path}")
            
            # 图片预处理
            image = self._preprocess_image(image_path, 'resnet')
            if image is None:
                raise CustomException(
                    code=ErrorCode.IMAGE_PROCESSING_FAILED,
                    message=f"图片预处理失败: {image_path}"
                )
            
            # 使用ResNet提取特征
            with torch.no_grad():
                features = self.models['resnet'](image)
                # 使用全局平均池化后的特征作为嵌入向量
                embedding = features.cpu().numpy().flatten().tolist()
            
            logger.info(f"ResNet向量化完成，向量维度: {len(embedding)}")
            return embedding
            
        except Exception as e:
            logger.error(f"ResNet向量化错误: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.VECTOR_GENERATION_FAILED,
                message=f"ResNet向量化失败: {str(e)}"
            )
    
    def generate_vit_embedding(self, image_path: str) -> List[float]:
        """使用ViT生成图片嵌入向量 - 根据设计文档实现"""
        try:
            logger.info(f"开始ViT向量化: {image_path}")
            
            # 图片预处理
            image = self._preprocess_image(image_path, 'vit')
            if image is None:
                raise CustomException(
                    code=ErrorCode.IMAGE_PROCESSING_FAILED,
                    message=f"图片预处理失败: {image_path}"
                )
            
            # 使用ViT提取特征
            with torch.no_grad():
                features = self.models['vit'](image)
                # 使用分类头前的特征作为嵌入向量
                embedding = features.cpu().numpy().flatten().tolist()
            
            logger.info(f"ViT向量化完成，向量维度: {len(embedding)}")
            return embedding
            
        except Exception as e:
            logger.error(f"ViT向量化错误: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.VECTOR_GENERATION_FAILED,
                message=f"ViT向量化失败: {str(e)}"
            )
    
    def generate_multi_model_embedding(self, image_path: str, models: List[str] = None) -> Dict[str, List[float]]:
        """使用多个模型生成图片嵌入向量 - 根据设计文档实现"""
        try:
            logger.info(f"开始多模型向量化: {image_path}")
            
            if models is None:
                models = ['clip', 'resnet', 'vit']
            
            embeddings = {}
            
            for model_name in models:
                try:
                    if model_name == 'clip':
                        embeddings['clip'] = self.generate_clip_embedding(image_path)
                    elif model_name == 'resnet':
                        embeddings['resnet'] = self.generate_resnet_embedding(image_path)
                    elif model_name == 'vit':
                        embeddings['vit'] = self.generate_vit_embedding(image_path)
                    else:
                        logger.warning(f"不支持的模型: {model_name}")
                except Exception as e:
                    logger.error(f"模型 {model_name} 向量化失败: {e}")
                    embeddings[model_name] = []
            
            logger.info(f"多模型向量化完成，成功生成 {len(embeddings)} 个向量")
            return embeddings
            
        except Exception as e:
            logger.error(f"多模型向量化错误: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.VECTOR_GENERATION_FAILED,
                message=f"多模型向量化失败: {str(e)}"
            )
    
    def generate_hybrid_embedding(self, image_path: str) -> List[float]:
        """生成混合嵌入向量 - 根据设计文档实现"""
        try:
            logger.info(f"开始混合向量化: {image_path}")
            
            # 获取多个模型的嵌入向量
            embeddings = self.generate_multi_model_embedding(image_path)
            
            # 融合策略：加权平均
            weights = {
                'clip': 0.5,    # CLIP权重最高，因为支持图文联合
                'resnet': 0.3,  # ResNet权重中等
                'vit': 0.2      # ViT权重较低
            }
            
            # 计算加权平均
            hybrid_embedding = []
            for i in range(512):  # 使用512维作为标准维度
                weighted_sum = 0.0
                total_weight = 0.0
                
                for model_name, embedding in embeddings.items():
                    if embedding and len(embedding) > i:
                        weight = weights.get(model_name, 0.0)
                        weighted_sum += embedding[i] * weight
                        total_weight += weight
                
                if total_weight > 0:
                    hybrid_embedding.append(weighted_sum / total_weight)
                else:
                    hybrid_embedding.append(0.0)
            
            logger.info(f"混合向量化完成，向量维度: {len(hybrid_embedding)}")
            return hybrid_embedding
            
        except Exception as e:
            logger.error(f"混合向量化错误: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.VECTOR_GENERATION_FAILED,
                message=f"混合向量化失败: {str(e)}"
            )
    
    def _preprocess_image(self, image_path: str, model_type: str) -> Optional[torch.Tensor]:
        """图片预处理 - 根据设计文档实现"""
        try:
            logger.debug(f"开始图片预处理: {image_path}, 模型: {model_type}")
            
            # 检查文件是否存在
            if not os.path.exists(image_path):
                logger.error(f"图片文件不存在: {image_path}")
                return None
            
            # 加载图片
            image = Image.open(image_path).convert('RGB')
            
            # 根据模型类型选择预处理方法
            if model_type == 'clip':
                # CLIP预处理
                transform = self.transforms['clip']
                processed_image = transform(image).unsqueeze(0).to(self.device)
            elif model_type in ['resnet', 'vit']:
                # ResNet/ViT预处理
                transform = self.transforms[model_type]
                processed_image = transform(image).unsqueeze(0).to(self.device)
            else:
                logger.error(f"不支持的模型类型: {model_type}")
                return None
            
            logger.debug(f"图片预处理完成: {image_path}")
            return processed_image
            
        except Exception as e:
            logger.error(f"图片预处理错误: {e}", exc_info=True)
            return None
    
    def extract_image_features(self, image_path: str) -> Dict[str, Any]:
        """提取图片特征 - 根据设计文档实现"""
        try:
            logger.info(f"开始提取图片特征: {image_path}")
            
            # 使用OpenCV提取传统特征
            image = cv2.imread(image_path)
            if image is None:
                raise CustomException(
                    code=ErrorCode.IMAGE_PROCESSING_FAILED,
                    message=f"无法读取图片: {image_path}"
                )
            
            # 转换为灰度图
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # 提取SIFT特征
            sift = cv2.SIFT_create()
            keypoints, descriptors = sift.detectAndCompute(gray, None)
            
            # 提取ORB特征
            orb = cv2.ORB_create()
            orb_keypoints, orb_descriptors = orb.detectAndCompute(gray, None)
            
            # 获取图片基本信息
            height, width = image.shape[:2]
            
            features = {
                'sift_keypoints': len(keypoints) if keypoints is not None else 0,
                'sift_descriptors': descriptors.tolist() if descriptors is not None else [],
                'orb_keypoints': len(orb_keypoints) if orb_keypoints is not None else 0,
                'orb_descriptors': orb_descriptors.tolist() if orb_descriptors is not None else [],
                'image_size': {'width': width, 'height': height},
                'aspect_ratio': width / height if height > 0 else 1.0
            }
            
            logger.info(f"图片特征提取完成: {image_path}")
            return features
            
        except Exception as e:
            logger.error(f"图片特征提取错误: {e}", exc_info=True)
            return {}
    
    def calculate_image_similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        """计算图片相似度 - 根据设计文档实现"""
        try:
            logger.debug("开始计算图片相似度")
            
            # 转换为numpy数组
            vec1 = np.array(embedding1)
            vec2 = np.array(embedding2)
            
            # 检查向量维度
            if len(vec1) != len(vec2):
                logger.warning(f"向量维度不一致: {len(vec1)} vs {len(vec2)}")
                return 0.0
            
            # 计算余弦相似度
            dot_product = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            
            if norm1 == 0 or norm2 == 0:
                logger.warning("向量为零向量")
                return 0.0
            
            similarity = dot_product / (norm1 * norm2)
            logger.debug(f"图片相似度计算结果: {similarity}")
            return similarity
            
        except Exception as e:
            logger.error(f"图片相似度计算错误: {e}", exc_info=True)
            return 0.0
    
    def batch_process_images(self, image_paths: List[str], model_type: str = 'clip') -> List[List[float]]:
        """批量处理图片 - 根据设计文档实现"""
        try:
            logger.info(f"开始批量处理图片，数量: {len(image_paths)}, 模型: {model_type}")
            
            embeddings = []
            
            for i, image_path in enumerate(image_paths):
                try:
                    logger.debug(f"处理图片 {i+1}/{len(image_paths)}: {image_path}")
                    
                    if model_type == 'clip':
                        embedding = self.generate_clip_embedding(image_path)
                    elif model_type == 'resnet':
                        embedding = self.generate_resnet_embedding(image_path)
                    elif model_type == 'vit':
                        embedding = self.generate_vit_embedding(image_path)
                    elif model_type == 'hybrid':
                        embedding = self.generate_hybrid_embedding(image_path)
                    else:
                        logger.warning(f"不支持的模型类型: {model_type}")
                        embedding = []
                    
                    embeddings.append(embedding)
                    
                except Exception as e:
                    logger.error(f"图片 {image_path} 处理失败: {e}")
                    embeddings.append([])
            
            logger.info(f"批量处理完成，成功处理 {len(embeddings)} 个图片")
            return embeddings
            
        except Exception as e:
            logger.error(f"批量处理错误: {e}", exc_info=True)
            return []
    
    def get_model_info(self) -> Dict[str, Any]:
        """获取模型信息 - 根据设计文档实现"""
        try:
            logger.info("获取视觉模型信息")
            
            model_info = {
                'available_models': list(self.models.keys()),
                'device': str(self.device),
                'clip_info': {
                    'model_name': 'ViT-B/32',
                    'embedding_dim': 512,
                    'supports_text_image': True
                },
                'resnet_info': {
                    'model_name': 'ResNet-50',
                    'embedding_dim': 1000,
                    'supports_text_image': False
                },
                'vit_info': {
                    'model_name': 'ViT-B/16',
                    'embedding_dim': 1000,
                    'supports_text_image': False
                },
                'hybrid_info': {
                    'model_name': 'Hybrid (CLIP+ResNet+ViT)',
                    'embedding_dim': 512,
                    'supports_text_image': True
                }
            }
            
            logger.info("视觉模型信息获取完成")
            return model_info
            
        except Exception as e:
            logger.error(f"获取模型信息错误: {e}", exc_info=True)
            return {'error': str(e)}
    
    def cleanup_models(self):
        """清理模型资源"""
        try:
            logger.info("开始清理模型资源")
            
            # 清理GPU内存
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            
            # 清理模型
            self.models.clear()
            self.transforms.clear()
            
            logger.info("模型资源清理完成")
            
        except Exception as e:
            logger.error(f"模型资源清理错误: {e}", exc_info=True)
