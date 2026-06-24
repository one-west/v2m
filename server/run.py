import sys

import uvicorn

from app.core.config import get_settings
from app.main import create_app


def _force_utf8_console() -> None:
    # Windows consoles default to a legacy code page (e.g. CP949 on Korean Windows),
    # which mojibakes any non-ASCII log line. Force UTF-8 so our logs stay readable
    # regardless of the host locale. No-op where the stream can't be reconfigured.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass


def main() -> None:
    _force_utf8_console()
    settings = get_settings()
    app = create_app()
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
