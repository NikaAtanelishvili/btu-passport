"""`python -m cli merkle-vectors`: shared Merkle test vectors (BC-05)."""

import hashlib
import json
from pathlib import Path
from typing import Any

from app.services import merkle

REPO_ROOT = Path(__file__).resolve().parents[2]
VECTORS_PATH = REPO_ROOT / "shared" / "merkle-vectors.json"
CASES = {"one-leaf": 1, "two-leaves": 2, "three-leaves": 3, "four-leaves": 4,
         "five-leaves": 5, "seven-leaves": 7}  # fmt: skip


def pdf_sha256(i: int) -> str:
    return "0x" + hashlib.sha256(f"vector-leaf-{i}".encode()).hexdigest()


def build() -> dict[str, Any]:
    cases = []
    for name, n in CASES.items():
        hashes = [pdf_sha256(i) for i in range(n)]
        root, proofs = merkle.build_tree(hashes)
        cases.append(
            {
                "name": name,
                "pdf_sha256": hashes,
                "leaves": [merkle.leaf(h) for h in hashes],
                "root": root,
                "proofs": {h: proofs[h] for h in hashes},
            }
        )
    return {"cases": cases}


def render() -> str:
    return json.dumps(build(), indent=2) + "\n"


def main() -> None:
    VECTORS_PATH.write_text(render(), encoding="utf-8")
    print(f"wrote {VECTORS_PATH.relative_to(REPO_ROOT)}")
