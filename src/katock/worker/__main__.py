"""工作进程入口。"""

from __future__ import annotations

import asyncio

from katock.config import ensure_config
from katock.worker.scheduler import serve


def main() -> None:
    config = ensure_config()
    asyncio.run(serve(config))


if __name__ == "__main__":
    main()
