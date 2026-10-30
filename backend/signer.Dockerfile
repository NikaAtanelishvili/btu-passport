# syntax=docker/dockerfile:1
# IN-05: the signer image (BC-07). The only container that ever holds the issuer key, given
# at run time as ISSUER_PRIVATE_KEY_FILE (a mounted secret) or ISSUER_PRIVATE_KEY (its
# content, for hosts without secret files). No app/, worker/, PDF libraries or seed data.
# Build from the repo root: docker build -f backend/signer.Dockerfile .

FROM ghcr.io/astral-sh/uv:0.13.5 AS uv

FROM python:3.12.16-slim-trixie AS deps
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /srv/backend
COPY backend/pyproject.toml backend/uv.lock ./
# No cache mount: Railway's builder only accepts ones with a service-specific id.
RUN uv sync --frozen --no-dev --no-cache

FROM python:3.12.16-slim-trixie
RUN useradd --uid 10001 --user-group --no-create-home --shell /usr/sbin/nologin app
ENV PATH=/srv/backend/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/tmp \
    PORT=8100 \
    HEALTHCHECK_PATH=/healthz
WORKDIR /srv/backend
COPY --from=deps /srv/backend/.venv .venv
COPY shared/PassportRegistry.abi.json /srv/shared/
COPY contracts/deployments/ /srv/contracts/deployments/
COPY backend/docker_healthcheck.py backend/docker-entrypoint.sh ./
COPY backend/signer signer
USER app
EXPOSE 8100
HEALTHCHECK --interval=60s --timeout=10s --start-period=20s --retries=3 \
    CMD ["python", "docker_healthcheck.py"]
# HOST=:: on Railway, whose private network is IPv6 (uvicorn then listens on IPv6 only).
CMD ["sh", "-c", "exec uvicorn signer.main:app --host \"${HOST:-0.0.0.0}\" --port \"${PORT}\""]
