"""
Celery worker launcher for Windows/Linux.

Usage (PowerShell):
  cd spx-knowledge-backend
  .\venv\Scripts\python.exe -m celery_worker.worker

Environment (optional):
  CELERY_LOG_LEVEL=INFO|DEBUG
  CELERY_CONCURRENCY=1
  CELERY_QUEUES=document,vector,index,image,version,cleanup,notification,celery
"""

from __future__ import annotations

import os
import sys
import multiprocessing
import logging
from pathlib import Path

# Ensure project root is on sys.path when running from celery_worker directory
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_current_dir)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 使用 app.tasks.celery_app 以确保任务路由配置一致
# 所有任务都定义在 app.tasks.* 中，它们使用 app.tasks.celery_app
from app.tasks.celery_app import celery_app
from app.config.settings import settings

# 配置 Celery Worker 日志
def setup_celery_logging():
    """配置 Celery Worker 日志输出到文件与控制台（包含任务日志）"""
    # 确保 logs 目录存在
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Celery 日志文件路径
    celery_log_file = log_dir / "celery.log"
    celery_task_log_file = log_dir / "celery_tasks.log"
    
    # 配置 Celery 根日志器
    celery_logger = logging.getLogger("celery")
    celery_logger.setLevel(logging.INFO)
    
    # 清除现有处理器
    celery_logger.handlers = []
    
    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)
    celery_logger.addHandler(console_handler)
    
    # Celery 主日志文件（worker 启动、关闭等）
    file_handler = logging.FileHandler(celery_log_file, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - [%(module)s:%(lineno)d] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_formatter)
    celery_logger.addHandler(file_handler)
    
    # 任务日志文件（任务执行日志）
    task_handler = logging.FileHandler(celery_task_log_file, encoding='utf-8')
    task_handler.setLevel(logging.DEBUG)
    task_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - [%(module)s:%(funcName)s:%(lineno)d] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    task_handler.setFormatter(task_formatter)
    
    # 为任务相关的日志器添加处理器（控制台 + 文件）
    task_logger = logging.getLogger("app.tasks")
    task_logger.setLevel(logging.DEBUG)
    task_logger.handlers = []
    task_logger.addHandler(task_handler)
    task_logger.addHandler(console_handler)
    
    # 应用日志器（spx-knowledge-backend）同时输出到控制台与任务文件
    app_logger = logging.getLogger("spx-knowledge-backend")
    app_logger.setLevel(logging.DEBUG)
    if console_handler not in app_logger.handlers:
        app_logger.addHandler(console_handler)
    if task_handler not in app_logger.handlers:
        app_logger.addHandler(task_handler)
    
    # Celery 将标准输出重定向到日志，便于在控制台看到 print/traceback
    celery_app.conf.worker_redirect_stdouts = True
    celery_app.conf.worker_redirect_stdouts_level = "INFO"
    
    logger = logging.getLogger(__name__)
    logger.info(f"Celery Worker 日志已配置: {celery_log_file}, 任务日志: {celery_task_log_file}")


def main() -> None:
    # 配置日志
    setup_celery_logging()
    
    # 显式打印 Redis 连接地址
    logging.getLogger("celery").info(f"Worker 使用 Redis: {settings.REDIS_URL}")
    
    # 优先使用 settings 中的配置，如果没有则使用环境变量，最后使用默认值
    log_level = (settings.CELERY_LOG_LEVEL or os.getenv("CELERY_LOG_LEVEL", "INFO")).lower()
    
    # 队列配置：优先使用 settings，然后环境变量，最后根据 OBSERVABILITY_ENABLE_SCHEDULE 决定
    if settings.CELERY_QUEUES:
        queues = settings.CELERY_QUEUES
    elif os.getenv("CELERY_QUEUES"):
        queues = os.getenv("CELERY_QUEUES")
    else:
        # 根据 OBSERVABILITY_ENABLE_SCHEDULE 决定默认队列
        if settings.OBSERVABILITY_ENABLE_SCHEDULE:
            queues = "document,vector,index,image,version,cleanup,notification,observability,celery"
        else:
            queues = "document,vector,index,image,version,cleanup,notification,celery"
            logging.getLogger("celery").info("OBSERVABILITY_ENABLE_SCHEDULE=False，默认排除 observability 队列")
    
    pool = "solo" if os.name == "nt" else "prefork"

    # 并发数配置：优先使用 settings，然后环境变量，最后自动计算
    if settings.CELERY_CONCURRENCY is not None:
        concurrency = str(settings.CELERY_CONCURRENCY)
    elif os.getenv("CELERY_CONCURRENCY"):
        concurrency = os.getenv("CELERY_CONCURRENCY")
    else:
        # 自动计算并发数
        try:
            cpu_count = multiprocessing.cpu_count() or 2
            # 默认取 [4, 8] 之间，确保有足够 worker 处理文档解析，即使 k8s 同步任务占用部分 worker
            # 如果 CPU 核心数 >= 4，使用 4-8 个并发；否则使用 2-4 个并发
            if cpu_count >= 4:
                default_concurrency = max(4, min(8, cpu_count))
            else:
                default_concurrency = max(2, min(4, cpu_count))
            logging.getLogger("celery").info(f"自动计算并发数: CPU核心数={cpu_count}, 并发数={default_concurrency} (考虑 k8s 同步任务占用)")
        except Exception:
            default_concurrency = 2
        concurrency = str(default_concurrency)

    argv = [
        "worker",
        "-l",
        log_level,
        "-Q",
        queues,
        "-c",
        str(concurrency),
        "--pool",
        pool,
        "--without-gossip",
        "--without-mingle",
    ]
    
    # 输出启动信息
    logging.getLogger("celery").info(
        f"🚀 Celery Worker 启动参数: "
        f"queues={queues}, concurrency={concurrency}, pool={pool}, log_level={log_level}"
    )
    logging.getLogger("celery").info(
        f"📋 监听的队列列表: {queues.split(',')}"
    )
    logging.getLogger("celery").info(
        f"🔗 Redis 连接: {settings.REDIS_URL}"
    )
    
    # 验证队列配置
    required_queues = ["document"]  # 文档处理任务必须的队列
    configured_queues = queues.split(",")
    missing_queues = [q for q in required_queues if q not in configured_queues]
    if missing_queues:
        logging.getLogger("celery").error(
            f"❌ 错误：Worker 未监听必需的队列: {missing_queues}。"
            f"当前监听的队列: {configured_queues}"
        )
    else:
        logging.getLogger("celery").info(
            f"✅ Worker 已正确配置，监听 document 队列"
        )

    try:
        celery_app.worker_main(argv)
    except SystemExit as exc:
        sys.exit(exc.code)


if __name__ == "__main__":
    main()


