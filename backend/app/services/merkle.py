"""Merkle trees over passport PDF hashes (BC-04).

Sorted-pair keccak256 with double-hashed leaves, the format OpenZeppelin's MerkleProof
uses, so `PassportRegistry.verify()` accepts the same proofs. All values are 32 bytes,
written as "0x" + 64 lowercase hex.
"""

from Crypto.Hash import keccak

Hex32 = str


def _keccak(data: bytes) -> bytes:
    return keccak.new(digest_bits=256, data=data).digest()


def _to_bytes(value: Hex32) -> bytes:
    raw = value[2:] if value[:2].lower() == "0x" else value
    if len(raw) != 64:
        raise ValueError(f"expected 32 bytes of hex, got {value!r}")
    try:
        return bytes.fromhex(raw)
    except ValueError as exc:
        raise ValueError(f"not hex: {value!r}") from exc


def _to_hex(value: bytes) -> Hex32:
    return "0x" + value.hex()


def _normalise(value: Hex32) -> Hex32:
    return _to_hex(_to_bytes(value))


def leaf(pdf_sha256: Hex32) -> Hex32:
    """keccak256(keccak256(pdf_sha256)), the PDF hash taken as 32 raw bytes."""
    return _to_hex(_keccak(_keccak(_to_bytes(pdf_sha256))))


def _pair(a: bytes, b: bytes) -> bytes:
    return _keccak(a + b) if a < b else _keccak(b + a)


def hash_pair(a: Hex32, b: Hex32) -> Hex32:
    return _to_hex(_pair(_to_bytes(a), _to_bytes(b)))


def build_tree(pdf_sha256_hexes: list[Hex32]) -> tuple[Hex32, dict[Hex32, list[Hex32]]]:
    """Return (root, {pdf_sha256: proof}); keys are normalised to lowercase 0x-hex."""
    if not pdf_sha256_hexes:
        raise ValueError("cannot build a tree from an empty batch")
    pdfs = [_normalise(h) for h in pdf_sha256_hexes]
    if len(set(pdfs)) != len(pdfs):
        raise ValueError("duplicate PDF hashes in batch")

    leaf_of = {pdf: _to_bytes(leaf(pdf)) for pdf in pdfs}
    level = sorted(leaf_of.values())
    # Position of each original leaf in the current level, followed upward.
    position = {pdf: level.index(node) for pdf, node in leaf_of.items()}
    proofs: dict[Hex32, list[Hex32]] = {pdf: [] for pdf in pdfs}

    while len(level) > 1:
        for pdf, i in position.items():
            sibling = i ^ 1
            if sibling < len(level):
                proofs[pdf].append(_to_hex(level[sibling]))
            position[pdf] = i // 2
        level = [
            _pair(level[i], level[i + 1]) if i + 1 < len(level) else level[i]
            for i in range(0, len(level), 2)
        ]

    return _to_hex(level[0]), proofs


def process_proof(leaf_hex: Hex32, proof: list[Hex32]) -> Hex32:
    """Fold hash_pair over the proof starting from the leaf; equals the root if valid."""
    node = _to_bytes(leaf_hex)
    for sibling in proof:
        node = _pair(node, _to_bytes(sibling))
    return _to_hex(node)
