"""BC-04: Merkle tree spec (sorted-pair keccak256, double-hashed leaves)."""

import hashlib

import pytest
from Crypto.Hash import keccak

from app.services import merkle


def _keccak(data: bytes) -> bytes:
    return keccak.new(digest_bits=256, data=data).digest()


def _sha(i: int) -> str:
    return "0x" + hashlib.sha256(f"vector-leaf-{i}".encode()).hexdigest()


def test_leaf_is_double_keccak_of_raw_sha256() -> None:
    pdf = _sha(0)
    expected = "0x" + _keccak(_keccak(bytes.fromhex(pdf[2:]))).hex()
    assert merkle.leaf(pdf) == expected


def test_leaf_accepts_uppercase_and_no_prefix() -> None:
    pdf = _sha(1)
    assert merkle.leaf(pdf[2:].upper()) == merkle.leaf(pdf)


def test_hash_pair_is_order_independent() -> None:
    a, b = merkle.leaf(_sha(0)), merkle.leaf(_sha(1))
    assert merkle.hash_pair(a, b) == merkle.hash_pair(b, a)
    lo, hi = sorted([bytes.fromhex(a[2:]), bytes.fromhex(b[2:])])
    assert merkle.hash_pair(a, b) == "0x" + _keccak(lo + hi).hex()


def test_single_leaf_tree() -> None:
    root, proofs = merkle.build_tree([_sha(0)])
    assert root == merkle.leaf(_sha(0))
    assert proofs == {_sha(0): []}


def test_odd_node_is_carried_up() -> None:
    hashes = [_sha(i) for i in range(3)]
    leaves = sorted(merkle.leaf(h) for h in hashes)
    root, _ = merkle.build_tree(hashes)
    assert root == merkle.hash_pair(merkle.hash_pair(leaves[0], leaves[1]), leaves[2])


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 7, 16, 33])
def test_every_proof_leads_to_root(n: int) -> None:
    hashes = [_sha(i) for i in range(n)]
    root, proofs = merkle.build_tree(hashes)
    assert set(proofs) == set(hashes)
    for pdf, proof in proofs.items():
        assert merkle.process_proof(merkle.leaf(pdf), proof) == root


def test_tree_is_independent_of_input_order() -> None:
    hashes = [_sha(i) for i in range(5)]
    assert merkle.build_tree(hashes) == merkle.build_tree(list(reversed(hashes)))


def test_flipped_leaf_does_not_reach_root() -> None:
    hashes = [_sha(i) for i in range(4)]
    root, proofs = merkle.build_tree(hashes)
    tampered = "0x" + ("1" if hashes[0][2] != "1" else "2") + hashes[0][3:]
    assert merkle.process_proof(merkle.leaf(tampered), proofs[hashes[0]]) != root


def test_empty_batch_rejected() -> None:
    with pytest.raises(ValueError, match="empty"):
        merkle.build_tree([])


def test_duplicate_hashes_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        merkle.build_tree([_sha(0), _sha(0).upper().replace("0X", "0x")])


@pytest.mark.parametrize("bad", ["0x1234", "zz" * 32, "0x" + "g" * 64])
def test_malformed_hash_rejected(bad: str) -> None:
    with pytest.raises(ValueError):
        merkle.leaf(bad)
