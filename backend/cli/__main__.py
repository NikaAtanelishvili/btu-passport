"""CLI entry point: `python -m cli <command>` (issue-pending arrives in M4)."""

import argparse

from cli import merkle_vectors, seed


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m cli")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("merkle-vectors", help="write shared/merkle-vectors.json (BC-05)")
    commands.add_parser("seed", help="import seed/test-data.csv (BE-04)")
    args = parser.parse_args()

    if args.command == "merkle-vectors":
        merkle_vectors.main()
    elif args.command == "seed":
        seed.main()


if __name__ == "__main__":
    main()
