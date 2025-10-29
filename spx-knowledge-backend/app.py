import threading
import time
import webbrowser
import uvicorn
import os

from app.config.settings import settings


def _open_browser():
    # 延迟等待服务就绪后再打开浏览器
    time.sleep(1.5)
    try:
        webbrowser.open(f"http://localhost:{settings.PORT}/docs")
    except Exception:
        pass


if __name__ == "__main__":
    # 在 Windows 上禁用 reloader 以避免 Ctrl+C 失效问题
    # 可以通过环境变量 ENABLE_RELOAD=false 来禁用 reloader
    enable_reload = os.getenv("ENABLE_RELOAD", "false").lower() == "true"
    # 是否自动打开浏览器，默认不打开
    auto_open_browser = os.getenv("OPEN_BROWSER", "false").lower() == "true"
    if auto_open_browser:
        threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=enable_reload,
        reload_excludes=["*.pyc", "__pycache__"] if enable_reload else None,
    )


