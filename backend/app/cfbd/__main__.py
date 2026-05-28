"""Backend CLI to sync a season of CFBD data for Toledo + MAC.

Usage (from ``backend/`` with the backend environment configured):

    python -m app.cfbd --season 2024
    python -m app.cfbd --season 2024 --season-type postseason

Requires ``CFBD_API_KEY`` in the backend environment. The key is never printed;
on a missing key this exits non-zero with a backend-only error message.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from app.cfbd.errors import CFBDConfigError
from app.cfbd.sync import (
    DEFAULT_CONFERENCE,
    DEFAULT_SEASON_TYPE,
    DEFAULT_TEAM,
    run_season_sync,
)
from app.logging import configure_logging


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cfbd", description=__doc__)
    parser.add_argument("--season", type=int, required=True, help="Season year, e.g. 2024")
    parser.add_argument("--season-type", default=DEFAULT_SEASON_TYPE, help="regular | postseason")
    parser.add_argument("--conference", default=DEFAULT_CONFERENCE, help="Conference (default MAC)")
    parser.add_argument("--team", default=DEFAULT_TEAM, help="Primary team (default Toledo)")
    return parser


async def _amain(argv: list[str]) -> int:
    args = _build_parser().parse_args(argv)
    configure_logging()
    try:
        summary = await run_season_sync(
            args.season,
            season_type=args.season_type,
            conference=args.conference,
            team=args.team,
        )
    except CFBDConfigError as exc:
        # Backend-only failure — no key value to leak.
        print(f"CFBD sync aborted: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary.as_dict(), indent=2, default=str))
    return 0


def main() -> int:
    return asyncio.run(_amain(sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
