// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console} from "forge-std/Script.sol";

import {PassportRegistry} from "../src/PassportRegistry.sol";

/// BC-03. Deploys PassportRegistry(ISSUER_ADDRESS) and writes deployments/<chainId>.json.
/// deploy_tx, block_number and deployed_at are filled in from the broadcast receipt by
/// script/post_deploy.py (`make chain-deploy`), since a script can't see them while it runs.
contract Deploy is Script {
    function run() external returns (PassportRegistry registry) {
        address issuer = vm.envAddress("ISSUER_ADDRESS");

        vm.startBroadcast();
        registry = new PassportRegistry(issuer);
        vm.stopBroadcast();

        string memory key = "deployment";
        vm.serializeUint(key, "chain_id", block.chainid);
        vm.serializeAddress(key, "issuer_address", issuer);
        string memory json = vm.serializeAddress(key, "contract_address", address(registry));
        string memory path = string.concat("deployments/", vm.toString(block.chainid), ".json");
        vm.writeJson(json, path);
        console.log("PassportRegistry", address(registry), "owner", issuer);
    }
}
