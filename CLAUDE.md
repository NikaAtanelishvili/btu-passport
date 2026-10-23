# BTU AI Skills Digital Passport

Issues one persistent, versioned PDF passport per student, anchors each version's
SHA-256 in a Merkle root on an EVM chain, and lets anyone verify it without login.

## Read first
- docs/plan.md — implementation plan (tasks, order, rules). It wins over other docs.
- docs/requirements.md, docs/design.md, docs/webapp.md — background and IDs.

## Stack (locked)
Next.js App Router + TS + Tailwind + stock shadcn/ui · FastAPI + Pydantic v2 +
SQLAlchemy 2 + Alembic · PostgreSQL 16 · MinIO · WeasyPrint · Keycloak (OIDC) ·
Solidity + Foundry · Anvil (dev) / Sepolia (demo) · web3.py signer.

## Commands
make infra-up | infra-down | migrate | seed | bootstrap
make api | worker | signer | web       # dev servers, hot reload
make chain-deploy | types | lint | test

## Rules
- One milestone at a time; run its "Done when" before claiming done.
- Invariants: failing test first. Rules live in the DB (UNIQUE/CHECK/triggers) AND in code.
- Never change table names, route paths or locked decisions without asking.
- Version statuses: LEGACY, PENDING, RENDERED, ANCHORING, ANCHORED, FAILED.
  Only ANCHORED versions are downloadable or verifiable.
- Event statuses: DRAFT, CHECKIN_OPEN, CHECKIN_CLOSED, COMPLETED. No delete once COMPLETED.
- Issued content is frozen in passport_versions.content_json; PDFs are never re-rendered
  after issue and are stored by SHA-256.
- The issuer key lives only in the signer process. Never log it, never import it elsewhere.
- No personal data on-chain. Only Merkle roots.
- Stock shadcn components only; no custom visual design.
- Commit per task: "<TASK-ID>: summary". Tick tasks in docs/plan.md.
- Unclear spec: use the documented default and add a "# DEFAULT(Qn)" comment.
