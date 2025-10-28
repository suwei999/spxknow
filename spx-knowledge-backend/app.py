import threading
import time
import webbrowser
import uvicorn

from app.config.settings import settings


def _open_browser():
    # 延迟等待服务就绪后再打开浏览器
    time.sleep(1.5)
    try:
        webbrowser.open(f"http://localhost:{settings.PORT}/docs")
    except Exception:
        pass


if __name__ == "__main__":
    threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
    )


