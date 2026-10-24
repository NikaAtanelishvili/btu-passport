# BTU AI Skills Digital Passport

One persistent, versioned PDF passport per student; each version's SHA-256 is anchored in a
Merkle root on an EVM chain, and anyone can verify a passport without signing in.

The plan lives in [docs/plan/](docs/plan/00-overview.md); agent rules in [CLAUDE.md](CLAUDE.md).
This README grows with the milestones (full version in M10).

## First-time setup

Needs Docker, [uv](https://docs.astral.sh/uv/), pnpm and [Foundry](https://getfoundry.sh).

```sh
git submodule update --init --recursive   # contracts/lib: OpenZeppelin, forge-std
cp .env.example .env                      # fill the change-me values
make infra-up                             # Postgres, MinIO, Mailpit, Anvil
make chain-deploy                         # PassportRegistry on Anvil; writes CONTRACT_ADDRESS to .env
make migrate seed bootstrap               # schema, hackathon seed data, dev admins
mkdir -p secrets && grep ^DEPLOYER_PRIVATE_KEY= .env.example | cut -d= -f2 > secrets/issuer_key
                                          # DEV ONLY: Anvil account 0's published key, for the signer
make dev                                  # api :8000, worker, signer :8100, web :3000
```

`make dev` runs the four dev servers together; `make api`, `make worker`, `make signer` and
`make web` run one each. `make issue-pending` gives every seed student a new version (18
PENDING versions on a fresh seed) and the worker renders and anchors them.

## Issuance (dev)

A direct award (`POST /api/admin/awards`) creates a PENDING version; the worker renders the
PDF (RENDERED), batches rendered versions into one Merkle root every `ANCHOR_INTERVAL_SECONDS`
and asks the signer to anchor it (ANCHORING → ANCHORED). Issued PDFs live in MinIO under
`pdf/<sha256>.pdf` in the `passports` bucket (console: http://localhost:9001, `minio` /
`S3_SECRET_KEY`); an admin can download any ANCHORED one from
`GET /api/admin/versions/{id}/pdf`. `make test-chain` runs the tests that need Anvil.

`make lint` and `make test` run the backend, web and contract checks; integration tests need
`make infra-up`.

## Verifying a passport without BTU

The verification page (`/verify`) offers each passport's `proof.json`. With the PDF, that file
and any RPC for the chain, `shared/verify_proof.py` checks it without BTU's server: the PDF's
hash, the Merkle proof, that the root is anchored, and that BTU's issuer key (from BTU's issuer
file) owns the registry. It needs only `web3` and `pycryptodome`:

```bash
pip install web3 pycryptodome
python shared/verify_proof.py passport.pdf proof.json --rpc http://localhost:8545
# --issuer-file <url or path> overrides the issuer_file_url written in proof.json
```

It prints `VALID` (exit 0) or `NOT VALID: <reason>` (exit 1). Whether the version is the
passport's latest is known only to BTU's server.

## Signing in (dev)

There are no passwords. Open http://localhost:3000/login, enter one of the test emails below
and press **Send code**. The email goes to Mailpit: open http://localhost:8025, click the
newest message ("123456 is your BTU AI Skills Passport sign-in code") and type the 6 digits
into the sign-in page. With `DEV_LOG_LOGIN_CODES=true` the code is also printed in the
`make api` terminal.

| Email | Who | Lands on |
| --- | --- | --- |
| `superadmin@btu.test` | Super admin (after `make bootstrap`) | `/admin` |
| `admin@btu.test` | Admin (after `make bootstrap`) | `/admin` |
| `btu-t-0002@example.org` | Mariam Beridze, seed student | `/me` |
| `btu-t-0012@example.org` | Nikoloz Gelashvili, seed student | `/me` |
| `btu-t-0021@example.org` | Luka Japaridze, seed student | `/me` |
| `newcomer@btu.test` | BTU email, no student record | `/` |

Rules: a code works once, expires after 10 minutes, and dies after 5 wrong tries; requesting
a new one cancels the old one. Each email can request 5 codes an hour (429 after that). In dev
every request reaches the API as 127.0.0.1, so only that per-email limit applies; to reset it
while testing: `docker exec btu-passport-db-1 psql -U passport -c "DELETE FROM login_codes"`.

**Demo:** set `SMTP_HOST`, `SMTP_PORT` (587 = STARTTLS, 465 = TLS), `SMTP_USER`,
`SMTP_PASSWORD`, `SMTP_FROM` to a real sender and `DEV_LOG_LOGIN_CODES=false`; the API refuses
to start with code logging on unless `ENV` is `dev` or `test`. Send yourself a code first and
check it doesn't land in spam. There is no second factor for staff: whoever controls an
admin's inbox can sign in as that admin (accepted trade-off).

## Phone test over the LAN (same Wi-Fi, plain http)

Phones scan the presenter QR, so the QR must point at an address they can reach: the
laptop's LAN IP. Only port 3000 needs to be reachable; Next.js proxies `/api` and `/auth` to
the API, which stays on 127.0.0.1. Cookies work over plain http because `.env` keeps
`SESSION_SECURE=false` and `SESSION_COOKIE_NAME=session` (the demo's `__Host-` cookie needs
HTTPS).

1. Put the laptop and the phone on the same Wi-Fi and get the laptop's address:
   `make lan-url` prints e.g. `http://192.168.1.27:3000`.
2. In `.env`, set `PUBLIC_BASE_URL` to that address. Leave everything else.
3. Stop any running dev servers (Ctrl-C; `make stop` if something was suspended with Ctrl-Z)
   and run `make dev`. All four must restart: the API and worker put `PUBLIC_BASE_URL` into
   check-in QR codes and verify links, and the web server only serves its dev assets to
   that host (`allowedDevOrigins` in `web/next.config.ts`).
4. If the laptop runs a firewall, allow port 3000 from the Wi-Fi (Ubuntu:
   `sudo ufw status`; if active, `sudo ufw allow from 192.168.1.0/24 to any port 3000 proto tcp`
   with your network's range). Add port 8025 too if phones should read Mailpit themselves.
5. On the phone, open `http://192.168.1.27:3000/verify` (your address). The page must load
   and react to typing; if it doesn't load, the Wi-Fi may isolate devices: use a phone
   hotspot instead.
6. On the laptop, sign in as `superadmin@btu.test` (at `http://localhost:3000` is fine),
   create an event, press **Open check-in now**, then **Open presenter view**.
7. On the phone, scan the QR with the camera app. Sign in with a test email, e.g.
   `btu-t-0012@example.org` (a student) or `newcomer@btu.test` (shows as Unregistered). The
   code is in Mailpit: http://localhost:8025 on the laptop, `http://<laptop-ip>:8025` on the
   phone, or the `make dev` log. After signing in the phone returns to the check-in page; if
   it says the code has expired (signing in took over a minute), scan the screen again.
   Tap **Check in**: the participant appears on the event page within 3 seconds.
8. Afterwards, set `PUBLIC_BASE_URL=http://localhost:3000` again and restart `make dev`.

Passports issued while `PUBLIC_BASE_URL` is the LAN address keep that address in their
printed verify link and QR for good (issued content is frozen), so don't issue real
passports in this mode. The verify page's independent blockchain check reads
`NEXT_PUBLIC_RPC_URL` (Anvil on the laptop's localhost), which a phone can't reach; it says
so and the server's result still shows.

## Demo accounts (real inboxes)

The test emails above go to Mailpit. For a demo, sign-in codes must reach real inboxes, so
the super admin, an admin and at least one student are created with real addresses. Their
domains are allowed only in the demo env file (`.env.demo`, git-ignored), never in `.env`:

```sh
# .env.demo (on top of the demo values: SMTP_*, ENV=demo, DEV_LOG_LOGIN_CODES=false, ...)
ALLOWED_EMAIL_DOMAINS=btu.edu.ge,btu.test,example.org,gmail.com   # + the real domains
DEMO_SUPER_ADMIN_EMAIL=you@gmail.com
DEMO_ADMIN_EMAIL=colleague@gmail.com
DEMO_STUDENT_EMAIL=student@gmail.com
DEMO_STUDENT_ID=BTU-T-0900            # optional; also DEMO_STUDENT_FIRST_NAME / _LAST_NAME
```

```sh
make demo-users            # reads .env.demo over .env; DEMO_ENV=path/to/file for another file
```

It grants SUPER_ADMIN and ADMIN to the two staff addresses and registers the student (with a
new Passport ID; their first version is issued with their first skill, e.g. a direct award).
Every change is in the audit log with the system as actor. Re-running changes nothing. It
refuses an address whose domain isn't in `ALLOWED_EMAIL_DOMAINS`, so it can't run against the
dev configuration by mistake. The API must run with the same `.env.demo`, or those addresses
can't sign in.

## Resetting the local chain

Anvil keeps its chain in the `anvildata` volume (`--state`), so contracts and anchored roots
survive restarts. Its block clock resumes from the saved state, so block timestamps lag real
time by however long Anvil was stopped; that's expected in dev.

To start the chain from scratch:

```sh
docker compose --env-file .env -f infra/docker-compose.yml rm -sf anvil
docker volume rm btu-passport_anvildata
make infra-up chain-deploy
```

Old Merkle roots are gone after this, so anything the database says was anchored no longer
verifies: also reset the database (`make infra-reset` wipes Postgres, MinIO and Anvil
together), then `make infra-up chain-deploy migrate seed bootstrap`.
