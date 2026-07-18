"""Command-line interface: orbitsense <command>."""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="orbitsense",
        description="A copilot for everything happening in Earth orbit.",
    )
    parser.add_argument("--version", action="version", version=f"orbitsense {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="Pull the catalog and append to the element ledger")
    p_ingest.add_argument("--group", default="active", help="CelesTrak GP group (default: active)")
    p_ingest.add_argument("--ledger", default="data/ledger", help="Ledger directory")

    p_run = sub.add_parser("run", help="Full daily pipeline: ingest, screen, detect, narrate, feed")
    p_run.add_argument("--data", default="data", help="Data directory (ledger + events)")
    p_run.add_argument("--group", default="active", help="CelesTrak GP group")
    p_run.add_argument("--hours", type=float, default=72.0, help="Screening lookahead")
    p_run.add_argument("--threshold-km", type=float, default=5.0, help="Conjunction threshold")

    p_report = sub.add_parser("report", help="Generate the weekly State of the Orbits report")
    p_report.add_argument("--data", default="data", help="Data directory")

    args = parser.parse_args(argv)

    if args.command == "ingest":
        from .catalog import ingest

        result = ingest(group=args.group, ledger_dir=args.ledger)
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "run":
        from .pipeline import run

        result = run(
            data_dir=args.data, group=args.group,
            hours=args.hours, threshold_km=args.threshold_km,
        )
        print(json.dumps(result, indent=2, default=str))
        return 0

    if args.command == "report":
        from .report import generate

        result = generate(data_dir=args.data)
        print(json.dumps(result, indent=2, default=str))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
