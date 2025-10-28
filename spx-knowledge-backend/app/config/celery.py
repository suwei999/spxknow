"""
Celery Configuration
"""

from celery import Celery
from app.config.settings import settings

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
    ]
)

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
)

def get_celery():
    """获取Celery应用"""
    return celery_app
