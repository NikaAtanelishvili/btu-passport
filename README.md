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
make api                                  # http://localhost:8000
make web                                  # http://localhost:3000
```

`make lint` and `make test` run the backend, web and contract checks; integration tests need
`make infra-up`.

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
