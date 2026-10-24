"""FastAPI application: `uvicorn app.main:app`."""

import logging

from fastapi import Depends, FastAPI
from pydantic import BaseModel

from app.auth.csrf import csrf_protect
from app.config import get_settings
from app.errors import install_error_handlers
from app.routers import admin, auth, session


class Health(BaseModel):
    ok: bool


def _configure_logging() -> None:
    """uvicorn only configures its own loggers; give the app's an INFO handler too."""
    log = logging.getLogger("app")
    if not log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s: %(message)s"))
        log.addHandler(handler)
        log.setLevel(logging.INFO)


def create_app() -> FastAPI:
    get_settings()  # fail fast on bad configuration (e.g. DEV_LOG_LOGIN_CODES outside dev)
    _configure_logging()
    app = FastAPI(
        title="BTU AI Skills Passport API",
        version="0.1.0",
        dependencies=[Depends(csrf_protect)],
    )
    install_error_handlers(app)
    app.include_router(auth.router)
    app.include_router(session.router)
    app.include_router(admin.router)

    @app.get("/api/healthz", response_model=Health, tags=["health"])
    def healthz() -> Health:
        return Health(ok=True)

    return app


app = create_app()
