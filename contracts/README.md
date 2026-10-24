# contracts

Foundry project for `PassportRegistry` (docs/plan/02-blockchain-signer.md, BC-01 – BC-03).

```sh
git submodule update --init --recursive   # forge-std, OpenZeppelin (pinned tags)
forge build && forge test
make chain-deploy                          # from the repo root, against Anvil
```
