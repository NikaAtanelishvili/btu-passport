"""CLI entry point: `python -m cli <command>` (issue-pending arrives in M4)."""

import argparse

from cli import bootstrap, merkle_vectors, seed


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m cli")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("merkle-vectors", help="write shared/merkle-vectors.json (BC-05)")
    commands.add_parser("seed", help="import seed/test-data.csv (BE-04)")
    boot = commands.add_parser("bootstrap", help="grant the first super admin (BE-05)")
    boot.add_argument("--dev-users", action="store_true", help="also make admin@btu.test ADMIN")
    args = parser.parse_args()

    if args.command == "merkle-vectors":
        merkle_vectors.main()
    elif args.command == "seed":
        seed.main()
    elif args.command == "bootstrap":
        bootstrap.main(dev_users=args.dev_users)


if __name__ == "__main__":
    main()
