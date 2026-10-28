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

There are no passwords. With a Google client configured you can also use **Sign in with
Google** (next section). Open http://localhost:3000/login, enter one of the test emails below
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

## Sign in with Google

`/login` shows **Sign in with Google** above the email form when `GOOGLE_CLIENT_ID` is set;
email codes stay as the fallback. BTU mail runs on Google Workspace, so `@btu.edu.ge` accounts
can use it (the API also checks the account belongs to BTU's Workspace, the `hd` claim). Other
allowed domains work if a Google account exists for the address; exact extra addresses go in
`ALLOWED_EMAILS`.

**Google Cloud setup (once):**

1. [console.cloud.google.com](https://console.cloud.google.com) → create or pick a project.
2. **Google Auth Platform → Branding** (OAuth consent screen): app name "BTU AI Skills
   Passport", support email, audience **External**, publishing status **Testing**. Scopes: the
   defaults `openid`, `email`, `profile` (no sensitive scopes, so no Google review).
3. **Audience → Test users:** add every Google account that should be able to sign in while
   the app is in Testing (only those get past Google's consent screen).
4. **Clients → Create client → Web application.** Authorized redirect URI:
   `http://localhost:3000/auth/google/callback` (exactly `PUBLIC_BASE_URL` +
   `/auth/google/callback`). No JavaScript origins are needed: the browser never calls Google's
   APIs, only the API server does.
5. Put the client ID and secret in `.env` (git-ignored) and restart `make dev`:

```sh
GOOGLE_CLIENT_ID=…apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=…        # never commit, print or log it
ALLOWED_EMAILS=you@gmail.com            # dev only: your Gmail as an exception
DEV_SUPER_ADMIN_EMAILS=you@gmail.com    # dev only: make it a super admin
```

```sh
make bootstrap             # grants SUPER_ADMIN to DEV_SUPER_ADMIN_EMAILS (with --dev-users)
```

Then **Sign in with Google** on http://localhost:3000/login lands on `/admin`. Errors come back
to `/login` as a message: cancelled, account not allowed, Google unreachable, or failed.

**Demo domain (later):** in the same client add the redirect URI
`https://<demo-domain>/auth/google/callback` (Google requires HTTPS for anything but
`localhost`), and set `PUBLIC_BASE_URL=https://<demo-domain>` in the demo env. Add the demo
users as test users, or publish the app (Audience → Publish app; with only the basic scopes
no verification is needed, though unverified apps show a warning until the branding is
verified). If BTU's Workspace admin restricts third-party apps, they must allow this client
ID (Admin console → Security → API controls). Prefer `ALLOWED_EMAILS` for individual Gmail
addresses over adding `gmail.com` to `ALLOWED_EMAIL_DOMAINS`, which would let any Gmail
account in. Leaving `GOOGLE_CLIENT_ID` empty hides the button and makes `/auth/google/*` 404.

**LAN phone test:** Google rejects plain-http redirect URIs on private IPs, so on a phone over
the LAN use email codes.

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

## Resetting for a Sheets demo

After rehearsing the Google Sheets demo, `make demo-reset` puts the Sheet and the dev database
back to the seed data, so `seed/sheets/demo-rows.md` gives fresh results again. It asks you to
type `yes`, then:

1. stops the dev servers (`make stop`);
2. in the Google Sheet: deletes every row below the seed data (*Students* after row 19,
   *Verified Skills* after row 61) and empties the write-back columns `sync_status`,
   `sync_message`, `synced_at` (G–I) of the seed rows. No other cell changes. It refuses and
   changes nothing if the seed rows are not where the import put them, in the import's
   order (someone sorted or edited the tab);
3. drops and recreates the dev database, then runs `migrate seed bootstrap issue-pending`.

Then run `make dev`: the worker renders and anchors the 18 seed passports, and the first
scheduled sync marks every seed row `DUPLICATE` again. The chain and MinIO stay as they are
(the new versions get new verification codes, so new Merkle roots); test inboxes in Mailpit are
not cleared. Signed-in sessions end with the database.

If you can't reset (for example on the hosted demo), paste the second set of rows,
`seed/sheets/demo-rows-live.md`, instead: same scenarios, fresh IDs.

## Deploying (M10)

Two targets run the same images: **Railway** (managed, preferred) and a **plain Linux server**
with Docker Compose and Caddy (fallback). Both use the demo configuration in `.env.demo`
(git-ignored; every variable is documented in `.env.example`, `# demo:` lines give the demo
value). Images: `backend/Dockerfile` (api, worker, CLI), `backend/signer.Dockerfile`,
`web/Dockerfile`, all built from the repo root. The Sepolia contract must be deployed first
(see "Sepolia contract" below): its address is in `contracts/deployments/11155111.json`, which
the backend images copy, and it is a build argument of the web image.

Before either target, check `.env.demo` locally with the production build (`make prod-up`,
"Local production rehearsal" below).

### Railway deploy

Five services in one project: `web` (the only public one), `api`, `worker`, `signer`,
`Postgres`, plus a storage bucket. Sheets sync runs inside the worker. No Caddy (Railway
terminates HTTPS), no Mailpit (Resend sends mail over HTTPS; Railway blocks SMTP), no Anvil.
`api`, `worker` and `signer` have no public domain; `web` forwards `/api`, `/auth` and
`/.well-known` to `api` over the private network.

1. **Variables from `.env.demo`:** `make railway-env` writes one block per service to
   `secrets/railway/{api,worker,signer,web}.env` (git-ignored, mode 0600; it prints only
   variable names). The signer key goes into `signer.env` only.
2. **Project:** in Railway, *New Project → Deploy from GitHub repo* → this repository. Rename
   the first service to `api`. Then *+ New → GitHub repo* (same repo) three more times for
   `worker`, `signer`, `web`; *+ New → Database → PostgreSQL* (keep the name `Postgres`);
   *+ New → Bucket* (name it `Bucket`). Service names matter: they are the private host
   names (`api.railway.internal`, `signer.railway.internal`) and the variable references
   (`${{Postgres.DATABASE_URL}}`, `${{Bucket.…}}`).
3. **Per service, Settings:** leave *Root Directory* empty (builds use the repo root) and set
   *Config-as-code → Railway config file* to:

   | Service | Config file | What it sets |
   | --- | --- | --- |
   | api | `/infra/railway/api.json` | `backend/Dockerfile`, pre-deploy `alembic upgrade head`, healthcheck `/api/healthz` |
   | worker | `/infra/railway/worker.json` | `backend/Dockerfile`, start `python -m worker` |
   | signer | `/infra/railway/signer.json` | `backend/signer.Dockerfile`, healthcheck `/healthz` |
   | web | `/infra/railway/web.json` | `web/Dockerfile`, healthcheck `/verify` |

4. **Per service, Variables → Raw Editor:** paste the matching `secrets/railway/<service>.env`.
   Open the bucket's *Variables* tab and check its variable names match the `${{Bucket.…}}`
   references in `api.env` / `worker.env` (`ENDPOINT`, `ACCESS_KEY_ID`, `SECRET_ACCESS_KEY`,
   `BUCKET`, `REGION`); rename the references if Railway shows other names. If uploads fail
   with an addressing error, set `S3_ADDRESSING_STYLE=path` on api and worker.
5. **Networking:** only `web` gets a domain: *web → Settings → Networking → Custom Domain* →
   `btuaipassport.space`, target port `3000`. Don't generate domains for the others.
6. **DNS at Namecheap** (*Domain List → Manage → Advanced DNS*): delete the default parking
   records for `@` and `www` (CNAME / URL Redirect), keep Resend's records, then add exactly
   what Railway shows for the custom domain, normally:

   | Type | Host | Value |
   | --- | --- | --- |
   | ALIAS Record | `@` | the `….up.railway.app` target Railway shows |
   | TXT Record | the host Railway shows (e.g. `_railway-verify`) | the value Railway shows, if it shows one |

   Namecheap has no CNAME at the apex; its *ALIAS Record* is the equivalent. Railway issues
   the certificate once DNS resolves (minutes to an hour).
7. **Deploy** all four (the api's pre-deploy step migrates the database). Then, in a terminal
   with the Railway CLI (`npm i -g @railway/cli`, `railway login`, `railway link`), run the
   one-off commands inside the api service:

   ```sh
   railway ssh --service api
   python -m cli seed                  # seed students, passports, skills (once)
   python -m cli demo-users            # DEMO_* super admin, admin, student
   python -m cli issue-pending         # the worker renders and anchors the seed passports
   python -m cli sheets-check          # reads the Sheet's three tabs
   python -m cli demo-reset --yes      # later: Sheet + database back to the seed data
   exit
   ```

8. **Check:** `https://btuaipassport.space/api/healthz` → `{"ok":true}`;
   `https://btuaipassport.space/.well-known/ai-passport-issuer.json` names the Sepolia
   contract; sign in with a code to `DEMO_SUPER_ADMIN_EMAIL`; the Issuance page reaches
   ANCHORED and the verify page links the transaction on Sepolia Etherscan.

Notes: Railway's private network has no per-service isolation, so the API can reach the signer
too (the HMAC header still guards `/anchor`; on the plain server only the worker shares a
network with the signer). Changing `CONTRACT_ADDRESS` or `NEXT_PUBLIC_*` on `web` needs a
redeploy, because Next.js builds them in.
