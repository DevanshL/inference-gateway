"""
Gateway entrypoint.
Run directly: python main.py
Or via uvicorn: uvicorn main:app --reload
"""
import uvicorn
from app.main import create_app
from app.core.config import get_settings

app = create_app()

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "main:app",
        host=settings.gateway_host,
        port=settings.gateway_port,
        workers=settings.gateway_workers if not settings.gateway_env == "development" else 1,
        reload=settings.gateway_env == "development",
        log_config=None,  # structlog handles logging
        access_log=False,  # structlog middleware handles this
    )