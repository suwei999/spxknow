"""
Celery App Configuration
"""

from celery import Celery
from app.config.settings import settings
from app.core.logging import logger

# 创建Celery应用
celery_app = Celery(
    "spx-knowledge-backend",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.document_tasks",
        "app.tasks.vector_tasks",
        "app.tasks.index_tasks",
        "app.tasks.image_tasks",
        "app.tasks.version_tasks",
        "app.tasks.cleanup_tasks",
        "app.tasks.notification_tasks",
        "app.tasks.observability_tasks",
    ]
)

# 输出 Redis 连接信息
try:
    logger.info(f"Celery 配置: broker={settings.REDIS_URL}, backend={settings.REDIS_URL}")
except Exception:
    pass

# Celery配置
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30分钟
    task_soft_time_limit=25 * 60,  # 25分钟
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    # 启动阶段无法连接到 broker 时立即失败（不重试），便于显式暴露配置/网络错误
    broker_connection_retry_on_startup=False,
    task_routes={
        "app.tasks.document_tasks.*": {"queue": "document"},
        "app.tasks.vector_tasks.*": {"queue": "vector"},
        "app.tasks.index_tasks.*": {"queue": "index"},
        "app.tasks.image_tasks.*": {"queue": "image"},
        "app.tasks.version_tasks.*": {"queue": "version"},
        "app.tasks.cleanup_tasks.*": {"queue": "cleanup"},
        "app.tasks.notification_tasks.*": {"queue": "notification"},
        "app.tasks.observability_tasks.*": {"queue": "observability"},
    }
)

celery_app.conf.beat_schedule = getattr(celery_app.conf, "beat_schedule", {})
if settings.OBSERVABILITY_ENABLE_SCHEDULE:
    celery_app.conf.beat_schedule.update(
        {
            "observability-resource-sync": {
                "task": "app.tasks.observability_tasks.sync_active_clusters",
                "schedule": settings.OBSERVABILITY_SYNC_INTERVAL_SECONDS,
            },
            "observability-health-check": {
                "task": "app.tasks.observability_tasks.health_check_clusters",
                "schedule": settings.OBSERVABILITY_HEALTHCHECK_INTERVAL_SECONDS,
            },
        }
    )
