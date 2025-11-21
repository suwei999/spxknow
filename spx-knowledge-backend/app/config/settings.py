"""
Configuration Management
"""

import os
from pathlib import Path
from typing import List, Optional
from pydantic_settings import BaseSettings  # type: ignore

# 计算项目根目录，确保无论从哪里运行都能找到根目录下的 .env
_CURRENT_DIR = Path(__file__).resolve().parent
_APP_DIR = _CURRENT_DIR.parent
_PROJECT_ROOT = _APP_DIR.parent
_ENV_FILE = _PROJECT_ROOT / ".env"

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
    
    # OpenSearch配置
    OPENSEARCH_URL: str = "http://localhost:9200"
    OPENSEARCH_USERNAME: str = ""
    OPENSEARCH_PASSWORD: str = ""
    OPENSEARCH_USE_SSL: bool = False
    OPENSEARCH_VERIFY_CERTS: bool = False
    # OpenSearch 索引与参数（可配置，去除硬编码）
    DOCUMENT_INDEX_NAME: str = "documents"
    IMAGE_INDEX_NAME: str = "images"
    QA_INDEX_NAME: str = "qa_history"
    RESOURCE_EVENTS_INDEX_NAME: str = "resource_events"
    RESOURCE_EVENTS_RETENTION_DAYS: int = 30
    OPENSEARCH_NUMBER_OF_SHARDS: int = 3
    OPENSEARCH_NUMBER_OF_REPLICAS: int = 1
    TEXT_ANALYZER: str = "ik_max_word"
    HNSW_EF_CONSTRUCTION: int = 128
    HNSW_M: int = 24
    KNN_NUM_CANDIDATES_FACTOR: int = 2
    
    # MinIO配置
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ROOT_USER: str = "minioadmin"
    MINIO_ROOT_PASSWORD: str = "minioadmin"
    MINIO_BUCKET_NAME: str = "spx-knowledge-base"
    MINIO_SECURE: bool = False
    
    # 向量模型配置
    OLLAMA_BASE_URL: str = "http://192.168.131.158:11434"
    OLLAMA_MODEL: str = "llama2"
    OLLAMA_EMBEDDING_MODEL: str = "nomic-embed-text"
    IMAGE_EMBEDDING_MODEL: str = "clip_vit_b32"
    CLIP_MODEL_NAME: str = "ViT-B-32"
    CLIP_MODELS_DIR: str = str((_PROJECT_ROOT / "models" / "clip").resolve())
    CLIP_PRETRAINED_PATH: str = str((_PROJECT_ROOT / "models" / "clip" / "ViT-B-32-openclip.pt").resolve())
    CLIP_CACHE_DIR: str = str((_PROJECT_ROOT / "models" / "clip" / "cache").resolve())
    # Hugging Face 缓存目录（可选，默认使用项目 models/cache 目录）
    HF_HOME: Optional[str] = str((_PROJECT_ROOT / "models" / "cache").resolve())

    IMAGE_PIPELINE_MODE: str = "memory"  # memory|temp
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
    QA_ANSWER_INDEX_NAME: str = "qa_answers"
    QA_HISTORY_CLEANUP_DAYS: int = 90
    QA_HISTORY_DEFAULT_PAGE_SIZE: int = 20
    QA_HISTORY_MAX_PAGE_SIZE: int = 100
    
    # 向量维度
    TEXT_EMBEDDING_DIMENSION: int = 1024
    IMAGE_EMBEDDING_DIMENSION: int = 512
    TEXT_EMBED_MAX_CHARS: int = 1024
    
    # Rerank模型配置
    RERANK_ENABLED: bool = True  # 是否启用rerank模型
    # 推荐中英文支持较好的模型：bge-reranker-v2-m3（多语言支持）或 bge-reranker-large（中英文效果更好）
    RERANK_MODEL_NAME: str = "BAAI/bge-reranker-v2-m3"  # rerank模型名称（支持中英文，多语言）
    RERANK_MODEL_PATH: Optional[str] = str((_PROJECT_ROOT / "models" / "rerank").resolve())  # 本地模型目录，默认指向项目 models/rerank
    RERANK_TOP_K: int = 5  # rerank后返回的结果数量（默认5个）
    RERANK_DEVICE: str = "cpu"  # rerank模型运行设备（cpu/cuda，如果配置为cuda但GPU不可用，会自动降级到cpu）
    RERANK_MIN_SCORE: float = 0.5  # rerank 后端最小得分过滤（0-1），业界建议0.4-0.5，设置为0.5以提升结果质量
    # 混合搜索向量权重 α（关键词权重为 1-α）
    # 设置为0.5表示向量和BM25权重平衡，既考虑语义相似度，也重视精确匹配
    SEARCH_HYBRID_ALPHA: float = 0.5

    # 文本向量检索参数
    SEARCH_VECTOR_THRESHOLD: float = 0.6  # 向量相似度默认阈值
    SEARCH_VECTOR_TOPK: int = 5  # 向量检索默认返回数量（与 RERANK_TOP_K 保持一致）
    # 精确搜索字段列表（用于 multi_match type=phrase），为空则默认 content
    SEARCH_EXACT_FIELDS: List[str] = ["content"]
    
    # 实体/意图阈值
    ENTITY_PERSON_CONFIDENCE: float = 0.8
    ENTITY_PLACE_CONFIDENCE: float = 0.7
    INTENT_FACTUAL_CONFIDENCE: float = 0.8
    INTENT_OPERATION_CONFIDENCE: float = 0.8
    INTENT_COMPARISON_CONFIDENCE: float = 0.7
    INTENT_DEFAULT_CONFIDENCE: float = 0.5
    
    # 图片搜索阈值
    IMAGE_SEARCH_DEFAULT_CONFIDENCE: float = 0.8
    IMAGE_SEARCH_MULTIMODAL_CONFIDENCE: float = 0.7
    IMAGE_SEARCH_DEFAULT_CONFIDENCE_FALLBACK: float = 0.5

    # 图片定位/关联增强
    IMAGE_COORDS_NORMALIZE: bool = True  # 统一输出坐标为 0-1 归一化
    IMAGE_ASSOC_RERANK_ENABLED: bool = False  # 图片↔文本关联是否启用 cross-encoder 精排（默认关闭）

    # 内容预览
    CONTENT_PREVIEW_LENGTH: int = 100
    
    # 批量操作
    MAX_BATCH_OPERATION_SIZE: int = 10
    
    # 缓存
    CACHE_TTL_SECONDS: int = 3600
    CACHE_MAX_SIZE: int = 1000
    CACHE_CLEANUP_INTERVAL: int = 300
    OBSERVABILITY_RESOURCE_TYPES: List[str] = [
        "pods",
        "deployments",
        "statefulsets",
        "configmaps",  # 支持追踪 ConfigMap 配置变更
        "secrets",     # 支持追踪 Secret 配置变更
        "daemonsets",  # 支持追踪 DaemonSet（如 kube-proxy）
    ]
    OBSERVABILITY_DEFAULT_NAMESPACE: Optional[str] = None  # None 表示全命名空间
    # 支持追踪多个命名空间（包含系统组件命名空间）；为空则表示全部
    OBSERVABILITY_TRACKED_NAMESPACES: Optional[List[str]] = None
    OBSERVABILITY_SYNC_INTERVAL_SECONDS: int = 300
    OBSERVABILITY_HEALTHCHECK_INTERVAL_SECONDS: int = 600
    OBSERVABILITY_METRICS_CACHE_SECONDS: int = 120
    OBSERVABILITY_LOG_CACHE_SECONDS: int = 60
    OBSERVABILITY_ENABLE_SCHEDULE: bool = True
    OBSERVABILITY_ALLOWED_ROLES: List[str] = ["admin"]
    OBSERVABILITY_WATCH_TIMEOUT_SECONDS: int = 30
    OBSERVABILITY_WATCH_MAX_ATTEMPTS: int = 3
    OBSERVABILITY_DIAGNOSIS_MAX_ITERATIONS: int = 5
    OBSERVABILITY_DIAGNOSIS_CONFIDENCE_THRESHOLD: float = 0.8
    OBSERVABILITY_DIAGNOSIS_MEMORY_RECENT_LIMIT: int = 10
    OBSERVABILITY_DIAGNOSIS_ITERATION_DELAY_SECONDS: int = 5
    OBSERVABILITY_KNOWLEDGE_BASE_ID: Optional[int] = None  # 诊断案例保存到的知识库ID（可选）
    OBSERVABILITY_KNOWLEDGE_EVAL_MAX_DOCS: int = 3  # 每轮知识库评估最多使用的文档数量
    # 日志收集配置
    OBSERVABILITY_LOG_INITIAL_TAIL_LINES: int = 500  # 第一次尝试获取日志时的 tail_lines
    OBSERVABILITY_LOG_FALLBACK_TAIL_LINES: int = 300  # 回退策略时的 tail_lines（时间范围内无日志时）
    OBSERVABILITY_LOG_MAX_LINES: int = 300  # 最终返回的最大日志行数（优先保留 ERROR/WARNING/FATAL 日志）
    OBSERVABILITY_LOG_CONTEXT_LINES: int = 3  # 错误日志上下文行数（前后各几行）
    OBSERVABILITY_LOG_MAX_LINE_LENGTH: int = 10000  # 单行日志最大长度（超过此长度将被截断，单位：字符）
    SEARXNG_URL: Optional[str] = None
    
    # 文本质量阈值
    MAX_NEWLINE_RATIO: float = 0.5
    MAX_SPECIAL_CHAR_RATIO: float = 0.1
    MIN_CHINESE_RATIO: float = 0.3
    MIN_ENGLISH_RATIO: float = 0.3
    
    # 降级策略置信度
    FALLBACK_CONFIDENCE_BOOST: float = 0.2
    FALLBACK_DEFAULT_CONFIDENCE: float = 0.5
    
    # 文件验证
    FILE_HEADER_READ_SIZE: int = 1024
    
    # 安全
    SECRET_KEY: str = "your-secret-key-here"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # 日志
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOG_FILE: str = "logs/app.log"
    
    # 环境
    ENVIRONMENT: str = "development"
    
    # ClamAV
    CLAMAV_ENABLED: bool = True
    CLAMAV_SOCKET_PATH: Optional[str] = None
    CLAMAV_TCP_HOST: Optional[str] = "localhost"
    CLAMAV_TCP_PORT: int = 3310
    CLAMAV_SCAN_TIMEOUT: int = 60
    CLAMAV_USE_TCP: bool = False
    
    # 上传
    MAX_FILE_SIZE: int = 100 * 1024 * 1024
    ALLOWED_FILE_TYPES: List[str] = [".docx"]  # 仅支持 DOCX
    
    # 文档处理
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    MAX_CHUNKS_PER_DOCUMENT: int = 1000
    PARSING_TIMEOUT: int = 300
    VECTORIZATION_TIMEOUT: int = 600
    OLLAMA_TIMEOUT: int = 300
    
    # 分块存储策略
    STORE_CHUNK_TEXT_IN_DB: bool = False

    # 兼容历史环境变量（忽略未使用但不报错）
    SOFFICE_PATH: Optional[str] = None  # 旧的 libreoffice 路径，当前未使用

    class Config:
        env_file = _ENV_FILE
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"  # 忽略未声明的环境变量，避免启动失败

settings = Settings()
