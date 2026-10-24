"""Check a BTU AI Skills Passport PDF without BTU's server (BC-06b, NFR-09).

    pip install web3 pycryptodome
    python verify_proof.py passport.pdf proof.json --rpc https://<any Sepolia RPC>

proof.json is offered next to every passport on the verification page. The script checks
that the PDF is the one the proof is for, that the proof leads to a Merkle root anchored on
the registry, and that BTU's issuer key (named in BTU's issuer file) owns that registry.
"""

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

from Crypto.Hash import keccak
from web3 import Web3

ABI = [
    {"name": n, "type": "function", "stateMutability": "view", "inputs": i, "outputs": o}
    for n, i, o in [
        ("anchoredAt", [{"name": "", "type": "bytes32"}], [{"name": "", "type": "uint256"}]),
        ("revoked", [{"name": "", "type": "bytes32"}], [{"name": "", "type": "bool"}]),
        ("owner", [], [{"name": "", "type": "address"}]),
    ]
]


def keccak256(data: bytes) -> bytes:
    return keccak.new(digest_bits=256, data=data).digest()


def check(args: argparse.Namespace) -> str:
    proof = json.loads(Path(args.proof).read_text())
    pdf_sha256 = hashlib.sha256(Path(args.pdf).read_bytes()).digest()
    if "0x" + pdf_sha256.hex() != proof["pdf_sha256"].lower():
        return "NOT VALID: the PDF is not the document this proof is for (it was changed)"
    node = keccak256(keccak256(pdf_sha256))  # leaf: sorted-pair keccak256, double-hashed
    leaf = node
    for sibling in proof["proof"]:
        a, b = sorted([node, bytes.fromhex(sibling[2:])])
        node = keccak256(a + b)
    if "0x" + node.hex() != proof["merkle_root"].lower():
        return "NOT VALID: the proof does not lead to the stated Merkle root"

    source = args.issuer_file or proof["issuer_file_url"]
    try:
        if source.startswith(("http://", "https://")):
            issuer = json.load(urllib.request.urlopen(source, timeout=10))
        else:
            issuer = json.loads(Path(source).read_text())
    except OSError as exc:
        print(f"WARNING: issuer file unavailable ({exc}); trusting proof.json's issuer address")
        issuer = {k: proof[k] for k in ("chain_id", "contract_address", "issuer_address")}
    if (issuer["chain_id"], issuer["contract_address"].lower()) != (
        proof["chain_id"],
        proof["contract_address"].lower(),
    ):
        return "NOT VALID: the proof names a registry that is not in BTU's issuer file"

    w3 = Web3(Web3.HTTPProvider(args.rpc))
    if w3.eth.chain_id != proof["chain_id"]:
        return f"NOT VALID: the RPC is on chain {w3.eth.chain_id}, not {proof['chain_id']}"
    registry = w3.eth.contract(address=Web3.to_checksum_address(proof["contract_address"]), abi=ABI)
    if registry.functions.owner().call().lower() != issuer["issuer_address"].lower():
        return "NOT VALID: the registry is not owned by BTU's issuer address"
    if registry.functions.anchoredAt(node).call() == 0:
        return "NOT VALID: the Merkle root is not anchored on the registry"
    if registry.functions.revoked(leaf).call():
        return "NOT VALID: BTU has revoked this passport version"
    return "VALID"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pdf")
    parser.add_argument("proof")
    parser.add_argument("--rpc", required=True, help="JSON-RPC URL of the proof's chain")
    parser.add_argument("--issuer-file", help="URL or path; default: proof.json's issuer_file_url")
    verdict = check(parser.parse_args())
    print("Note: only BTU's verification page can tell whether this is the latest version.")
    print(verdict)
    sys.exit(0 if verdict == "VALID" else 1)


if __name__ == "__main__":
    main()
