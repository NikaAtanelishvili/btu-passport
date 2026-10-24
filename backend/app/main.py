"""FastAPI application: `uvicorn app.main:app`."""

from fastapi import FastAPI
from pydantic import BaseModel

from app.errors import install_error_handlers
from app.routers import admin


class Health(BaseModel):
    ok: bool


def create_app() -> FastAPI:
    app = FastAPI(title="BTU AI Skills Passport API", version="0.1.0")
    install_error_handlers(app)
    app.include_router(admin.router)

    @app.get("/api/healthz", response_model=Health, tags=["health"])
    def healthz() -> Health:
        return Health(ok=True)

    return app


app = create_app()
