"""
Configuration Management
"""

from pydantic_settings import BaseSettings
from typing import List, Optional
import os

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
    
    # OpenSearch配置（docker-compose 禁用安全插件，使用 http 无鉴权）
    OPENSEARCH_HOST: str = "http://localhost:9200"
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
    OLLAMA_IMAGE_MODEL: str = "clip"
    
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
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

settings = Settings()
