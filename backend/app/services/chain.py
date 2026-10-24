"""Read-only registry client for verification (BE-30): anchoredAt, owner, revoked.

Results are cached in-process for 60 s; a root's anchoring time never changes once set, so
a non-zero one is kept for good. No key here: the API only reads the chain.
"""

import json
import threading
import time
from collections.abc import Callable
from functools import lru_cache
from typing import Any

from web3 import Web3
from web3.contract import Contract
from web3.exceptions import BadFunctionCallOutput, ContractLogicError

from app.config import REPO_ROOT, get_settings

ABI_PATH = REPO_ROOT / "shared" / "PassportRegistry.abi.json"
CACHE_SECONDS = 60


class ChainUnavailable(Exception):
    """The RPC could not be reached or answered with an error: no verdict is possible."""


_cache: dict[tuple[Any, ...], tuple[float, Any]] = {}  # key -> (expires, value)
_lock = threading.Lock()


def clear_cache() -> None:
    with _lock:
        _cache.clear()


@lru_cache
def _web3(rpc_url: str) -> Web3:
    return Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 10}))


@lru_cache
def _abi() -> list[dict[str, Any]]:
    return list(json.loads(ABI_PATH.read_text()))


def _contract() -> Contract:
    s = get_settings()
    if not s.contract_address:
        raise ChainUnavailable("CONTRACT_ADDRESS is not set; run `make chain-deploy`.")
    return _web3(s.rpc_url).eth.contract(
        address=Web3.to_checksum_address(s.contract_address), abi=_abi()
    )


def _read[T](key: tuple[Any, ...], call: Callable[[], T], no_code: T, forever: bool = False) -> T:
    """Cached contract read. `no_code` is the answer when the address holds no registry
    (e.g. a reset dev chain); any other failure is ChainUnavailable."""
    s = get_settings()
    key = (s.rpc_url, s.contract_address.lower(), *key)
    now = time.time()
    with _lock:
        hit = _cache.get(key)
    if hit is not None and now < hit[0]:
        return hit[1]  # type: ignore[no-any-return]
    try:
        value = call()
    except (BadFunctionCallOutput, ContractLogicError):
        value = no_code
    except ChainUnavailable:
        raise
    except Exception as exc:  # connection refused, timeout, RPC error …
        raise ChainUnavailable(f"{type(exc).__name__}: {exc}") from exc
    expires = float("inf") if forever and value else now + CACHE_SECONDS
    with _lock:
        _cache[key] = (expires, value)
    return value


def _bytes32(hex_value: str) -> bytes:
    return bytes.fromhex(hex_value.removeprefix("0x"))


def anchored_at(root: str) -> int:
    """Unix time the root was anchored on the configured registry, or 0."""
    return _read(
        ("anchoredAt", root.lower()),
        lambda: int(_contract().functions.anchoredAt(_bytes32(root)).call()),
        0,
        forever=True,
    )


def owner() -> str | None:
    """The registry's owner, or None when the configured address holds no registry."""
    return _read(("owner",), lambda: str(_contract().functions.owner().call()), None)


def is_revoked(leaf: str) -> bool:
    return _read(
        ("revoked", leaf.lower()),
        lambda: bool(_contract().functions.revoked(_bytes32(leaf)).call()),
        False,
    )
