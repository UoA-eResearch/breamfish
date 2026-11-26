"""Command line: `breamfish refresh [--data-dir DIR]` and `breamfish version`."""

import argparse
import os
from functools import partial
from pathlib import Path

from breamfish import __version__, refresh
from breamfish.sources import fetch


def data_dir_from(option: Path | None) -> Path:
    """--data-dir wins, then $BREAMFISH_DATA_DIR, then ./data."""
    return option or Path(os.environ.get("BREAMFISH_DATA_DIR") or "data")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="breamfish", description="Fishing-conditions data pipeline for Bream Bay."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    refresh_parser = commands.add_parser(
        "refresh", help="fetch the sources and publish conditions.json and status.json"
    )
    refresh_parser.add_argument(
        "--data-dir", type=Path, help="where cache/ and published/ live (default: ./data)"
    )
    commands.add_parser("version", help="print the version")
    args = parser.parse_args(argv)

    if args.command == "version":
        print(__version__)
        return 0

    with fetch.make_client() as client:
        return refresh.run(data_dir_from(args.data_dir), partial(fetch.http_get, client))
