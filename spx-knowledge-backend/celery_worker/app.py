"""
FastAPI entry for the Celery Worker Service.

- Health endpoints to verify environment and Redis connectivity
- Shares configuration with the main backend via `app.config.settings`
- Auto-start Celery worker and beat in background when running `python app.py`
"""

from fastapi import FastAPI
from contextlib import asynccontextmanager

# Ensure project root is on sys.path when running from celery_worker directory
import os
import sys
import subprocess
_current_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_current_dir)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from app.config.settings import settings
from app.core.logging import logger

_worker_proc = None  # 全局保存 Worker 子进程句柄，便于优雅退出
_beat_proc = None  # 全局保存 Beat 子进程句柄，便于优雅退出


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 可在此添加更多启动检查（如 Redis/MinIO/OpenSearch）
    try:
        logger.info(f"Celery Health Service 使用 Redis: {settings.REDIS_URL}")
    except Exception:
        pass

    global _worker_proc, _beat_proc
    # 可通过环境变量关闭自动启动（默认开启）
    if os.getenv("CELERY_AUTOSTART", "true").lower() == "true":
        try:
            log_level = os.getenv("CELERY_LOG_LEVEL", "INFO")
            queues = os.getenv("CELERY_QUEUES", "document,vector,index,image,version,cleanup,notification,observability,celery")
            concurrency = os.getenv("CELERY_CONCURRENCY", "1")
            logger.info(f"启动内嵌 Celery Worker(子进程): level={log_level}, queues={queues}, concurrency={concurrency}")

            # 以子进程方式启动 Worker，将工作目录设置为项目根，保证 `-m celery_worker.worker` 可导入
            env = {**os.environ, "CELERY_LOG_LEVEL": log_level, "CELERY_QUEUES": queues, "CELERY_CONCURRENCY": concurrency}
            _worker_proc = subprocess.Popen(
                [sys.executable, "-m", "celery_worker.worker"],
                cwd=_project_root,
                env=env,
            )
            
            # 启动 Celery Beat（定时任务调度器）
            if settings.OBSERVABILITY_ENABLE_SCHEDULE:
                logger.info(f"启动内嵌 Celery Beat(子进程): level={log_level}")
                _beat_proc = subprocess.Popen(
                    [sys.executable, "-m", "celery", "-A", "app.tasks.celery_app", "beat", "--loglevel", log_level.lower()],
                    cwd=_project_root,
                    env=env,
                )
        except Exception as e:
            logger.error(f"内嵌 Celery Worker/Beat 启动失败: {e}", exc_info=True)

    try:
        yield
    finally:
        # 应用关闭时，优雅停止子进程
        if _beat_proc and _beat_proc.poll() is None:
            try:
                logger.info("正在终止内嵌 Celery Beat 子进程…")
                _beat_proc.terminate()
                _beat_proc.wait(timeout=10)
            except Exception:
                try:
                    logger.info("强制结束内嵌 Celery Beat 子进程…")
                    _beat_proc.kill()
                except Exception:
                    pass
        
        if _worker_proc and _worker_proc.poll() is None:
            try:
                logger.info("正在终止内嵌 Celery Worker 子进程…")
                _worker_proc.terminate()
                _worker_proc.wait(timeout=10)
            except Exception:
                try:
                    logger.info("强制结束内嵌 Celery Worker 子进程…")
                    _worker_proc.kill()
                except Exception:
                    pass


app = FastAPI(
    title="SPX Celery Worker",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {
        "service": "celery-worker",
        "status": "ok",
        "redis_url": settings.REDIS_URL,
    }


# 允许在该目录直接运行：python app.py
if __name__ == "__main__":
    import uvicorn
    # 作为独立健康检查服务运行，并自动在后台启动 Celery Worker（子进程）
    uvicorn.run("celery_worker.app:app", host="0.0.0.0", port=8010, reload=False)


