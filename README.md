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

Mailpit's inbox (sign-in codes in dev) is at http://localhost:8025.
`make lint` and `make test` run the backend, web and contract checks; integration tests need
`make infra-up`.

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
