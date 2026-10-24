"""Signer (BC-07): the only code that loads the issuer key. It puts a given Merkle root on-chain,
safely and idempotently, for the worker; it never signs anything else.

Written against web3.py 8 (the plan targets v7; the calls used here are unchanged in v8).
"""

import hashlib
import hmac
import json
import logging
import re
import threading
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from eth_account import Account
from eth_account.signers.local import LocalAccount
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError
from starlette.concurrency import run_in_threadpool
from web3 import Web3
from web3.contract import Contract
from web3.exceptions import TimeExhausted, Web3Exception
from web3.types import TxParams, Wei

from signer.config import SignerSettings, get_signer_settings

log = logging.getLogger("signer")

MAX_CLOCK_SKEW_SECONDS = 60
GAS_HEADROOM = 1.2
ROOT_RE = re.compile(r"^0x[0-9a-f]{64}$")


class StartupError(Exception):
    """A configuration problem found before any transaction; the signer refuses to start."""


class AnchorIn(BaseModel):
    root: str = Field(pattern=ROOT_RE.pattern)
    leaf_count: int = Field(ge=1, le=2**32 - 1)


class AnchorOut(BaseModel):
    tx_hash: str
    block_number: int
    anchored_at: str  # ISO 8601 UTC
    already_anchored: bool


class Health(BaseModel):
    ok: bool
    address: str
    chain_id: int
    balance_wei: int


class SignerError(Exception):
    def __init__(self, code: str, message: str, status: int) -> None:
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def _iso(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Signer:
    settings: SignerSettings
    w3: Web3
    account: LocalAccount
    contract: Contract
    from_block: int
    lock: threading.Lock

    @property
    def address(self) -> str:
        return str(self.account.address)

    def anchor(self, root: str, leaf_count: int) -> AnchorOut:
        root_bytes = bytes.fromhex(root[2:])
        if root_bytes == bytes(32):
            raise SignerError("validation_error", "The root must not be zero.", 422)
        with self.lock:  # one transaction at a time, so nonces never clash
            if self.contract.functions.anchoredAt(root_bytes).call() > 0:
                return self._existing(root)
            return self._send(root_bytes, leaf_count)

    def _existing(self, root: str) -> AnchorOut:
        """The root is already on-chain (e.g. an earlier call timed out after sending)."""
        logs = self.w3.eth.get_logs(
            {
                "address": self.contract.address,
                "topics": [self.contract.events.Anchored.topic, root],
                "fromBlock": self.from_block,
                "toBlock": "latest",
            }
        )
        if not logs:
            raise SignerError("anchor_log_missing", f"{root} is anchored but no log found.", 502)
        entry = logs[0]
        block = self.w3.eth.get_block(entry["blockNumber"])
        return AnchorOut(
            tx_hash="0x" + entry["transactionHash"].hex().removeprefix("0x"),
            block_number=entry["blockNumber"],
            anchored_at=_iso(block["timestamp"]),
            already_anchored=True,
        )

    def _send(self, root_bytes: bytes, leaf_count: int) -> AnchorOut:
        call = self.contract.functions.anchor(root_bytes, leaf_count)
        try:
            gas = int(call.estimate_gas({"from": self.account.address}) * GAS_HEADROOM)
            priority = self.w3.eth.max_priority_fee
            base_fee = self.w3.eth.get_block("latest").get("baseFeePerGas", 0)
            params: TxParams = {
                "from": self.account.address,
                "nonce": self.w3.eth.get_transaction_count(self.account.address, "pending"),
                "chainId": self.settings.chain_id,
                "gas": gas,
                "maxPriorityFeePerGas": priority,
                "maxFeePerGas": Wei(2 * base_fee + priority),
            }
            tx = call.build_transaction(params)
            signed = self.account.sign_transaction(cast(dict[str, Any], tx))
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        except (Web3Exception, ValueError) as exc:
            if "insufficient funds" in str(exc).lower():
                raise SignerError(
                    "insufficient_funds", "The issuer account can't pay for gas.", 503
                ) from exc
            raise SignerError("send_failed", f"Sending the transaction failed: {exc}", 502) from exc
        try:
            receipt = self.w3.eth.wait_for_transaction_receipt(
                tx_hash, timeout=self.settings.receipt_timeout_seconds
            )
        except TimeExhausted as exc:
            raise SignerError(
                "receipt_timeout", f"No receipt for {tx_hash.to_0x_hex()} in time.", 502
            ) from exc
        if receipt["status"] != 1:
            raise SignerError("reverted", f"Transaction {tx_hash.to_0x_hex()} reverted.", 502)
        self._wait_confirmations(receipt["blockNumber"])
        block = self.w3.eth.get_block(receipt["blockNumber"])
        return AnchorOut(
            tx_hash=tx_hash.to_0x_hex(),
            block_number=receipt["blockNumber"],
            anchored_at=_iso(block["timestamp"]),
            already_anchored=False,
        )

    def _wait_confirmations(self, block_number: int) -> None:
        deadline = time.monotonic() + self.settings.receipt_timeout_seconds
        while self.w3.eth.block_number - block_number + 1 < self.settings.confirmations:
            if time.monotonic() > deadline:
                raise SignerError("receipt_timeout", "Not enough confirmations in time.", 502)
            time.sleep(1)


def load_signer(settings: SignerSettings) -> Signer:
    """Startup checks (BC-07): key matches ISSUER_ADDRESS, right chain, our contract and owner."""
    try:
        key = settings.key_path().read_text().strip()
    except OSError as exc:
        raise StartupError(f"Cannot read ISSUER_PRIVATE_KEY_FILE ({exc.strerror}).") from None
    try:
        account: LocalAccount = Account.from_key(key)
    except Exception:  # the message could contain key material; say nothing about the value
        raise StartupError("ISSUER_PRIVATE_KEY_FILE does not hold a valid private key.") from None
    del key
    if account.address.lower() != settings.issuer_address.lower():
        raise StartupError(
            f"The issuer key's address {account.address} does not match ISSUER_ADDRESS "
            f"{settings.issuer_address}. Refusing to start."
        )

    w3 = Web3(Web3.HTTPProvider(settings.rpc_url, request_kwargs={"timeout": 30}))
    try:
        chain_id = w3.eth.chain_id
    except Exception as exc:
        raise StartupError(f"Cannot reach RPC_URL {settings.rpc_url}: {exc}") from None
    if chain_id != settings.chain_id:
        raise StartupError(f"RPC chain ID is {chain_id}, but CHAIN_ID is {settings.chain_id}.")
    if not settings.contract_address or not Web3.is_address(settings.contract_address):
        raise StartupError("CONTRACT_ADDRESS is not set; run `make chain-deploy`.")
    address = Web3.to_checksum_address(settings.contract_address)
    if not w3.eth.get_code(address):
        raise StartupError(f"No contract code at CONTRACT_ADDRESS {address} on chain {chain_id}.")
    contract = w3.eth.contract(address=address, abi=json.loads(settings.abi_path().read_text()))
    owner = contract.functions.owner().call()
    if owner.lower() != account.address.lower():
        raise StartupError(f"The registry's owner is {owner}, not the issuer {account.address}.")

    from_block = 0  # where to start looking for Anchored logs: the deploy block if known
    if settings.deployment_path().exists():
        from_block = int(json.loads(settings.deployment_path().read_text()).get("block_number", 0))
    return Signer(settings, w3, account, contract, from_block, threading.Lock())


def _check_hmac(settings: SignerSettings, request: Request, body: bytes) -> None:
    ts = request.headers.get("x-signer-timestamp", "")
    signature = request.headers.get("x-signer-signature", "")
    if not ts.isdigit() or abs(time.time() - int(ts)) > MAX_CLOCK_SKEW_SECONDS:
        raise SignerError("bad_signature", "Missing or stale X-Signer-Timestamp.", 401)
    secret = settings.signer_hmac_secret.get_secret_value().encode()
    expected = hmac.new(secret, f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise SignerError("bad_signature", "Bad X-Signer-Signature.", 401)


def _error(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": code, "message": message, "fields": {}}, status_code=status)


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            app.state.signer = load_signer(get_signer_settings())
        except StartupError as exc:
            log.error("signer: %s", exc)
            raise
        signer: Signer = app.state.signer
        log.info("signer ready for %s on chain %s", signer.address, signer.settings.chain_id)
        yield

    app = FastAPI(title="BTU Passport signer", version="0.1.0", lifespan=lifespan)

    @app.exception_handler(SignerError)
    async def _signer_error(_: Request, exc: SignerError) -> JSONResponse:
        return _error(exc.code, exc.message, exc.status)

    @app.get("/healthz", response_model=Health)
    def healthz(request: Request) -> Health:
        signer: Signer = request.app.state.signer
        return Health(
            ok=True,
            address=signer.address,
            chain_id=signer.settings.chain_id,
            balance_wei=signer.w3.eth.get_balance(signer.account.address),
        )

    @app.post("/anchor", response_model=AnchorOut)
    async def anchor(request: Request) -> Any:
        signer: Signer = request.app.state.signer
        body = await request.body()
        _check_hmac(signer.settings, request, body)
        try:
            data = AnchorIn.model_validate_json(body)
        except ValidationError as exc:
            return _error("validation_error", str(exc.errors()[0]["msg"]), 422)
        # Blocking chain calls run in a worker thread; the lock serialises them.
        return await run_in_threadpool(signer.anchor, data.root, data.leaf_count)

    return app


app = create_app()
