"""
Configuration Management
"""

from pydantic_settings import BaseSettings
from typing import List, Optional
import os

# 计算项目根目录，确保无论从哪里运行都能找到根目录下的 .env
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_APP_DIR = os.path.dirname(_CURRENT_DIR)
_PROJECT_ROOT = os.path.dirname(_APP_DIR)
_ENV_FILE = os.path.join(_PROJECT_ROOT, ".env")

class Settings(BaseSettings):
    """应用配置"""
    
    # 应用配置
    APP_NAME: str = "SPX Knowledge Base"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # 服务器配置
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    ALLOWED_HOSTS: List[str] = ["*"]
    
    # 数据库配置
    DATABASE_URL: str = "mysql+pymysql://user:password@localhost:3306/spx_knowledge"
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "user"
    MYSQL_PASSWORD: str = "password"
    MYSQL_DATABASE: str = "spx_knowledge"
    
    # Redis配置
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_DB: int = 0
    
    # OpenSearch配置（统一仅使用 OPENSEARCH_URL）
    OPENSEARCH_URL: str = "http://localhost:9200"
    OPENSEARCH_USERNAME: str = ""
    OPENSEARCH_PASSWORD: str = ""
    OPENSEARCH_USE_SSL: bool = False
    OPENSEARCH_VERIFY_CERTS: bool = False
    
    # MinIO配置（与 docker-compose 保持一致：ROOT_USER/ROOT_PASSWORD）
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ROOT_USER: str = "minioadmin"
    MINIO_ROOT_PASSWORD: str = "minioadmin"
    MINIO_BUCKET_NAME: str = "spx-knowledge-base"
    MINIO_SECURE: bool = False
    
    # Ollama配置
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_API_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama2"
    OLLAMA_EMBEDDING_MODEL: str = "nomic-embed-text"
    # 图片向量配置（默认本地CLIP ViT-B/32，512维）
    OLLAMA_IMAGE_MODEL: str = "local"  # 兼容旧字段，不通过Ollama
    IMAGE_EMBEDDING_MODEL: str = "clip_vit_b32"
    CLIP_MODEL_NAME: str = "ViT-B-32"
    # 本地权重与缓存默认目录（位于项目根目录 models/clip/ 下）
    CLIP_MODELS_DIR: str = os.path.join(_PROJECT_ROOT, "models", "clip")
    # 本地权重路径（若不存在将自动创建目录并允许首轮下载到该路径所在目录）
    CLIP_PRETRAINED_PATH: str = os.path.join(CLIP_MODELS_DIR, "ViT-B-32-openclip.pt")
    # 模型本地缓存目录（OpenCLIP/HF 缓存）
    CLIP_CACHE_DIR: str = os.path.join(CLIP_MODELS_DIR, "cache")

    # 图片处理流水线模式：memory | temp
    # memory：优先走内存管道（BytesIO/数组），失败自动回退到临时文件
    # temp：始终使用临时文件
    IMAGE_PIPELINE_MODE: str = "memory"

    # 调试时是否保留临时文件（仅当使用临时文件路径时有效）
    DEBUG_KEEP_TEMP_FILES: bool = False
    
    # QA系统配置
    QA_DEFAULT_PAGE_SIZE: int = 20
    QA_MAX_PAGE_SIZE: int = 100
    QA_DEFAULT_SIMILARITY_THRESHOLD: float = 0.7
    QA_DEFAULT_MAX_SOURCES: int = 10
    QA_DEFAULT_MAX_HISTORY: int = 5
    QA_DEFAULT_MAX_RESULTS: int = 10
    
    # 多模态处理配置
    MULTIMODAL_TEXT_MAX_LENGTH: int = 10000
    MULTIMODAL_IMAGE_MAX_SIZE_MB: int = 10
    MULTIMODAL_IMAGE_MAX_DIMENSION: int = 1024
    MULTIMODAL_MAX_KEYWORDS: int = 10
    MULTIMODAL_DEFAULT_FUSION_SCORE: float = 0.8
    MULTIMODAL_DEFAULT_SEMANTIC_SIMILARITY: float = 0.7
    MULTIMODAL_DEFAULT_RELEVANCE_SCORE: float = 0.7
    MULTIMODAL_DEFAULT_CONSISTENCY_SCORE: float = 0.8
    
    # 降级策略配置
    FALLBACK_HIGH_RELEVANCE_THRESHOLD: float = 0.8
    FALLBACK_MEDIUM_RELEVANCE_THRESHOLD: float = 0.5
    FALLBACK_LOW_RELEVANCE_THRESHOLD: float = 0.3
    FALLBACK_SIMILARITY_WEIGHT: float = 0.4
    FALLBACK_MATCH_WEIGHT: float = 0.3
    FALLBACK_COMPLETENESS_WEIGHT: float = 0.2
    FALLBACK_ACCURACY_WEIGHT: float = 0.1
    
    # 历史存储配置
    QA_HISTORY_INDEX_NAME: str = "qa_history"
    QA_HISTORY_CLEANUP_DAYS: int = 90
    QA_HISTORY_DEFAULT_PAGE_SIZE: int = 20
    QA_HISTORY_MAX_PAGE_SIZE: int = 100
    
    # 向量维度配置
    TEXT_EMBEDDING_DIMENSION: int = 768
    IMAGE_EMBEDDING_DIMENSION: int = 512
    # 文本向量模型可接受的最大字符数（用于分块与预处理上限对齐）
    TEXT_EMBED_MAX_CHARS: int = 1024
    
    # 实体识别配置
    ENTITY_PERSON_CONFIDENCE: float = 0.8
    ENTITY_PLACE_CONFIDENCE: float = 0.7
    
    # 意图识别配置
    INTENT_FACTUAL_CONFIDENCE: float = 0.8
    INTENT_OPERATION_CONFIDENCE: float = 0.8
    INTENT_COMPARISON_CONFIDENCE: float = 0.7
    INTENT_DEFAULT_CONFIDENCE: float = 0.5
    
    # 图片搜索配置
    IMAGE_SEARCH_DEFAULT_CONFIDENCE: float = 0.8
    IMAGE_SEARCH_MULTIMODAL_CONFIDENCE: float = 0.7
    IMAGE_SEARCH_DEFAULT_CONFIDENCE_FALLBACK: float = 0.5

    # 内容预览配置
    CONTENT_PREVIEW_LENGTH: int = 100
    
    # 批量操作配置
    MAX_BATCH_OPERATION_SIZE: int = 10
    
    # 缓存配置
    CACHE_TTL_SECONDS: int = 3600
    CACHE_MAX_SIZE: int = 1000
    CACHE_CLEANUP_INTERVAL: int = 300
    
    # 内容验证配置
    MAX_NEWLINE_RATIO: float = 0.5
    MAX_SPECIAL_CHAR_RATIO: float = 0.1
    MIN_CHINESE_RATIO: float = 0.3
    MIN_ENGLISH_RATIO: float = 0.3
    
    # 降级策略置信度调整
    FALLBACK_CONFIDENCE_BOOST: float = 0.2
    FALLBACK_DEFAULT_CONFIDENCE: float = 0.5
    
    # 文件验证配置
    FILE_HEADER_READ_SIZE: int = 1024  # 读取文件头的大小（字节）
    
    # 安全配置
    SECRET_KEY: str = "your-secret-key-here"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # 日志配置
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOG_FILE: str = "logs/app.log"
    
    # 环境配置
    ENVIRONMENT: str = "development"
    
    # ClamAV配置
    CLAMAV_ENABLED: bool = True  # 是否启用ClamAV病毒扫描
    CLAMAV_SOCKET_PATH: Optional[str] = None  # Socket路径，None表示自动检测。优先级最高
    CLAMAV_TCP_HOST: Optional[str] = "localhost"  # TCP方式的主机，可用于远程ClamAV服务器
    CLAMAV_TCP_PORT: int = 3310  # TCP方式的端口
    CLAMAV_SCAN_TIMEOUT: int = 60  # 扫描超时时间（秒）
    CLAMAV_USE_TCP: bool = False  # 是否优先使用TCP方式（用于远程调用）
    
    # 文件上传配置
    MAX_FILE_SIZE: int = 100 * 1024 * 1024  # 100MB
    ALLOWED_FILE_TYPES: List[str] = [".pdf", ".docx", ".txt", ".md", ".html"]
    
    # 文档处理配置
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    MAX_CHUNKS_PER_DOCUMENT: int = 1000
    PARSING_TIMEOUT: int = 300
    VECTORIZATION_TIMEOUT: int = 600
    OLLAMA_TIMEOUT: int = 300
    
    # Unstructured配置
    UNSTRUCTURED_PDF_STRATEGY: str = "hi_res"
    UNSTRUCTURED_PDF_OCR_LANGUAGES: List[str] = ["eng", "chi_sim"]
    UNSTRUCTURED_PDF_EXTRACT_IMAGES: bool = True
    UNSTRUCTURED_PDF_IMAGE_TYPES: List[str] = ["Image", "Table"]
    UNSTRUCTURED_DOCX_STRATEGY: str = "fast"
    UNSTRUCTURED_DOCX_EXTRACT_IMAGES: bool = True
    UNSTRUCTURED_PPTX_STRATEGY: str = "fast"
    UNSTRUCTURED_PPTX_EXTRACT_IMAGES: bool = True
    UNSTRUCTURED_HTML_STRATEGY: str = "fast"
    UNSTRUCTURED_HTML_EXTRACT_IMAGES: bool = True
    UNSTRUCTURED_TXT_ENCODING: str = "utf-8"
    # 统一的语言优先级配置（供 Unstructured 解析使用）
    UNSTRUCTURED_LANGUAGES: List[str] = ["zh", "en"]
    
    # 文档内容过滤配置（提升解析质量 - 文档降噪处理）
    ENABLE_TOC_DETECTION: bool = True  # 启用目录识别（将误识别为表格的目录转换为文本）
    ENABLE_HEADER_FOOTER_FILTER: bool = True  # 启用页眉页脚过滤（排除页眉页脚内容）
    ENABLE_BLANK_CONTENT_FILTER: bool = True  # 启用空白内容过滤（排除空白页、纯空白字符）
    ENABLE_NOISE_TEXT_FILTER: bool = True  # 启用噪声文本过滤（排除OCR错误、碎片文本等）
    ENABLE_COPYRIGHT_FILTER: bool = True  # 启用版权声明过滤（排除版权页内容）
    ENABLE_WATERMARK_FILTER: bool = True  # 启用水印过滤（排除水印文字）
    ENABLE_COVER_PAGE_FILTER: bool = True  # 启用封面/封底页过滤（排除封面封底内容）
    ENABLE_FOOTNOTE_FILTER: bool = False  # 启用脚注/页边注释过滤（默认关闭，因为某些脚注可能有用）
    ENABLE_DUPLICATE_DETECTION: bool = True  # 启用重复内容检测（排除重复的段落或标题）

    # 文档预处理/转换（参照 Dify 流程）
    ENABLE_DOCX_REPAIR: bool = True  # 解析前修复主文档关系并清洗无效关系
    ENABLE_OFFICE_TO_PDF: bool = True  # 修复仍失败时，尝试 LibreOffice 转 PDF 再解析
    SOFFICE_PATH: str = "soffice"  # LibreOffice 可执行文件路径（可在 .env 中覆盖）

    # 设备与性能（自动检测 CPU/GPU/版本）
    UNSTRUCTURED_AUTO_DEVICE: bool = True  # 自动选择 cpu/cuda，并按需调整策略

    # 外部可执行程序路径（可选覆盖）
    POPPLER_PATH: Optional[str] = None  # 如 C:\tools\poppler\bin
    TESSERACT_PATH: Optional[str] = None  # 如 C:\Program Files\Tesseract-OCR
    TESSDATA_PREFIX: Optional[str] = None  # 如 C:\Program Files\Tesseract-OCR\tessdata
    
    # Unstructured模型配置（本地模型路径，优先使用本地模型）
    # 模型目录结构：models/unstructured/yolo_x_layout/yolox_10.05.onnx
    UNSTRUCTURED_MODELS_DIR: str = os.path.join(_PROJECT_ROOT, "models", "unstructured")
    # Hugging Face缓存目录（用于存储从HF下载的模型，如果未设置则使用 UNSTRUCTURED_MODELS_DIR）
    HF_HOME: Optional[str] = None  # 默认None，将设置为 UNSTRUCTURED_MODELS_DIR
    # 是否允许从Hugging Face自动下载模型（如果本地不存在）
    UNSTRUCTURED_AUTO_DOWNLOAD_MODEL: bool = True  # 默认允许自动下载，优先使用本地模型，本地没有则联网下载
    
    # 分块存储策略
    STORE_CHUNK_TEXT_IN_DB: bool = False  # 轻量模式：仅存元信息到 MySQL，全文分块归档到 MinIO
    
    class Config:
        env_file = _ENV_FILE
        env_file_encoding = "utf-8"
        case_sensitive = True

settings = Settings()
