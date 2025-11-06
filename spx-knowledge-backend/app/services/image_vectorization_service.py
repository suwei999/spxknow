"""
Image Vectorization Service
根据文档处理流程设计实现CLIP/ResNet/ViT图片向量化功能
"""

import os
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from PIL import Image
import torch
import open_clip
import cv2
from app.core.logging import logger
from app.core.exceptions import CustomException, ErrorCode
from app.utils.download_progress import (
    log_download_start, 
    log_download_success, 
    log_download_error,
    setup_hf_download_progress
)

# 彻底移除对 torchvision 的导入，避免因环境不兼容导致应用启动失败
# 如果后续需要 ResNet/ViT，可在具备兼容环境时再按需引入

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
            from app.config.settings import settings as _settings
            
            # ⚠️ 重要：在检查模型之前就设置 HF_HOME，确保 open_clip 能找到缓存
            # 优先使用 settings.py 中配置的 HF_HOME，否则使用系统默认位置
            # 关键修复：如果配置了 CLIP_CACHE_DIR，应该优先使用配置的缓存目录作为 HF_HOME
            if _settings.HF_HOME:
                # 如果明确配置了 HF_HOME，使用配置的值
                hf_home = _settings.HF_HOME
                logger.info(f"📁 使用配置的 HF_HOME: {hf_home}")
            else:
                # 如果没有配置 HF_HOME，但配置了 CLIP_CACHE_DIR，优先使用 CLIP_CACHE_DIR 的父目录
                # 这样 open_clip 和 huggingface_hub 都会优先使用配置的缓存目录
                if _settings.CLIP_CACHE_DIR:
                    # 将 HF_HOME 设置为 CLIP_CACHE_DIR 的父目录（通常是 models/clip）
                    # 或者直接设置为 CLIP_CACHE_DIR（如果希望 HF 缓存直接放在这里）
                    hf_home = os.path.dirname(_settings.CLIP_CACHE_DIR)  # 例如：F:\spxknowlage\spx-knowledge-backend\models\clip
                    logger.info(f"📁 未配置 HF_HOME，使用 CLIP_CACHE_DIR 的父目录作为 HF_HOME: {hf_home}")
                else:
                    # 最后才使用系统默认位置
                    hf_home = os.path.expanduser("~/.cache/huggingface")
                    logger.info(f"📁 使用系统默认 HF_HOME: {hf_home}")
            
            # ⚠️ 关键：强制设置 HF_HOME 环境变量，确保 open_clip 和 huggingface_hub 使用配置的目录
            os.environ["HF_HOME"] = hf_home  # 使用 = 而不是 setdefault，确保覆盖任何默认值
            logger.info(f"✅ 已设置 HF_HOME 环境变量: {hf_home}")
            
            # 仅初始化CLIP，避免下载其他模型
            logger.info("初始化CLIP模型")
            # 准备本地目录（首次运行自动创建）
            try:
                os.makedirs(_settings.CLIP_MODELS_DIR, exist_ok=True)
                os.makedirs(_settings.CLIP_CACHE_DIR, exist_ok=True)
                logger.info(f"✅ CLIP模型目录已准备: {_settings.CLIP_MODELS_DIR}")
                logger.info(f"✅ CLIP缓存目录已准备: {_settings.CLIP_CACHE_DIR}")
            except Exception as e:
                logger.warning(f"创建CLIP目录失败: {e}")
            
            # ⚠️ 关键：设置 OPENCLIP_CACHE 环境变量，确保 open_clip 使用配置的缓存目录
            os.environ["OPENCLIP_CACHE"] = _settings.CLIP_CACHE_DIR  # 使用 = 而不是 setdefault，确保覆盖
            logger.info(f"✅ 已设置 OPENCLIP_CACHE 环境变量: {_settings.CLIP_CACHE_DIR}")

            # 检查本地权重文件是否存在
            model_name = getattr(_settings, 'CLIP_MODEL_NAME', 'ViT-B-32')
            model_full_name = f"{model_name} (CLIP)"
            
            # ⚠️ 重要：检查模型是否已存在（包括指定路径和缓存目录）
            # open_clip 库下载的模型可能缓存在 OPENCLIP_CACHE 目录中
            model_found = False
            model_location = None
            hf_cache_model_path = None  # Hugging Face Hub 缓存中的模型路径
            
            def _check_clip_model_in_directory(directory, desc=""):
                """在指定目录中查找 CLIP 模型文件"""
                if not os.path.exists(directory):
                    return None
                try:
                    # CLIP 模型可能是 .pt, .pth, .safetensors 等格式
                    model_extensions = ['.pt', '.pth', '.safetensors', '.bin']
                    for root, dirs, files in os.walk(directory):
                        for file in files:
                            # 检查是否是CLIP模型文件（通常包含模型名称或pretrained标识）
                            file_lower = file.lower()
                            if any(file_lower.endswith(ext) for ext in model_extensions):
                                # 检查文件名是否包含CLIP相关标识
                                if ('clip' in file_lower or 
                                    'vit-b-32' in file_lower or 
                                    'laion' in file_lower or
                                    'openclip' in file_lower):
                                    model_path = os.path.join(root, file)
                                    try:
                                        file_size = os.path.getsize(model_path)
                                        # CLIP模型通常>10MB
                                        if file_size > 10 * 1024 * 1024:  # 至少10MB
                                            return model_path
                                    except OSError:
                                        continue
                except Exception:
                    pass
                return None
            
            # 1. 优先检查指定路径
            if os.path.exists(_settings.CLIP_PRETRAINED_PATH):
                model_found = True
                model_location = _settings.CLIP_PRETRAINED_PATH
                pretrained_arg = _settings.CLIP_PRETRAINED_PATH
                logger.info(f"✅ 检测到本地CLIP模型权重: {_settings.CLIP_PRETRAINED_PATH}")
                logger.info(f"🔧 正在从本地加载 CLIP 模型: {model_name}")
            else:
                # 2. 检查 open_clip 缓存目录
                cached_model = _check_clip_model_in_directory(_settings.CLIP_CACHE_DIR, "CLIP缓存目录")
                if cached_model:
                    model_found = True
                    model_location = cached_model
                    # open_clip 会自动使用缓存，不需要指定路径；但需强制离线避免探测网络
                    pretrained_arg = "laion2b_s34b_b79k"
                    logger.info(f"✅ 在 CLIP 缓存目录中发现模型: {cached_model}")
                    logger.info(f"💡 open_clip 库将自动使用缓存中的模型，无需重新下载")
                    logger.info(f"🔧 正在从缓存加载 CLIP 模型: {model_name}")
                else:
                    # 3. 检查 Hugging Face 缓存位置（open_clip 可能使用 HF Hub）
                    # ⚠️ 关键修复：优先检查已设置的 HF_HOME（即配置的缓存目录），而不是系统默认位置
                    try:
                        # 使用已设置的 HF_HOME（已经在前面设置为配置的目录）
                        hf_cache_dir = os.environ.get("HF_HOME", os.path.expanduser("~/.cache/huggingface"))
                        cached_model = _check_clip_model_in_directory(hf_cache_dir, "HF缓存目录（配置的）")
                        if cached_model:
                            model_found = True
                            model_location = cached_model
                            hf_cache_model_path = cached_model
                            pretrained_arg = "laion2b_s34b_b79k"
                            logger.info(f"✅ 在配置的 HF 缓存目录中发现 CLIP 模型: {cached_model}")
                            logger.info(f"💡 open_clip 库将自动使用缓存中的模型，无需重新下载")
                            logger.info(f"🔧 正在从缓存加载 CLIP 模型: {model_name}")
                        else:
                            # 如果配置的目录中没有，再检查系统默认位置（作为最后的备选）
                            default_hf_cache = os.path.expanduser("~/.cache/huggingface")
                            if default_hf_cache != hf_cache_dir:
                                cached_model = _check_clip_model_in_directory(default_hf_cache, "HF缓存目录（系统默认）")
                                if cached_model:
                                    logger.warning(f"⚠️ 在系统默认缓存目录中发现模型，但配置的缓存目录中未找到: {cached_model}")
                                    logger.warning(f"⚠️ 建议将模型复制到配置的缓存目录: {_settings.CLIP_CACHE_DIR}")
                                    logger.warning(f"⚠️ 注意：系统将优先使用配置的缓存目录，不会使用系统默认缓存中的模型")
                                    logger.warning(f"⚠️ 如果希望使用系统默认缓存，请在 settings.py 中配置 HF_HOME 指向: {default_hf_cache}")
                                    # 注意：这里不设置 model_found = True，因为希望优先使用配置的目录
                                    # 如果用户希望使用系统默认缓存，可以手动配置 HF_HOME 指向默认位置
                    except Exception as e:
                        logger.debug(f"检查 HF 缓存目录时出错: {e}")
                
                # 如果模型不存在，才记录下载开始
                if not model_found:
                    logger.info(f"⚠️ 本地CLIP模型权重不存在: {_settings.CLIP_PRETRAINED_PATH}")
                    logger.info(f"⚠️ CLIP缓存目录中未发现模型: {_settings.CLIP_CACHE_DIR}")
                    logger.info("🌐 将允许联网下载模型（本地模型不存在）")
                    
                    # ✅ 重要：确保离线模式环境变量未设置，允许下载
                    # 清除任何可能阻止下载的离线模式设置
                    if "HF_HUB_OFFLINE" in os.environ:
                        old_offline = os.environ.pop("HF_HUB_OFFLINE", None)
                        logger.debug(f"已清除 HF_HUB_OFFLINE={old_offline}，允许下载")
                    if "TRANSFORMERS_OFFLINE" in os.environ:
                        old_transformers = os.environ.pop("TRANSFORMERS_OFFLINE", None)
                        logger.debug(f"已清除 TRANSFORMERS_OFFLINE={old_transformers}，允许下载")
                    if "HF_DATASETS_OFFLINE" in os.environ:
                        old_datasets = os.environ.pop("HF_DATASETS_OFFLINE", None)
                        logger.debug(f"已清除 HF_DATASETS_OFFLINE={old_datasets}，允许下载")
                    
                    # 设置 Hugging Face 下载进度显示
                    try:
                        # 启用 Hugging Face Hub 的进度显示
                        os.environ['HF_HUB_DISABLE_PROGRESS_BARS'] = '0'
                        # 尝试设置 tqdm 进度条
                        from huggingface_hub.utils import disable_progress_bars
                        disable_progress_bars(False)
                        logger.debug("✅ 已启用 Hugging Face 下载进度显示")
                    except Exception as e:
                        logger.debug(f"启用下载进度显示失败: {e}")
                    
                    # 记录下载开始信息
                    log_download_start(
                        model_name=model_full_name,
                        source="Hugging Face",
                        estimated_size="300-500 MB"
                    )
                    
                    pretrained_arg = "laion2b_s34b_b79k"
                    logger.info(f"🔧 正在下载并加载 CLIP 模型: {model_name}, pretrained={pretrained_arg}")
                    logger.info(f"💾 下载后的模型将保存到缓存目录: {_settings.CLIP_CACHE_DIR}")
            
            # 如果已找到本地/缓存模型，强制开启离线模式，避免任何网络探测
            if model_found:
                # 设置多个离线模式环境变量，确保所有库都遵守离线模式
                os.environ["HF_HUB_OFFLINE"] = "1"
                os.environ["TRANSFORMERS_OFFLINE"] = "1"
                os.environ["HF_DATASETS_OFFLINE"] = "1"
                # 强制 Hugging Face Hub 使用本地文件，禁止网络连接
                os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
                logger.info("🌐 已启用 HF 离线模式（发现本地/缓存模型，禁止联网探测）")
                logger.info(f"📍 模型位置: {model_location}")
                
                # ⚠️ 如果使用的是 Hugging Face Hub 缓存的模型，确保 HF_HOME 指向正确位置
                # 注意：如果模型在系统默认缓存中，但我们希望使用配置的缓存目录，这里不应该修改 HF_HOME
                if hf_cache_model_path:
                    # 检查模型路径是否在配置的缓存目录中
                    configured_hf_home = os.environ.get("HF_HOME", "")
                    if hf_cache_model_path.startswith(_settings.CLIP_CACHE_DIR) or hf_cache_model_path.startswith(configured_hf_home):
                        # 模型已经在配置的目录中，不需要修改 HF_HOME
                        logger.debug(f"✅ 模型已在配置的缓存目录中，无需修改 HF_HOME")
                    else:
                        # 模型在系统默认缓存中，但我们已经设置了 HF_HOME 指向配置的目录
                        # 这里不应该修改，因为我们已经强制使用配置的目录
                        logger.warning(f"⚠️ 发现模型在系统默认缓存中: {hf_cache_model_path}")
                        logger.warning(f"⚠️ 但已配置使用: {configured_hf_home}")
                        logger.warning(f"⚠️ 建议将模型复制到配置的缓存目录: {_settings.CLIP_CACHE_DIR}")
                        logger.warning(f"⚠️ 当前将继续使用配置的缓存目录，模型下载将保存到配置的目录")

            # 尝试加载模型，如果是下载过程，捕获下载相关错误
            try:
                # 如果找到本地模型，在调用 open_clip 之前再次确认离线模式设置
                if model_found:
                    # 确保所有离线模式环境变量都已设置（在调用前再次确认）
                    os.environ["HF_HUB_OFFLINE"] = "1"
                    os.environ["TRANSFORMERS_OFFLINE"] = "1"
                    os.environ["HF_DATASETS_OFFLINE"] = "1"
                    # 强制 Hugging Face Hub 使用本地文件，禁止任何网络连接
                    os.environ["HF_HUB_DISABLE_EXPERIMENTAL_WARNING"] = "1"
                    
                    # ✅ 关键修复：使用多种方式强制禁用网络连接
                    try:
                        # 方法1: 使用 huggingface_hub 的 offline_mode（如果支持）
                        try:
                            from huggingface_hub import offline_mode
                            offline_mode(True)
                            logger.info("✅ 已启用 huggingface_hub.offline_mode(True)")
                        except (ImportError, AttributeError):
                            pass
                        
                        # 方法2: 使用环境变量强制离线（已设置）
                        # 方法3: 临时禁用 Hugging Face 相关的网络请求（仅限 huggingface.co）
                        try:
                            import requests
                            from urllib.parse import urlparse
                            # 保存原始的 get 和 head 方法
                            original_get = requests.get
                            original_head = requests.head
                            
                            def disabled_get(url, *args, **kwargs):
                                """禁用 Hugging Face 相关的网络请求"""
                                if isinstance(url, str):
                                    parsed = urlparse(url)
                                    if 'huggingface.co' in parsed.netloc or 'hf.co' in parsed.netloc:
                                        raise ConnectionError(f"网络连接已禁用（离线模式），拒绝访问: {url}")
                                # 对于非 Hugging Face 的请求，允许通过
                                return original_get(url, *args, **kwargs)
                            
                            def disabled_head(url, *args, **kwargs):
                                """禁用 Hugging Face 相关的 HEAD 请求"""
                                if isinstance(url, str):
                                    parsed = urlparse(url)
                                    if 'huggingface.co' in parsed.netloc or 'hf.co' in parsed.netloc:
                                        raise ConnectionError(f"网络连接已禁用（离线模式），拒绝访问: {url}")
                                # 对于非 Hugging Face 的请求，允许通过
                                return original_head(url, *args, **kwargs)
                            
                            # 临时替换 requests 方法，仅禁用 Hugging Face 相关请求
                            requests.get = disabled_get
                            requests.head = disabled_head
                            logger.info("✅ 已临时禁用 Hugging Face 网络连接（仅用于模型加载）")
                            
                            # 加载模型
                            try:
                                clip_model, _, clip_preprocess = open_clip.create_model_and_transforms(
                                    model_name, pretrained=pretrained_arg, device=self.device
                                )
                                logger.info("✅ 成功从本地缓存加载 CLIP 模型（未联网）")
                            finally:
                                # 恢复原始的 requests 方法
                                requests.get = original_get
                                requests.head = original_head
                                logger.debug("✅ 已恢复 requests 网络连接")
                        except Exception as req_err:
                            logger.warning(f"禁用 Hugging Face 网络连接失败，使用标准离线模式: {req_err}")
                            # 回退到标准加载方式（依赖环境变量）
                            clip_model, _, clip_preprocess = open_clip.create_model_and_transforms(
                                model_name, pretrained=pretrained_arg, device=self.device
                            )
                    except Exception as offline_err:
                        logger.warning(f"强制离线模式设置失败，回退到标准方式: {offline_err}")
                        # 最后的回退：使用标准加载方式
                        clip_model, _, clip_preprocess = open_clip.create_model_and_transforms(
                            model_name, pretrained=pretrained_arg, device=self.device
                        )
                else:
                    # ✅ 模型不存在，允许下载（不设置离线模式）
                    logger.info("🌐 允许联网下载（本地模型不存在）")
                    logger.info(f"📥 正在从 Hugging Face 下载模型: {pretrained_arg}")
                    clip_model, _, clip_preprocess = open_clip.create_model_and_transforms(
                        model_name, pretrained=pretrained_arg, device=self.device
                    )
                    logger.info("✅ 模型下载完成")
                
                # 如果是从网络下载的（模型不在缓存中），记录成功
                if not model_found:
                    log_download_success(
                        model_name=model_full_name,
                        save_path=_settings.CLIP_CACHE_DIR
                    )
                
                logger.info("✅ CLIP模型加载完成，正在移动到设备...")
            except Exception as download_error:
                # 判断是否是下载相关的错误
                error_str = str(download_error).lower()
                is_download_error = any(keyword in error_str for keyword in [
                    'download', 'huggingface', 'hub', 'network', 'connection', 
                    'timeout', 'unpack', 'http', 'https', 'ssl', 'certificate'
                ])
                
                if is_download_error:
                    # 使用统一的错误日志格式
                    log_download_error(
                        model_name=model_full_name,
                        error=download_error,
                        download_url="https://huggingface.co/laion/CLIP-ViT-B-32-xlaion2b-s34b-b79k",
                        local_path=_settings.CLIP_PRETRAINED_PATH,
                        readme_path="models/clip/README.md"
                    )
                    
                    raise CustomException(
                        code=ErrorCode.VECTOR_GENERATION_FAILED,
                        message=f"CLIP模型下载失败: {str(download_error)}。请检查网络连接或手动下载模型到 {_settings.CLIP_PRETRAINED_PATH}。详见 models/clip/README.md"
                    )
                else:
                    # 其他类型的错误（如模型加载、格式错误等）
                    logger.error(f"❌ CLIP模型加载失败（非下载错误）: {download_error}")
                    raise
            
            clip_model.eval()
            clip_model.to(self.device)
            self.models['clip'] = clip_model
            self.transforms['clip'] = clip_preprocess
            logger.info("✅ CLIP模型初始化完成，已加载到设备")
            
            # 关闭 ResNet/ViT 以避免联网下载
            
            logger.info("✅ 所有视觉模型初始化完成")
            
        except CustomException:
            # 重新抛出自定义异常
            raise
        except Exception as e:
            logger.error(f"❌ 模型初始化失败: {e}", exc_info=True)
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
    
    def generate_clip_text_embedding(self, text: str) -> List[float]:
        """使用CLIP文本编码器生成文本向量（512维）
        
        Args:
            text: 输入文本（如用户查询文本）
            
        Returns:
            512维向量列表
        """
        try:
            logger.info(f"开始CLIP文本向量化: {text[:50]}...")
            
            # 检查CLIP模型是否已加载
            if 'clip' not in self.models:
                raise CustomException(
                    code=ErrorCode.VECTOR_GENERATION_FAILED,
                    message="CLIP模型未初始化"
                )
            
            clip_model = self.models['clip']
            
            # 对文本进行tokenize
            # open_clip.tokenize 返回的是 torch.Tensor，需要移动到device
            text_tokens = open_clip.tokenize([text]).to(self.device)
            
            # 使用CLIP文本编码器
            with torch.no_grad():
                text_features = clip_model.encode_text(text_tokens)
                # 归一化特征向量（与图像向量处理方式一致）
                text_features = text_features / text_features.norm(dim=-1, keepdim=True)
                embedding = text_features.cpu().numpy().flatten().tolist()
            
            if not embedding or len(embedding) != 512:
                logger.error(f"CLIP文本向量生成失败或维度不正确: {len(embedding) if embedding else 0}")
                raise CustomException(
                    code=ErrorCode.VECTOR_GENERATION_FAILED,
                    message=f"CLIP文本向量生成失败或维度不正确: 期望512维，实际{len(embedding) if embedding else 0}维"
                )
            
            logger.info(f"CLIP文本向量化完成，向量维度: {len(embedding)}")
            return embedding
            
        except CustomException:
            raise
        except Exception as e:
            logger.error(f"CLIP文本向量化错误: {e}", exc_info=True)
            raise CustomException(
                code=ErrorCode.VECTOR_GENERATION_FAILED,
                message=f"CLIP文本向量化失败: {str(e)}"
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
