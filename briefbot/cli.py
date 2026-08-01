"""Command line entry point: ``python -m briefbot``."""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import replace
from pathlib import Path

from .config import Holding, Watchlist, load_settings, load_watchlist
from .errors import ConfigError
from .pipeline import run_brief


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="briefbot",
        description="Generate the daily market brief.",
    )
    parser.add_argument(
        "--watchlist",
        type=Path,
        default=None,
        help="path to a watchlist JSON file (default: watchlist.json at the repo root)",
    )
    parser.add_argument(
        "--tickers",
        default=None,
        help="comma-separated symbols to use instead of the watchlist file",
    )
    parser.add_argument("--output-dir", type=Path, default=None, help="where to write the brief")
    parser.add_argument("--model", default=None, help="override the Claude model")
    parser.add_argument(
        "--skip-research",
        action="store_true",
        help="numbers only — no Claude calls, no cost, useful for a fast check",
    )
    parser.add_argument(
        "--no-fundamentals",
        action="store_true",
        help="skip the slow Ticker.info lookups (prices and volume only)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the brief to stdout instead of writing a file",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit 2 if any step degraded, even though a brief was still produced",
    )
    parser.add_argument("-v", "--verbose", action="count", default=0, help="-v info, -vv debug")
    return parser


def _watchlist_from_args(args: argparse.Namespace) -> Watchlist:
    if args.tickers:
        symbols = [s.strip().upper() for s in args.tickers.split(",") if s.strip()]
        if not symbols:
            raise ConfigError("--tickers was given but contained no symbols")
        return Watchlist(
            name="ad-hoc watchlist",
            holdings=tuple(Holding(symbol=s) for s in dict.fromkeys(symbols)),
        )
    return load_watchlist(args.watchlist)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    level = logging.WARNING
    if args.verbose == 1:
        level = logging.INFO
    elif args.verbose >= 2:
        level = logging.DEBUG
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s", stream=sys.stderr)

    try:
        settings = load_settings()
        if args.output_dir:
            settings = replace(settings, output_dir=args.output_dir.resolve())
        if args.model:
            settings = replace(settings, model=args.model)

        watchlist = _watchlist_from_args(args)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 1

    try:
        result = run_brief(
            watchlist=watchlist,
            settings=settings,
            skip_research=args.skip_research,
            write=not args.dry_run,
            include_fundamentals=not args.no_fundamentals,
        )
    except Exception as exc:  # noqa: BLE001 - the CLI reports, it does not traceback
        logging.getLogger(__name__).exception("brief generation failed")
        print(f"brief generation failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(result.text)
    else:
        print(f"wrote {result.path}", file=sys.stderr)

    print(f"summary: {result.summary()}", file=sys.stderr)
    if result.degraded:
        print("DEGRADED:", file=sys.stderr)
        for item in result.degradations:
            print(f"  - {item}", file=sys.stderr)
        if args.strict:
            return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
