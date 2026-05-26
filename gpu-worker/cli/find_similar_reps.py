"""CLI: "find me reps like this rep" (Issue #8).

Thin wrapper around ``POST /api/v1/search/similar`` so analysts and
coaches can sanity-check the embedding stack from a terminal without
opening the front-end. Suitable for use inside a Jupyter notebook too —
import ``find_similar_reps`` and call it with the same args as the CLI.

Usage::

    python -m cli.find_similar_reps \\
        --clip 7b8d2e34-...  --k 10  --backend-url https://api.football-iq.dev  \\
        --token $FOOTBALL_IQ_TOKEN  --formation trips_right

Set ``--include-experimental`` to also return embeddings that have not
yet been promoted via the cluster-review workflow. By default the
endpoint filters those out.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import httpx


def find_similar_reps(
    clip_id: str,
    *,
    backend_url: str,
    token: str,
    k: int = 10,
    chunk_kind: str = "play",
    since: str | None = None,
    until: str | None = None,
    opponent: str | None = None,
    formation: str | None = None,
    coverage: str | None = None,
    side_of_ball: str | None = None,
    include_experimental: bool = False,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Call the search-similar endpoint and return the parsed JSON body.

    Raises on HTTP error so callers can handle 404s (e.g. no embedding for
    the clip yet) explicitly.
    """
    filters: dict[str, Any] = {"include_experimental": include_experimental}
    if since:
        filters["since"] = since
    if until:
        filters["until"] = until
    if opponent:
        filters["opponent"] = opponent
    if formation:
        filters["formation"] = formation
    if coverage:
        filters["coverage"] = coverage
    if side_of_ball:
        filters["side_of_ball"] = side_of_ball

    payload = {
        "clip_id": clip_id,
        "k": k,
        "chunk_kind": chunk_kind,
        "filters": filters,
    }
    headers = {"Authorization": f"Bearer {token}"}
    url = backend_url.rstrip("/") + "/api/v1/search/similar"
    with httpx.Client(timeout=timeout) as c:
        resp = c.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        return dict(resp.json())


def format_results_table(body: dict[str, Any]) -> str:
    """Render the search response as a human-readable table for the CLI."""
    if body.get("reason"):
        return f"[no results] {body['reason']}"
    results = body.get("results") or []
    if not results:
        return "[no results]"
    model_label = body.get("model_version_label") or "(unknown model version)"
    lines = [
        f"Model: {model_label}    (experimental={body.get('experimental')})",
        f"Anchor clip: {body.get('anchor_clip_id')}",
        "-" * 80,
        f"{'rank':>4}  {'score':>6}  {'clip_id':<36}  exp  snap  labels",
    ]
    for i, r in enumerate(results, start=1):
        exp = "Y" if r.get("is_experimental") else "N"
        snap = "Y" if r.get("snap_anchor") else "N"
        label_data = r.get("label_data") or {}
        label_summary = _summarise_labels(label_data)
        lines.append(
            f"{i:>4}  {float(r['score']):>6.3f}  {r['clip_id']:<36}  {exp:^3}  {snap:^4}  {label_summary}"
        )
    return "\n".join(lines)


def _summarise_labels(label_data: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("formation", "coverage", "personnel"):
        node = label_data.get(key)
        if isinstance(node, dict):
            generic = node.get("generic") or node.get("toledo")
            if generic:
                parts.append(f"{key}={generic}")
        elif isinstance(node, str):
            parts.append(f"{key}={node}")
    return ", ".join(parts) or "(no labels)"


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="find_similar_reps",
        description="Find plays whose embedding is closest to the given clip.",
    )
    parser.add_argument("--clip", required=True, help="Clip UUID to search from")
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--chunk-kind", default="play")
    parser.add_argument(
        "--backend-url",
        default=os.environ.get("BACKEND_API_URL", "http://localhost:8000"),
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("FOOTBALL_IQ_TOKEN", ""),
        help="Bearer token; also reads FOOTBALL_IQ_TOKEN from env.",
    )
    parser.add_argument("--since")
    parser.add_argument("--until")
    parser.add_argument("--opponent")
    parser.add_argument("--formation")
    parser.add_argument("--coverage")
    parser.add_argument("--side-of-ball", dest="side_of_ball")
    parser.add_argument(
        "--include-experimental",
        action="store_true",
        help="Include embeddings that have not yet been promoted by coach review.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit raw JSON instead of the rendered table.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    if not args.token:
        print(
            "error: --token (or FOOTBALL_IQ_TOKEN env var) is required.",
            file=sys.stderr,
        )
        return 2
    try:
        body = find_similar_reps(
            args.clip,
            backend_url=args.backend_url,
            token=args.token,
            k=args.k,
            chunk_kind=args.chunk_kind,
            since=args.since,
            until=args.until,
            opponent=args.opponent,
            formation=args.formation,
            coverage=args.coverage,
            side_of_ball=args.side_of_ball,
            include_experimental=args.include_experimental,
        )
    except httpx.HTTPStatusError as exc:
        print(
            f"backend error: {exc.response.status_code} {exc.response.text}",
            file=sys.stderr,
        )
        return 1
    if args.json:
        print(json.dumps(body, indent=2, default=str))
    else:
        print(format_results_table(body))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
