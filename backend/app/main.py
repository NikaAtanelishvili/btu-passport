"""FastAPI application: `uvicorn app.main:app`."""

from fastapi import FastAPI
from pydantic import BaseModel

from app.errors import install_error_handlers


class Health(BaseModel):
    ok: bool


def create_app() -> FastAPI:
    app = FastAPI(title="BTU AI Skills Passport API", version="0.1.0")
    install_error_handlers(app)
    # SessionMiddleware (OAuth handshake only) and the routers arrive with M3 (BE-10).

    @app.get("/api/healthz", response_model=Health, tags=["health"])
    def healthz() -> Health:
        return Health(ok=True)

    return app


app = create_app()
