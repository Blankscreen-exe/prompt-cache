"""Entry point for the ``prompt-cache`` console script."""

from __future__ import annotations

import argparse
import sys

from prompt_cache import __version__
from prompt_cache.paths import DATA_DIR_ENV, db_path
from prompt_cache.store.db import Fts5Unavailable, database


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prompt-cache",
        description="Write, find and fill reusable AI prompts in seconds.",
    )
    parser.add_argument("--version", action="version", version=f"prompt-cache {__version__}")
    parser.add_argument(
        "--where",
        action="store_true",
        help=f"print the database path and exit (override it with ${DATA_DIR_ENV})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.where:
        print(db_path())
        return 0

    try:
        with database() as connection:
            from prompt_cache.ui.app import PromptCacheApp

            PromptCacheApp(connection).run()
    except Fts5Unavailable as exc:
        print(f"prompt-cache: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
