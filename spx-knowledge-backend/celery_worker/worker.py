"""
Celery worker launcher for Windows/Linux.

Usage (PowerShell):
  cd spx-knowledge-backend
  .\venv\Scripts\python.exe -m celery_worker.worker

Environment (optional):
  CELERY_LOG_LEVEL=INFO|DEBUG
  CELERY_CONCURRENCY=1
  CELERY_QUEUES=celery
"""

from __future__ import annotations

import os
import sys
import multiprocessing

from app.config.celery import celery_app


def main() -> None:
    log_level = os.getenv("CELERY_LOG_LEVEL", "INFO").lower()
    queues = os.getenv("CELERY_QUEUES", "celery")
    pool = "solo" if os.name == "nt" else "prefork"

    try:
        default_concurrency = max(1, multiprocessing.cpu_count() - 1)
    except Exception:
        default_concurrency = 1
    concurrency = os.getenv("CELERY_CONCURRENCY", str(default_concurrency))

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

    try:
        celery_app.worker_main(argv)
    except SystemExit as exc:
        sys.exit(exc.code)


if __name__ == "__main__":
    main()


