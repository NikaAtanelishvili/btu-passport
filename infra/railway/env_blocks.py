"""`make railway-env` (M10): one Raw Editor block per Railway service, built from .env.demo.

Writes secrets/railway/<service>.env (git-ignored, mode 0600) and prints only file names and
variable names, never values. Paste each file into that service's Variables → Raw Editor.
The signer key and the Sheets key are read from the files .env.demo points at; the key goes
into signer.env only. Stdlib only.
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "secrets" / "railway"

# Railway references: Postgres' private URL and the bucket's credentials (names as shown on
# the bucket's Variables tab), and the signer's HMAC secret shared with the worker.
POSTGRES = "${{Postgres.DATABASE_URL}}"
BUCKET = {
    "S3_ENDPOINT_URL": "${{Bucket.ENDPOINT}}",
    "S3_ACCESS_KEY": "${{Bucket.ACCESS_KEY_ID}}",
    "S3_SECRET_KEY": "${{Bucket.SECRET_ACCESS_KEY}}",
    "S3_BUCKET": "${{Bucket.BUCKET}}",
    "S3_REGION": "${{Bucket.REGION}}",
}

COMMON = [  # api and worker, values from .env.demo
    "ENV", "TIMEZONE", "PUBLIC_BASE_URL", "MAIL_PROVIDER", "MAIL_FROM", "RESEND_API_KEY",
    "DEV_LOG_LOGIN_CODES", "ALLOWED_EMAIL_DOMAINS", "SESSION_COOKIE_NAME", "SESSION_SECURE",
    "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "CHAIN_ID", "RPC_URL", "CONTRACT_ADDRESS",
    "ISSUER_ADDRESS", "SIGNER_HMAC_SECRET", "ANCHOR_INTERVAL_SECONDS", "GOOGLE_SHEETS_ID",
    "SHEET_WRITEBACK", "DEMO_SUPER_ADMIN_EMAIL", "DEMO_ADMIN_EMAIL", "DEMO_STUDENT_EMAIL",
]  # fmt: skip
OPTIONAL = {"TIMEZONE", "ANCHOR_INTERVAL_SECONDS", "SHEET_WRITEBACK"}
SIGNER = ["ENV", "CHAIN_ID", "RPC_URL", "CONTRACT_ADDRESS", "ISSUER_ADDRESS"]
WEB_BUILD = ["CHAIN_ID", "CONTRACT_ADDRESS", "ISSUER_ADDRESS", "PUBLIC_BASE_URL",
             "NEXT_PUBLIC_RPC_URL", "NEXT_PUBLIC_EXPLORER_TX_URL"]  # fmt: skip


def read_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def main(env_file: str) -> None:
    env = read_env(ROOT / env_file)
    missing = [k for k in {*COMMON, *SIGNER, *WEB_BUILD} - OPTIONAL if not env.get(k)]
    if env.get("ALLOWED_EMAILS"):
        sys.exit("ALLOWED_EMAILS must be empty in the demo (ENV=demo refuses it)")
    key_file = env.get("ISSUER_PRIVATE_KEY_FILE", "")
    sa_file = env.get("GOOGLE_SHEETS_CREDENTIALS_FILE", "")
    if not key_file:
        missing.append("ISSUER_PRIVATE_KEY_FILE")
    if not sa_file:
        missing.append("GOOGLE_SHEETS_CREDENTIALS_FILE")
    if missing:
        sys.exit(f"{env_file} lacks: {', '.join(sorted(missing))}")
    issuer_key = (ROOT / key_file).read_text().strip()
    sa_json = json.dumps(json.loads((ROOT / sa_file).read_text()), separators=(",", ":"))

    common = {k: env[k] for k in COMMON if env.get(k)}
    blocks = {
        "api": common | BUCKET | {
            "DATABASE_URL": POSTGRES, "GOOGLE_SHEETS_CREDENTIALS_JSON": sa_json,
            "S3_ADDRESSING_STYLE": env.get("RAILWAY_S3_ADDRESSING_STYLE", "virtual"),
            "HOST": "::", "PORT": "8000",
        },
        "worker": common | BUCKET | {
            "DATABASE_URL": POSTGRES, "GOOGLE_SHEETS_CREDENTIALS_JSON": sa_json,
            "S3_ADDRESSING_STYLE": env.get("RAILWAY_S3_ADDRESSING_STYLE", "virtual"),
            "SIGNER_URL": "http://signer.railway.internal:8100",
        },
        "signer": {k: env[k] for k in SIGNER} | {
            "SIGNER_HMAC_SECRET": env["SIGNER_HMAC_SECRET"], "ISSUER_PRIVATE_KEY": issuer_key,
            "CONFIRMATIONS": env.get("CONFIRMATIONS", "1"), "HOST": "::", "PORT": "8100",
        },
        "web": {k: env[k] for k in WEB_BUILD} | {
            "API_ORIGIN": "http://api.railway.internal:8000", "TRUSTED_EDGE_PROXY": "true",
            "PORT": "3000",
        },
    }  # fmt: skip
    OUT.mkdir(parents=True, exist_ok=True)
    for service, values in blocks.items():
        path = OUT / f"{service}.env"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as out:
            out.writelines(f"{k}={v}\n" for k, v in values.items())
        print(f"{path.relative_to(ROOT)}: {', '.join(values)}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".env.demo")
