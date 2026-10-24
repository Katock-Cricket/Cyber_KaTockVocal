"""网页进程入口。"""

from __future__ import annotations

import os
import threading
import webbrowser

import uvicorn

from katock.config import ensure_config


def main() -> None:
    config = ensure_config()
    if not os.environ.get("KATOCK_NO_BROWSER"):
        threading.Timer(0.8, lambda: webbrowser.open(f"http://127.0.0.1:{config.port}")).start()
    uvicorn.run(
        "katock.web.app:app",
        host=config.host,
        port=config.port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
