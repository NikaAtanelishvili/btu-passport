# Blockchain and signer

## 1. Registry contract

The whole on-chain part is one small contract that stores Merkle roots with a timestamp and accepts writes only from BTU's issuer address. No personal data goes on-chain (NFR-03).

### BC-01 Foundry project and contract (M1) — `contracts/` ✅

- `forge init contracts --no-git`; `forge install OpenZeppelin/openzeppelin-contracts` (v5.x, pinned); remapping `@openzeppelin/contracts/=lib/openzeppelin-contracts/contracts/`.
- `foundry.toml`: `solc` pinned (0.8.24 or newer), `optimizer = true`, `fs_permissions = [{ access = "read-write", path = "./deployments" }, { access = "read", path = "../shared" }]`.

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {Ownable2Step} from "@openzeppelin/contracts/access/Ownable2Step.sol";
import {MerkleProof} from "@openzeppelin/contracts/utils/cryptography/MerkleProof.sol";

/// @title BTU AI Skills Passport registry: Merkle roots of issued passport PDFs.
contract PassportRegistry is Ownable2Step {
    mapping(bytes32 root => uint256 timestamp) public anchoredAt;
    mapping(bytes32 leaf => bool) public revoked;

    event Anchored(bytes32 indexed root, uint32 leafCount, uint256 timestamp);
    event Revoked(bytes32 indexed leaf);

    error EmptyRoot();
    error AlreadyAnchored(bytes32 root);

    constructor(address issuer) Ownable(issuer) {}

    function anchor(bytes32 root, uint32 leafCount) external onlyOwner {
        if (root == bytes32(0)) revert EmptyRoot();
        if (anchoredAt[root] != 0) revert AlreadyAnchored(root);
        anchoredAt[root] = block.timestamp;
        emit Anchored(root, leafCount, block.timestamp);
    }

    function revoke(bytes32 leaf) external onlyOwner {
        revoked[leaf] = true;
        emit Revoked(leaf);
    }

    /// Returns the anchoring time of the root this proof leads to, or 0.
    function verify(bytes32 leaf, bytes32[] calldata proof) external view returns (uint256) {
        return anchoredAt[MerkleProof.processProofCalldata(proof, leaf)];
    }
}
```

`verify()` is a convenience for independent checkers: it uses OpenZeppelin's sorted-pair hashing, which is exactly the tree format in BC-04, so a correct proof gives a non-zero timestamp in one call. `revoke` exists for the Could-have revocation feature; nothing in the MVP UI calls it.

**ABI export:** after every contract change run `forge inspect PassportRegistry abi --json > ../shared/PassportRegistry.abi.json` (wrapped in `make chain-abi`). Python and TypeScript load the ABI from that file.

## 2. Foundry tests and deploy scripts

### BC-02 Contract tests (M1) — `contracts/test/PassportRegistry.t.sol` ✅

| Test | Expect |
| --- | --- |
| Owner anchors a root | `anchoredAt(root) == block.timestamp`; `Anchored` emitted with the leaf count |
| Non-owner anchors | Reverts `OwnableUnauthorizedAccount(sender)` (A7) |
| Same root twice | Reverts `AlreadyAnchored(root)` |
| Zero root | Reverts `EmptyRoot()` |
| `verify` with each proof from `shared/merkle-vectors.json` | Returns the anchoring timestamp after that case's root is anchored |
| `verify` with a flipped leaf byte | Returns 0 |
| Two-step ownership transfer | New owner can anchor only after `acceptOwnership()` |
| `revoke` | Only owner; sets `revoked(leaf)`; emits `Revoked` |

Read the vectors with `vm.readFile("../shared/merkle-vectors.json")` and `vm.parseJson*` helpers.

### BC-03 Deploy script (M1) — `contracts/script/Deploy.s.sol` ✅

- Reads `ISSUER_ADDRESS` from the environment, deploys `PassportRegistry(issuer)`, and writes `deployments/<chainId>.json`:

```json
{ "chain_id": 31337, "contract_address": "0x…", "issuer_address": "0x…",
  "deploy_tx": "0x…", "block_number": 1, "deployed_at": "2026-10-22T16:00:00Z" }
```

- `make chain-deploy` runs `forge script script/Deploy.s.sol --rpc-url $RPC_URL --broadcast --private-key $DEPLOYER_PRIVATE_KEY`, then copies `contract_address` into `.env` as `CONTRACT_ADDRESS` (a small script; never edit `.env` by hand in tasks).
- Dev: deployer and issuer are both Anvil account 0. On a fresh Anvil the first contract from that account usually lands at `0x5FbDB2315678afecb367f032d93F642f64180aa3`, but always read the address from the JSON, never hard-code it.

**Done when (M1):** `forge test` passes; `make chain-deploy` against Anvil writes `deployments/31337.json`; `cast call $CONTRACT_ADDRESS "owner()(address)"` prints the issuer address.

## 3. Merkle tree spec and shared test vectors

Python builds trees, Python and the browser verify proofs, and Solidity's `verify()` checks them too — so the format is fixed here once and tested in all three languages against the same vectors.

### BC-04 Spec and Python implementation (M1) — `backend/app/services/merkle.py` ✅

All hashes are keccak-256; all values are 32 bytes, written as `0x` + 64 lowercase hex.

```text
leaf(pdf_sha256)  = keccak256( keccak256( pdf_sha256 ) )    -- pdf_sha256 as 32 raw bytes
                    (equals OpenZeppelin's keccak256(bytes.concat(keccak256(abi.encode(bytes32)))))
hash_pair(a, b)   = a < b ? keccak256(a ‖ b) : keccak256(b ‖ a)   -- byte-wise comparison

build_tree(pdf_hashes):
  level = sorted(leaf(h) for h in pdf_hashes)        -- sorted ascending: deterministic
  while len(level) > 1:
    next = []
    for i in 0, 2, 4, …:
      if i + 1 < len(level): next.append(hash_pair(level[i], level[i+1]))
      else:                   next.append(level[i])   -- odd node is carried up unchanged
    level = next
  root = level[0]
  proof(leaf) = the sibling at every level where the node had one, bottom to top

process_proof(leaf, proof) = fold hash_pair over proof, starting from leaf   -- must equal root
```

A single-leaf tree has `root = leaf` and an empty proof. Reject an empty batch and duplicate PDF hashes (impossible anyway: `pdf_sha256` is UNIQUE).

Python API: `leaf(pdf_sha256_hex) -> str`, `build_tree(pdf_sha256_hexes) -> (root, {pdf_sha256_hex: proof})`, `process_proof(leaf, proof) -> str`. Keccak via `Crypto.Hash.keccak` (pycryptodome).

### BC-05 Shared vectors (M1) — `shared/merkle-vectors.json` ✅

Generated once by `python -m cli merkle-vectors` and committed. Inputs are deterministic: `pdf_sha256_i = sha256("vector-leaf-<i>")`. Cases with 1, 2, 3, 4, 5 and 7 leaves.

```json
{ "cases": [ { "name": "three-leaves",
               "pdf_sha256": ["0x…", "0x…", "0x…"],
               "leaves":     ["0x…", "0x…", "0x…"],
               "root": "0x…",
               "proofs": { "0x<pdf_sha256>": ["0x…", "0x…"] } } ] }
```

Three consumers, all in `make test`: `backend/tests/unit/test_merkle.py` (rebuilds every case and compares), `contracts/test/PassportRegistry.t.sol` (anchors each root and calls `verify` for each proof), `web/tests/merkle.test.ts` (Vitest: `processProof` gives the root for every proof).

### BC-06 TypeScript verification library (M1, used in M5) — `web/lib/merkle.ts` ✅

`leafFromPdfSha256(hex)`, `hashPair(a, b)`, `processProof(leaf, proof)` with `keccak_256` from `@noble/hashes/sha3`, plus `sha256File(file: File)` using `crypto.subtle.digest("SHA-256", …)`. No tree building in the browser.

**Done when (M1):** all three test suites pass on the same vectors.

## 4. Signer service

### BC-07 Signer (M4) — `backend/signer/` ✅

A tiny FastAPI app (`uvicorn signer.main:app --port 8100`) and the only code that ever loads the issuer private key. It does one thing: put a given root on-chain, safely and idempotently.

**Startup:**

1. Read the key from `ISSUER_PRIVATE_KEY_FILE`; derive its address with web3.py; **exit with an error if it doesn't equal `ISSUER_ADDRESS`** (catches a wrong key before any transaction).
2. Connect to `RPC_URL`; check `chain_id == CHAIN_ID` and that `CONTRACT_ADDRESS` has code and `owner()` is this address. Exit otherwise.
3. Never log the key, never return it, never expose an endpoint that signs arbitrary data.

**Endpoints:**

| Route | Behaviour |
| --- | --- |
| `GET /healthz` | `{ok, address, chain_id, balance_wei}` — no secrets |
| `POST /anchor` | Body `{root, leaf_count}`. Headers `X-Signer-Timestamp` (unix seconds) and `X-Signer-Signature` = hex `HMAC-SHA256(SIGNER_HMAC_SECRET, "<timestamp>.<raw body>")`. Reject with 401 if the signature is wrong or the timestamp is more than 60 s off |

**`/anchor` logic** (one call at a time, guarded by a process-wide lock so nonces never clash):

1. Validate `root` is `0x` + 64 hex and not zero.
2. If `anchoredAt(root) > 0`: the root is already on-chain (e.g. an earlier call timed out after sending). Find the `Anchored` log for that root (`get_logs` filtered on topic 1 = root) and return `{tx_hash, block_number, anchored_at, already_anchored: true}`.
3. Build `anchor(root, leaf_count)` with nonce = pending transaction count, EIP-1559 fees from the node, gas estimated + 20 %. Sign with the key (web3.py v7: `account.sign_transaction(tx).raw_transaction`), send, wait for the receipt (120 s timeout, `CONFIRMATIONS` blocks, default 1).
4. Receipt `status == 1` → return `{tx_hash, block_number, anchored_at, already_anchored: false}` where `anchored_at` comes from the block timestamp. Status 0 or timeout → 502 with the reason; insufficient funds → 503 `insufficient_funds` (the most likely failure on Sepolia).

**Worker side** (`app/services/anchoring.py`): signs the request with the shared secret and maps 2xx → success, anything else or a timeout → failure (BE-28 step 4).

**Done when (M4):** `tests/chain/test_signer.py` against Anvil: a valid call anchors and returns a receipt; the same root again returns `already_anchored: true` with the same `tx_hash`; a wrong HMAC gets 401; starting with a key that doesn't match `ISSUER_ADDRESS` exits with a clear error.

## 5. Verification algorithm and proof.json

The same five steps run in three places: the API (BE-30, to produce the verdict), the browser (FE-12, an independent second check), and a standalone script anyone can run without our server (NFR-09).

### The algorithm

1. **Hash.** `pdf_sha256 = SHA-256(file bytes)`. In the browser this happens locally; only the hash is sent.
2. **Proof.** Get `{proof, merkle_root, chain_id, contract_address}` for that hash (API lookup, or from `proof.json`).
3. **Document check.** `leaf = leaf(pdf_sha256)`; `root' = process_proof(leaf, proof)`; must equal `merkle_root`; then `anchoredAt(root') > 0` on the contract. Equivalent single call: `verify(leaf, proof) > 0`.
4. **Issuer check.** Fetch BTU's issuer file (`/.well-known/ai-passport-issuer.json`); the contract address and chain ID must match it, and `owner()` on the contract must equal its `issuer_address`.
5. **Status.** `revoked(leaf)` must be false. Latest-version status (Valid vs Superseded) comes from the API, because the chain doesn't track versions.

### `proof.json` format (served by `/api/verify/{code}/proof.json` and `/api/me/versions/{n}/proof.json`)

```json
{ "schema": "btu-ai-passport-proof/1",
  "passport_id": "BTU-AI-000126", "version_no": 2, "verification_code": "K7QM3XWP9D",
  "pdf_sha256": "0x…", "leaf": "0x…", "proof": ["0x…", "0x…"], "merkle_root": "0x…",
  "chain_id": 11155111, "contract_address": "0x…", "issuer_address": "0x…",
  "tx_hash": "0x…", "block_number": 6543210, "anchored_at": "2026-10-22T15:41:00Z",
  "issuer_file_url": "https://…/.well-known/ai-passport-issuer.json" }
```

### BC-06b Standalone checker (M5) — `shared/verify_proof.py`

`python verify_proof.py passport.pdf proof.json --rpc https://…`: about 50 lines with only `web3` and `pycryptodome`, implementing steps 1–4 (it prints a warning instead of fetching the issuer file if offline). It is documented in the README and on the passport's last page as the "verify without BTU" option.

**Done when (M5):** the script says VALID for an issued PDF and NOT VALID for one edited with any PDF editor.

## 6. Environments: Anvil and Sepolia

Build everything against Anvil; switch to Sepolia only in M10 by changing configuration, never code.

|  | Anvil (dev, test) | Sepolia (demo) |
| --- | --- | --- |
| Chain ID | 31337 | 11155111 |
| Runs | Compose service `anvil`, `anvil --host 0.0.0.0 --state /data/anvil-state.json` | Public network |
| Blocks | Instant on each transaction | About every 12 s |
| Issuer key | Anvil account 0 (published test key, `# DEV ONLY`) | New key from `cast wallet new`, stored only in `secrets/issuer_key` on the demo machine |
| Funds | Pre-funded | Faucet; request on day 1, keep at least 0.05 Sepolia ETH |
| `RPC_URL` (server) | `http://anvil:8545` / `http://localhost:8545` | Alchemy or Infura Sepolia URL with key |
| `NEXT_PUBLIC_RPC_URL` (browser) | `http://localhost:8545` | A public Sepolia RPC, or a provider key restricted to the demo domain |
| Explorer | none | `https://sepolia.etherscan.io/tx/` |
| Persistence | `--state` keeps the chain across restarts; deleting the file means redeploying **and** re-seeding, because old roots would be gone | Permanent (until Sepolia is retired) |

### BC-08 Sepolia deployment (M10)

1. `cast wallet new` → save the key to `secrets/issuer_key`, the address to `.env` as `ISSUER_ADDRESS`. Fund it from a faucet.
2. `make chain-deploy RPC_URL=$SEPOLIA_RPC_URL` with `--verify` and `ETHERSCAN_API_KEY` set, so the contract source is public on Etherscan.
3. Update `.env.demo`: `CHAIN_ID=11155111`, `RPC_URL`, `CONTRACT_ADDRESS` from `deployments/11155111.json`, `NEXT_PUBLIC_RPC_URL`, `NEXT_PUBLIC_EXPLORER_TX_URL`.
4. Fresh database for the demo: `make migrate seed bootstrap`, then `python -m cli issue-pending` and watch the first batch anchor; read the gas used from the first receipt and note it in the README.
5. Check the verify page against Sepolia from a phone on mobile data (not the demo machine's network).

**Done when:** the demo configuration anchors a batch on Sepolia and the transaction is visible on Etherscan.
