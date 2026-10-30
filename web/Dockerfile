# syntax=docker/dockerfile:1
# IN-05: the Next.js app as a standalone server. Build from the repo root:
#   docker build -f web/Dockerfile --build-arg ... .
# Next.js inlines the rewrite target and every NEXT_PUBLIC_* value at build time, so these
# are build arguments: one image per deployment (chain, contract, API address).

FROM node:24.22.1-trixie-slim AS deps
WORKDIR /app
RUN corepack enable
COPY web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml ./
# No cache mount: Railway's builder only accepts ones with a service-specific id.
RUN COREPACK_ENABLE_DOWNLOAD_PROMPT=0 pnpm install --frozen-lockfile

FROM deps AS build
COPY web/ ./
# Where /api, /auth and /.well-known are forwarded (compose: http://api:8000; Railway:
# http://api.railway.internal:8000). The browser never sees it.
ARG API_ORIGIN=http://api:8000
# BTU's issuer identity for the independent check's fallback (FE-12), and the chain the
# browser reads (a public RPC: the URL ends up in the page's JavaScript).
ARG CHAIN_ID=31337
ARG CONTRACT_ADDRESS=
ARG ISSUER_ADDRESS=
ARG NEXT_PUBLIC_RPC_URL=
ARG NEXT_PUBLIC_EXPLORER_TX_URL=
ARG PUBLIC_BASE_URL=http://localhost:3000
ENV API_ORIGIN=$API_ORIGIN CHAIN_ID=$CHAIN_ID CONTRACT_ADDRESS=$CONTRACT_ADDRESS \
    ISSUER_ADDRESS=$ISSUER_ADDRESS NEXT_PUBLIC_RPC_URL=$NEXT_PUBLIC_RPC_URL \
    NEXT_PUBLIC_EXPLORER_TX_URL=$NEXT_PUBLIC_EXPLORER_TX_URL PUBLIC_BASE_URL=$PUBLIC_BASE_URL \
    NEXT_TELEMETRY_DISABLED=1
RUN COREPACK_ENABLE_DOWNLOAD_PROMPT=0 pnpm build

FROM node:24.22.1-trixie-slim
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=:: PORT=3000
WORKDIR /app
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static
COPY --from=build --chown=node:node /app/public ./public
USER node
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=6s --start-period=20s --retries=3 \
    CMD ["node", "-e", "fetch('http://127.0.0.1:' + process.env.PORT + '/verify').then(r => process.exit(r.ok ? 0 : 1), () => process.exit(1))"]
CMD ["node", "server.js"]
