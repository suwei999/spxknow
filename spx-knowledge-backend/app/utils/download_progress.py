"""
下载进度回调工具
用于显示模型下载进度和错误处理
"""

import os
import sys
from typing import Optional, Callable
from app.core.logging import logger


class DownloadProgressCallback:
    """Hugging Face 模型下载进度回调"""
    
    def __init__(self, model_name: str, total_size: Optional[int] = None):
        self.model_name = model_name
        self.total_size = total_size
        self.downloaded_size = 0
        self.last_logged_percent = -1
        
    def __call__(self, bytes_downloaded: int, total_bytes: Optional[int] = None):
        """进度回调函数"""
        if total_bytes:
            self.total_size = total_bytes
        
        self.downloaded_size = bytes_downloaded
        
        if self.total_size and self.total_size > 0:
            percent = int((bytes_downloaded / self.total_size) * 100)
            # 每 10% 或完成时记录一次日志
            if percent >= self.last_logged_percent + 10 or percent >= 100:
                self.last_logged_percent = percent
                size_mb = bytes_downloaded / (1024 * 1024)
                total_mb = self.total_size / (1024 * 1024)
                logger.info(f"📥 {self.model_name} 下载进度: {percent}% ({size_mb:.1f}MB / {total_mb:.1f}MB)")
        else:
            # 不知道总大小，显示已下载大小
            size_mb = bytes_downloaded / (1024 * 1024)
            logger.debug(f"📥 {self.model_name} 已下载: {size_mb:.1f}MB")


def setup_hf_download_progress(model_name: str):
    """
    设置 Hugging Face Hub 下载进度显示
    
    参数:
        model_name: 模型名称（用于日志显示）
    
    返回:
        进度回调函数
    """
    try:
        from huggingface_hub.utils import tqdm
        
        def progress_callback(bytes_downloaded: int, total_bytes: Optional[int] = None):
            callback = DownloadProgressCallback(model_name, total_bytes)
            callback(bytes_downloaded, total_bytes)
        
        return progress_callback
    except ImportError:
        # 如果没有 tqdm，返回简单的回调
        logger.warning(f"⚠️ 无法加载 tqdm，将使用简化进度显示")
        return DownloadProgressCallback(model_name)
    except Exception as e:
        logger.warning(f"⚠️ 设置下载进度回调失败: {e}")
        return None


def log_download_start(model_name: str, source: str, estimated_size: Optional[str] = None):
    """
    记录下载开始日志
    
    参数:
        model_name: 模型名称
        source: 下载源（如 "Hugging Face"）
        estimated_size: 预估大小（如 "300MB"）
    """
    logger.info(f"📥 开始下载 {model_name} 模型...")
    logger.info(f"   来源: {source}")
    if estimated_size:
        logger.info(f"   预估大小: {estimated_size}")
    logger.info(f"⏳ 下载可能需要几分钟，请耐心等待...")


def log_download_success(model_name: str, save_path: Optional[str] = None):
    """
    记录下载成功日志
    
    参数:
        model_name: 模型名称
        save_path: 保存路径（可选）
    """
    logger.info(f"✅ {model_name} 模型下载完成")
    if save_path:
        logger.info(f"   保存位置: {save_path}")


def log_download_error(model_name: str, error: Exception, download_url: Optional[str] = None, 
                       local_path: Optional[str] = None, readme_path: Optional[str] = None):
    """
    记录下载失败日志（包含详细的解决方案）
    
    参数:
        model_name: 模型名称
        error: 错误对象
        download_url: 下载地址（可选）
        local_path: 本地保存路径（可选）
        readme_path: README 文档路径（可选）
    """
    logger.error("=" * 60)
    logger.error(f"❌ {model_name} 模型下载失败")
    logger.error("=" * 60)
    logger.error(f"错误类型: {type(error).__name__}")
    logger.error(f"错误详情: {error}")
    logger.error("")
    logger.error("💡 解决方案：")
    logger.error("")
    logger.error("方案一：检查网络连接")
    logger.error("   1. 确保可以访问 Hugging Face (huggingface.co)")
    logger.error("   2. 检查防火墙和代理设置")
    logger.error("   3. 如果网络受限，可以设置代理：")
    logger.error("      export HTTP_PROXY=http://proxy.example.com:8080")
    logger.error("      export HTTPS_PROXY=http://proxy.example.com:8080")
    logger.error("")
    logger.error("方案二：手动下载模型（推荐）")
    if download_url:
        logger.error(f"   1. 下载地址: {download_url}")
    if local_path:
        logger.error(f"   2. 保存到: {local_path}")
    logger.error("   3. 下载完成后重启服务")
    logger.error("")
    logger.error("方案三：使用 Python 脚本下载")
    logger.error("   ```python")
    logger.error(f"   # 示例代码")
    logger.error("   import open_clip")
    logger.error("   model, _, _ = open_clip.create_model_and_transforms('ViT-B-32', pretrained='laion2b_s34b_b79k')")
    logger.error("   ```")
    logger.error("")
    if readme_path:
        logger.error(f"📖 详细说明请查看: {readme_path}")
    logger.error("=" * 60)

