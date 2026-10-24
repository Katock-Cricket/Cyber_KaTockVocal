"""假 docker。只响应 info。"""

from __future__ import annotations

import sys


def main() -> None:
    if "info" in sys.argv:
        print("29.7.2")
        return
    print("unknown docker command", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
