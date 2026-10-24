// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {Test} from "forge-std/Test.sol";

import {PassportRegistry} from "../src/PassportRegistry.sol";

contract PassportRegistryTest is Test {
    event Anchored(bytes32 indexed root, uint32 leafCount, uint256 timestamp);
    event Revoked(bytes32 indexed leaf);

    address internal issuer = makeAddr("issuer");
    address internal stranger = makeAddr("stranger");
    PassportRegistry internal registry;

    bytes32 internal constant ROOT = keccak256("root");

    function setUp() public {
        vm.warp(1_790_000_000);
        registry = new PassportRegistry(issuer);
    }

    function test_OwnerAnchorsRoot() public {
        vm.expectEmit(true, false, false, true, address(registry));
        emit Anchored(ROOT, 3, block.timestamp);
        vm.prank(issuer);
        registry.anchor(ROOT, 3);
        assertEq(registry.anchoredAt(ROOT), block.timestamp);
    }

    /// A7: only BTU's issuer can anchor in BTU's registry.
    function test_NonOwnerCannotAnchor() public {
        vm.expectRevert(
            abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, stranger)
        );
        vm.prank(stranger);
        registry.anchor(ROOT, 1);
    }

    function test_SameRootTwiceReverts() public {
        vm.startPrank(issuer);
        registry.anchor(ROOT, 1);
        vm.expectRevert(abi.encodeWithSelector(PassportRegistry.AlreadyAnchored.selector, ROOT));
        registry.anchor(ROOT, 1);
        vm.stopPrank();
    }

    function test_ZeroRootReverts() public {
        vm.expectRevert(PassportRegistry.EmptyRoot.selector);
        vm.prank(issuer);
        registry.anchor(bytes32(0), 1);
    }

    /// Every proof in shared/merkle-vectors.json verifies once its case's root is anchored.
    function test_VerifySharedVectors() public {
        string memory json = vm.readFile("../shared/merkle-vectors.json");
        uint256 cases;
        for (uint256 i = 0; vm.keyExistsJson(json, _case(i)); i++) {
            string memory c = _case(i);
            bytes32 root = vm.parseJsonBytes32(json, string.concat(c, ".root"));
            bytes32[] memory pdfs = vm.parseJsonBytes32Array(json, string.concat(c, ".pdf_sha256"));
            bytes32[] memory leaves = vm.parseJsonBytes32Array(json, string.concat(c, ".leaves"));

            vm.prank(issuer);
            registry.anchor(root, uint32(pdfs.length));

            for (uint256 j = 0; j < pdfs.length; j++) {
                bytes32 leaf = _leaf(pdfs[j]);
                assertEq(leaf, leaves[j], "leaf formula differs from Python");
                bytes32[] memory proof = vm.parseJsonBytes32Array(
                    json, string.concat(c, ".proofs.", vm.toString(pdfs[j]))
                );
                assertEq(registry.verify(leaf, proof), block.timestamp, "proof rejected");
            }
            cases++;
        }
        assertEq(cases, 6, "expected 6 vector cases");
    }

    function test_VerifyFlippedLeafByteReturnsZero() public {
        string memory json = vm.readFile("../shared/merkle-vectors.json");
        string memory c = _case(3); // four leaves
        bytes32 root = vm.parseJsonBytes32(json, string.concat(c, ".root"));
        bytes32 pdf = vm.parseJsonBytes32Array(json, string.concat(c, ".pdf_sha256"))[0];
        bytes32[] memory proof =
            vm.parseJsonBytes32Array(json, string.concat(c, ".proofs.", vm.toString(pdf)));

        vm.prank(issuer);
        registry.anchor(root, 4);
        assertGt(registry.verify(_leaf(pdf), proof), 0);

        bytes32 tampered = pdf ^ bytes32(uint256(1));
        assertEq(registry.verify(_leaf(tampered), proof), 0);
    }

    /// A7 (chain side): a root anchored on a look-alike registry is unknown to BTU's.
    function test_ForeignRegistryRootIsNotInOurs() public {
        PassportRegistry foreign = new PassportRegistry(stranger);
        vm.prank(stranger);
        foreign.anchor(ROOT, 1);
        assertGt(foreign.anchoredAt(ROOT), 0);
        assertEq(registry.anchoredAt(ROOT), 0);
        assertTrue(foreign.owner() != registry.owner());
    }

    function test_TwoStepOwnershipTransfer() public {
        address next = makeAddr("next");
        vm.prank(issuer);
        registry.transferOwnership(next);
        assertEq(registry.owner(), issuer);
        assertEq(registry.pendingOwner(), next);

        vm.expectRevert(abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, next));
        vm.prank(next);
        registry.anchor(ROOT, 1);

        vm.prank(next);
        registry.acceptOwnership();
        assertEq(registry.owner(), next);

        vm.prank(next);
        registry.anchor(ROOT, 1);
        assertEq(registry.anchoredAt(ROOT), block.timestamp);

        vm.expectRevert(abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, issuer));
        vm.prank(issuer);
        registry.anchor(keccak256("other"), 1);
    }

    function test_RevokeOnlyOwner() public {
        bytes32 leaf = keccak256("leaf");
        vm.expectRevert(
            abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, stranger)
        );
        vm.prank(stranger);
        registry.revoke(leaf);
        assertFalse(registry.revoked(leaf));

        vm.expectEmit(true, false, false, false, address(registry));
        emit Revoked(leaf);
        vm.prank(issuer);
        registry.revoke(leaf);
        assertTrue(registry.revoked(leaf));
    }

    /// BC-04 leaf: keccak256(keccak256(abi.encode(pdf_sha256))), as in OpenZeppelin's docs.
    function _leaf(bytes32 pdfSha256) internal pure returns (bytes32) {
        return keccak256(bytes.concat(keccak256(abi.encode(pdfSha256))));
    }

    function _case(uint256 i) internal pure returns (string memory) {
        return string.concat(".cases[", vm.toString(i), "]");
    }
}
