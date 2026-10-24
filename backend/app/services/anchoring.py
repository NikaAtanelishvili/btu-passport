"""Worker → signer client (BC-07). Signs each request with the shared HMAC secret.

2xx is success; any other status, a timeout or a connection error is an AnchorError, and the
caller (BE-28) retries the same batch.
"""

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from datetime import datetime

import httpx

from app.config import get_settings

TIMEOUT_SECONDS = 120


class AnchorError(Exception):
    pass


@dataclass(frozen=True)
class AnchorReceipt:
    tx_hash: str
    block_number: int
    anchored_at: datetime
    already_anchored: bool


def signature_headers(body: bytes, secret: str, now: float | None = None) -> dict[str, str]:
    ts = str(int(time.time() if now is None else now))
    mac = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return {"X-Signer-Timestamp": ts, "X-Signer-Signature": mac}


def anchor_root(root: str, leaf_count: int) -> AnchorReceipt:
    s = get_settings()
    body = json.dumps({"root": root, "leaf_count": leaf_count}).encode()
    headers = {
        "Content-Type": "application/json",
        **signature_headers(body, s.signer_hmac_secret.get_secret_value()),
    }
    try:
        response = httpx.post(
            f"{s.signer_url}/anchor", content=body, headers=headers, timeout=TIMEOUT_SECONDS
        )
    except httpx.HTTPError as exc:
        raise AnchorError(f"signer unreachable: {exc}") from exc
    if not response.is_success:
        try:
            detail = response.json().get("message", response.text)
        except ValueError:
            detail = response.text
        raise AnchorError(f"signer returned {response.status_code}: {detail}")
    data = response.json()
    return AnchorReceipt(
        tx_hash=data["tx_hash"],
        block_number=int(data["block_number"]),
        anchored_at=datetime.fromisoformat(data["anchored_at"]),
        already_anchored=bool(data["already_anchored"]),
    )
