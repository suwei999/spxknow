"""
FastAPI entry for the Celery Worker Service.

- Health endpoints to verify environment and Redis connectivity
- Shares configuration with the main backend via `app.config.settings`
"""

from fastapi import FastAPI
from contextlib import asynccontextmanager

from app.config.settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 可在此添加更多启动检查（如 Redis/MinIO/OpenSearch）
    yield


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


