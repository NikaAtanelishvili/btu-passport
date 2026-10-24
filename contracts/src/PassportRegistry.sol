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
