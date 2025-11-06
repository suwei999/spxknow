"""
Rerank Service
使用bge-reranker模型对搜索结果进行重新排序
"""

from typing import List, Dict, Any, Optional, Tuple
import os
from app.core.logging import logger
from app.core.exceptions import CustomException, ErrorCode
from app.config.settings import settings


class RerankService:
    """Rerank服务 - 使用bge-reranker模型对搜索结果重新排序"""
    
    def __init__(self):
        self.model = None
        self.tokenizer = None
        self.enabled = settings.RERANK_ENABLED
        self.model_name = settings.RERANK_MODEL_NAME
        self.model_path = settings.RERANK_MODEL_PATH
        # 自动检测GPU可用性，如果配置为cuda但GPU不可用，降级到cpu
        self.device = self._get_device(settings.RERANK_DEVICE)
        self._initialize_model()
    
    def _get_device(self, configured_device: str) -> str:
        """获取实际使用的设备，自动检测GPU可用性
        
        Args:
            configured_device: 配置的设备（cpu/cuda）
            
        Returns:
            实际使用的设备（cpu/cuda）
        """
        # 如果配置为cpu，直接返回
        if configured_device.lower() == "cpu":
            return "cpu"
        
        # 如果配置为cuda，检查GPU是否可用
        if configured_device.lower() == "cuda":
            try:
                import torch
                if torch.cuda.is_available():
                    logger.info(f"检测到GPU可用，使用CUDA设备")
                    return "cuda"
                else:
                    logger.warning(f"配置为CUDA但GPU不可用，自动降级到CPU")
                    return "cpu"
            except ImportError:
                logger.warning(f"PyTorch未安装，无法使用CUDA，使用CPU")
                return "cpu"
            except Exception as e:
                logger.warning(f"检测GPU可用性失败: {e}，使用CPU")
                return "cpu"
        
        # 其他情况默认使用cpu
        logger.warning(f"未知的设备配置: {configured_device}，使用CPU")
        return "cpu"
    
    def _initialize_model(self):
        """初始化rerank模型 - 优先使用本地缓存，没有才联网下载"""
        if not self.enabled:
            logger.info("Rerank模型未启用，跳过初始化")
            return
        
        try:
            logger.info(f"开始初始化Rerank模型: {self.model_name}")
            
            # ⚠️ 关键：在检查模型之前设置 HF_HOME，确保模型下载到配置的目录
            # 优先使用 settings 中配置的 HF_HOME，否则使用 CLIP_CACHE_DIR 的父目录（如果存在）
            # 这样 FlagEmbedding 和 huggingface_hub 都会使用配置的缓存目录
            hf_home = None
            if settings.HF_HOME:
                hf_home = settings.HF_HOME
                logger.info(f"📁 使用配置的 HF_HOME: {hf_home}")
            elif settings.CLIP_CACHE_DIR:
                # 如果没有配置 HF_HOME，使用 CLIP_CACHE_DIR 的父目录（与CLIP模型保持一致）
                hf_home = os.path.dirname(settings.CLIP_CACHE_DIR)
                logger.info(f"📁 未配置 HF_HOME，使用 CLIP_CACHE_DIR 的父目录作为 HF_HOME: {hf_home}")
            else:
                hf_home = os.path.expanduser("~/.cache/huggingface")
                logger.info(f"📁 使用系统默认 HF_HOME: {hf_home}")
            
            # ⚠️ 关键：强制设置 HF_HOME 环境变量，确保模型下载到配置的目录
            os.environ["HF_HOME"] = hf_home  # 使用 = 而不是 setdefault，确保覆盖
            logger.info(f"✅ 已设置 HF_HOME 环境变量: {hf_home}")
            
            # 延迟导入，避免未安装时出错
            try:
                from FlagEmbedding import FlagReranker
            except ImportError:
                logger.warning(
                    "FlagEmbedding未安装，rerank功能将不可用。"
                    "请安装: pip install FlagEmbedding"
                )
                self.enabled = False
                return
            
            # ⚠️ 关键：优先检查本地缓存，按以下顺序：
            # 1. 配置的本地路径（如果存在）
            # 2. HF缓存目录（配置的或系统默认的）
            # 3. 最后才从网络下载
            
            model_found = False
            model_location = None
            
            # 1. 优先检查配置的本地路径
            if self.model_path and os.path.exists(self.model_path):
                model_found = True
                model_location = self.model_path
                logger.info(f"✅ 在配置的本地路径中发现Rerank模型: {self.model_path}")
                logger.info(f"🔧 正在从本地路径加载Rerank模型: {self.model_path}，设备: {self.device}")
                self.model = FlagReranker(self.model_path, use_fp16=False)
            else:
                # 2. 检查HF缓存目录（配置的或系统默认的）
                # FlagEmbedding 使用 huggingface_hub，会自动检查 HF_HOME 下的缓存
                # 如果模型已下载，FlagReranker 会自动使用缓存
                # 但我们需要先检查是否已缓存，避免不必要的网络请求
                hf_cache_dir = hf_home
                cached_model_path = None
                
                # 尝试在HF缓存目录中查找模型
                # HF缓存结构: ~/.cache/huggingface/hub/models--BAAI--bge-reranker-v2-m3/snapshots/xxx/
                if os.path.exists(hf_cache_dir):
                    try:
                        # 查找模型目录（FlagEmbedding使用huggingface_hub的缓存结构）
                        model_dir_name = self.model_name.replace("/", "--")  # BAAI/bge-reranker-v2-m3 -> BAAI--bge-reranker-v2-m3
                        hub_dir = os.path.join(hf_cache_dir, "hub")
                        if os.path.exists(hub_dir):
                            model_cache_dir = os.path.join(hub_dir, f"models--{model_dir_name}")
                            if os.path.exists(model_cache_dir):
                                # 查找snapshots目录
                                snapshots_dir = os.path.join(model_cache_dir, "snapshots")
                                if os.path.exists(snapshots_dir):
                                    # 获取最新的snapshot
                                    snapshots = [d for d in os.listdir(snapshots_dir) if os.path.isdir(os.path.join(snapshots_dir, d))]
                                    if snapshots:
                                        latest_snapshot = sorted(snapshots)[-1]
                                        cached_model_path = os.path.join(snapshots_dir, latest_snapshot)
                                        model_found = True
                                        model_location = cached_model_path
                                        logger.info(f"✅ 在HF缓存目录中发现Rerank模型: {cached_model_path}")
                                        logger.info(f"💡 FlagReranker将自动使用缓存中的模型，无需重新下载")
                    except Exception as e:
                        logger.debug(f"检查HF缓存目录时出错: {e}")
                
                # 3. 如果找到缓存，使用缓存（FlagReranker会自动使用）
                if model_found:
                    logger.info(f"🔧 正在从缓存加载Rerank模型: {self.model_name}，设备: {self.device}")
                    # FlagReranker会自动使用HF_HOME下的缓存，不需要指定路径
                    self.model = FlagReranker(self.model_name, use_fp16=False)
                else:
                    # 4. 如果本地缓存不存在，才从网络下载
                    if self.model_path:
                        logger.warning(f"⚠️ 配置的本地模型路径不存在: {self.model_path}")
                    logger.info(f"⚠️ 本地缓存中未发现Rerank模型: {self.model_name}")
                    logger.info(f"🌐 将允许联网下载模型（本地模型不存在）")
                    logger.info(f"💾 下载后的模型将保存到缓存目录: {hf_home}")
                    logger.info(f"🔧 正在从HuggingFace下载并加载Rerank模型: {self.model_name}，设备: {self.device}")
                    # FlagReranker会自动下载并保存到HF_HOME下的缓存目录
                    self.model = FlagReranker(self.model_name, use_fp16=False)
                    logger.info(f"✅ Rerank模型下载完成，已保存到: {hf_home}")
            
            # 如果模型支持手动设置设备，尝试设置（FlagReranker内部会自动处理）
            # 这里主要是记录实际使用的设备
            logger.info(f"✅ Rerank模型初始化成功: {self.model_name}，实际使用设备: {self.device}")
            if model_location:
                logger.info(f"📍 模型位置: {model_location}")
            
        except Exception as e:
            logger.error(f"Rerank模型初始化失败: {e}", exc_info=True)
            logger.warning("Rerank功能将不可用，将使用简单排序")
            self.enabled = False
            self.model = None
    
    def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_k: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """使用rerank模型对搜索结果重新排序
        
        Args:
            query: 查询文本
            candidates: 候选结果列表，每个结果包含 'content' 字段
            top_k: 返回前k个结果（如果为None，使用配置的默认值）
            
        Returns:
            重新排序后的结果列表
        """
        if not self.enabled or self.model is None:
            logger.debug("Rerank未启用或模型未加载，使用原始排序")
            # 降级：按原始分数排序
            sorted_candidates = sorted(
                candidates,
                key=lambda x: x.get("score", 0.0),
                reverse=True
            )
            top_k = top_k or settings.RERANK_TOP_K
            return sorted_candidates[:top_k]
        
        if not candidates:
            return []
        
        try:
            logger.info(f"开始Rerank排序，查询: {query[:50]}..., 候选数量: {len(candidates)}")
            
            # 准备rerank输入：query + 每个候选的content
            pairs = []
            for candidate in candidates:
                content = candidate.get("content", "")
                if not content:
                    continue
                pairs.append([query, content])
            
            if not pairs:
                logger.warning("没有有效的候选内容，返回空结果")
                return []
            
            # 使用rerank模型计算分数
            # FlagReranker.compute_score() 接受列表，返回numpy数组或列表
            import numpy as np
            try:
                # 方式1：批量计算（推荐）
                scores = self.model.compute_score(pairs, normalize=True)
                
                # 转换为列表
                if isinstance(scores, np.ndarray):
                    scores = scores.tolist()
                elif isinstance(scores, (list, tuple)):
                    scores = [float(s) for s in scores]
                elif isinstance(scores, (int, float)):
                    # 如果只有一个分数，转换为列表
                    scores = [float(scores)] * len(pairs)
                else:
                    logger.warning(f"Rerank返回的分数格式不支持: {type(scores)}")
                    scores = [0.0] * len(pairs)
                    
            except Exception as e:
                logger.warning(f"Rerank批量计算失败，尝试逐个计算: {e}")
                # 降级：逐个计算
                scores = []
                for pair in pairs:
                    query_text, passage_text = pair
                    try:
                        score = self.model.compute_score([pair], normalize=True)
                        if isinstance(score, np.ndarray):
                            score = float(score[0])
                        elif isinstance(score, (list, tuple)):
                            score = float(score[0])
                        else:
                            score = float(score)
                        scores.append(score)
                    except Exception as e2:
                        logger.warning(f"单个pair计算失败: {e2}")
                        scores.append(0.0)
            
            # 更新候选结果的分数
            valid_candidates = []
            score_idx = 0
            for candidate in candidates:
                content = candidate.get("content", "")
                if not content:
                    continue
                
                # 更新rerank分数
                rerank_score = float(scores[score_idx]) if score_idx < len(scores) else 0.0
                # 保存原始分数（融合分数）
                original_score = candidate.get("score", 0.0)
                candidate["original_score"] = original_score
                # 更新rerank分数
                candidate["rerank_score"] = rerank_score
                # 使用rerank分数作为最终分数
                candidate["score"] = rerank_score
                
                valid_candidates.append(candidate)
                score_idx += 1
            
            # 按rerank分数排序
            sorted_candidates = sorted(
                valid_candidates,
                key=lambda x: x.get("rerank_score", 0.0),
                reverse=True
            )
            
            # 返回top_k个结果
            top_k = top_k or settings.RERANK_TOP_K
            result = sorted_candidates[:top_k]
            
            logger.info(f"Rerank排序完成，返回 {len(result)} 个结果")
            return result
            
        except Exception as e:
            logger.error(f"Rerank排序失败: {e}", exc_info=True)
            logger.warning("Rerank失败，降级到简单排序")
            # 降级：按原始分数排序
            sorted_candidates = sorted(
                candidates,
                key=lambda x: x.get("score", 0.0),
                reverse=True
            )
            top_k = top_k or settings.RERANK_TOP_K
            return sorted_candidates[:top_k]
    
    def is_available(self) -> bool:
        """检查rerank模型是否可用"""
        return self.enabled and self.model is not None

