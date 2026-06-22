import uvicorn

from app.core.config import get_settings
from app.main import create_app

app = create_app()

if __name__ == "__main__":
    s = get_settings()
    uvicorn.run(app, host=s.host, port=s.port)
