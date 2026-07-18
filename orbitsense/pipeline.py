"""The daily pipeline: ingest -> screen -> detect -> narrate -> feed.

One entry point the CI workflow calls. Reads/writes the parquet ledger and
the events feed under the data directory (the `data` branch checkout in CI).
Everything is deterministic except narration, which uses whatever ORBITSENSE_LLM
points at (default: template fallback if no key).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .analyst import narrate_maneuver
from .catalog import ingest
from .detector import scan_ledger
from .herald import cards_from_conjunctions, write_feed, write_globe
from .screener import screen


def _load_ledger(ledger_dir: Path, months: int = 4) -> pd.DataFrame:
    files = sorted(ledger_dir.glob("*.parquet"))[-months:]
    if not files:
        return pd.DataFrame()
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def _latest_names(ledger: pd.DataFrame) -> dict[int, str]:
    if ledger.empty:
        return {}
    latest = ledger.sort_values("epoch").groupby("norad_id").tail(1)
    return dict(zip(latest["norad_id"], latest["name"]))


def run(
    data_dir: str | Path = "data",
    group: str = "active",
    hours: float = 72.0,
    threshold_km: float = 5.0,
    top_conjunctions: int = 25,
    provider_spec: str | None = None,
) -> dict:
    data = Path(data_dir)
    ledger_dir = data / "ledger"
    events_dir = data / "events"

    # 1. Ingest today's catalog into the element ledger.
    ing = ingest(group=group, ledger_dir=ledger_dir)

    # 2. Load recent ledger history for detection + naming.
    ledger = _load_ledger(ledger_dir)
    names = _latest_names(ledger)

    # 3. Screen for conjunctions on the freshest elements.
    from .catalog import fetch_group_tles

    records = fetch_group_tles(group)
    conjunctions = screen(
        records, datetime.now(timezone.utc), hours=hours, threshold_km=threshold_km,
    )

    # 4. Narrate: maneuvers from the ledger + top conjunctions.
    maneuver_events = scan_ledger(ledger) if not ledger.empty else []
    cards = [narrate_maneuver(ev, names.get(ev.norad_id), provider_spec)
             for ev in maneuver_events]
    cards += cards_from_conjunctions(
        conjunctions, top=top_conjunctions, provider_spec=provider_spec,
    )

    # 5. Publish the feed + the 3D globe points.
    feed = write_feed(cards, out_dir=events_dir)
    globe = write_globe(conjunctions, out_dir=events_dir)

    summary = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "ingest": ing,
        "ledger_objects": int(ledger["norad_id"].nunique()) if not ledger.empty else 0,
        "conjunctions": len(conjunctions),
        "maneuvers": len(maneuver_events),
        "cards": len(cards),
        "feed": feed,
        "globe": globe,
    }
    (events_dir / "pipeline_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    return summary
