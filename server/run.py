import uvicorn

from app.core.config import get_settings
from app.main import create_app


def main() -> None:
    settings = get_settings()
    app = create_app()
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
