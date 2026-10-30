# syntax=docker/dockerfile:1
# IN-05: the API, worker and CLI image; they differ only in the command:
#   api     (default)  uvicorn app.main:app on $PORT (8000)
#   worker             python -m worker   (set WORKER_HEARTBEAT_FILE for the healthcheck)
#   cli / migrations   python -m cli <command> · alembic upgrade head
# Build from the repo root: docker build -f backend/Dockerfile .
# /srv mirrors the repo, so REPO_ROOT (app/config.py) finds shared/, contracts/deployments/
# and seed/ as in dev. No secret is in the image; configuration comes from the environment.

FROM ghcr.io/astral-sh/uv:0.13.5 AS uv

FROM python:3.12.16-slim-trixie AS deps
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /srv/backend
COPY backend/pyproject.toml backend/uv.lock ./
# No cache mount: Railway's builder only accepts ones with a service-specific id.
RUN uv sync --frozen --no-dev --no-cache

FROM python:3.12.16-slim-trixie
# WeasyPrint's runtime libraries (Pango, HarfBuzz with subsetting). The PDF fonts (Noto) are
# bundled in app/pdf/fonts, so no system font packages beyond what fontconfig needs.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fontconfig \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --user-group --no-create-home --shell /usr/sbin/nologin app
ENV PATH=/srv/backend/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/tmp
WORKDIR /srv/backend
COPY --from=deps /srv/backend/.venv .venv
COPY shared/PassportRegistry.abi.json /srv/shared/
COPY contracts/deployments/ /srv/contracts/deployments/
COPY seed/ /srv/seed/
COPY backend/alembic.ini backend/docker_healthcheck.py backend/docker-entrypoint.sh ./
COPY backend/migrations migrations
COPY backend/app app
COPY backend/worker worker
COPY backend/cli cli
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=6s --start-period=30s --retries=3 \
    CMD ["python", "docker_healthcheck.py"]
# Without HOST uvicorn listens on every IPv4 and IPv6 address: Railway's healthcheck comes
# over IPv4, its private network over IPv6 (HOST=:: would be IPv6 only).
CMD ["sh", "-c", "exec uvicorn app.main:app --host \"${HOST:-}\" --port \"${PORT:-8000}\""]
