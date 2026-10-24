"""BC-03 post-deploy step (stdlib only), run by `make chain-deploy` after `forge script`.

Completes deployments/<chainId>.json with deploy_tx, block_number and deployed_at from the
broadcast receipt, then writes CONTRACT_ADDRESS into the repo's .env.
"""

import json
import re
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

CONTRACTS = Path(__file__).resolve().parents[1]
ENV_FILE = CONTRACTS.parent / ".env"


def rpc(url: str, method: str, *params: object) -> dict:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    request = urllib.request.Request(url, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)["result"]


def main(chain_id: str, rpc_url: str) -> None:
    run = json.loads((CONTRACTS / f"broadcast/Deploy.s.sol/{chain_id}/run-latest.json").read_text())
    tx = next(t for t in run["transactions"] if t["transactionType"] == "CREATE")
    receipt = rpc(rpc_url, "eth_getTransactionReceipt", tx["hash"])
    if int(receipt["status"], 16) != 1:
        sys.exit(f"deploy transaction {tx['hash']} failed")
    block = rpc(rpc_url, "eth_getBlockByNumber", receipt["blockNumber"], False)

    path = CONTRACTS / f"deployments/{chain_id}.json"
    deployment = json.loads(path.read_text())
    if deployment["contract_address"].lower() != receipt["contractAddress"].lower():
        sys.exit("deployments JSON and receipt disagree on the contract address")
    deployment |= {
        "deploy_tx": tx["hash"],
        "block_number": int(receipt["blockNumber"], 16),
        "deployed_at": datetime.fromtimestamp(int(block["timestamp"], 16), UTC)
        .isoformat()
        .replace("+00:00", "Z"),
    }
    keys = ["chain_id", "contract_address", "issuer_address", "deploy_tx", "block_number",
            "deployed_at"]  # fmt: skip
    path.write_text(json.dumps({k: deployment[k] for k in keys}, indent=2) + "\n")

    line = f"CONTRACT_ADDRESS={deployment['contract_address']}"
    env = ENV_FILE.read_text() if ENV_FILE.exists() else ""
    if re.search(r"^CONTRACT_ADDRESS=.*$", env, flags=re.M):
        env = re.sub(r"^CONTRACT_ADDRESS=.*$", line, env, flags=re.M)
    else:
        env += ("" if env.endswith("\n") or not env else "\n") + line + "\n"
    ENV_FILE.write_text(env)
    print(f"wrote {path.relative_to(CONTRACTS.parent)}; .env {line}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
