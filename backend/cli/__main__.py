"""CLI entry point: `python -m cli <command>` (seed, bootstrap, issue-pending arrive later)."""

import argparse

from cli import merkle_vectors


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m cli")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("merkle-vectors", help="write shared/merkle-vectors.json (BC-05)")
    args = parser.parse_args()

    if args.command == "merkle-vectors":
        merkle_vectors.main()


if __name__ == "__main__":
    main()
