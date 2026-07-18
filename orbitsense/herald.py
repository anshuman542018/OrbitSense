"""The HERALD: assembles event cards into the feed the dashboard reads.

Output is plain JSON on disk (committed to the data branch, served via CDN).
No server required — the dashboard is a static reader of these files, and the
chat backend queries the same ledger.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .analyst import EventCard, card_to_dict, narrate_conjunction, narrate_maneuver
from .detector import scan_ledger
from .screener import Conjunction


def build_cards_from_ledger(
    ledger: pd.DataFrame,
    names: dict[int, str] | None = None,
    provider_spec: str | None = None,
    z_thresh: float = 5.0,
) -> list[EventCard]:
    """Detect maneuvers in a ledger frame and narrate each as a card."""
    names = names or {}
    events = scan_ledger(ledger, z_thresh=z_thresh)
    return [narrate_maneuver(ev, names.get(ev.norad_id), provider_spec) for ev in events]


def is_docked_or_formation(c: Conjunction,
                           min_speed_km_s: float = 0.05,
                           min_miss_km: float = 0.05) -> bool:
    """True for pairs that are co-located rather than approaching.

    Docked assemblies (space-station modules, a cargo ship berthed to a
    station) and tightly-flown formations sit at ~0 km separation and ~0
    relative velocity for long stretches. They are not encounters and would
    otherwise dominate a min-range feed. A real approach has either
    meaningful closing speed or meaningful (if small) miss distance.
    """
    return c.relative_speed_km_s < min_speed_km_s and c.miss_distance_km < min_miss_km


def cards_from_conjunctions(
    conjunctions: list[Conjunction], top: int = 25, provider_spec: str | None = None,
    drop_formations: bool = True,
) -> list[EventCard]:
    pool = [c for c in conjunctions
            if not (drop_formations and is_docked_or_formation(c))]
    return [narrate_conjunction(c, provider_spec) for c in pool[:top]]


def write_globe(conjunctions: list[Conjunction], out_dir: str | Path = "data/events",
                top: int = 200) -> dict:
    """Emit globe.json: conjunction points in TEME km for the 3D view.

    Positions are Earth-centered inertial (TEME) at closest approach. The
    globe renders them directly against a rotating Earth — visual scale, not
    a geodetic product.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pts = []
    pool = [c for c in conjunctions
            if c.position_km and not is_docked_or_formation(c)]
    for c in sorted(pool, key=lambda c: c.miss_distance_km)[:top]:
        x, y, z = c.position_km
        pts.append({
            "a": c.name_a, "b": c.name_b,
            "miss_km": round(c.miss_distance_km, 3),
            "relv_km_s": round(c.relative_speed_km_s, 2),
            "tca": c.tca.isoformat(),
            "pos": [x, y, z],
        })
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "earth_radius_km": 6378.137,
        "points": pts,
    }
    (out / "globe.json").write_text(json.dumps(payload))
    return {"points": len(pts)}


def write_feed(cards: list[EventCard], out_dir: str | Path = "data/events") -> dict:
    """Write feed.json (latest N) and a dated daily file."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    payload = [card_to_dict(c) for c in cards]
    payload.sort(key=lambda c: c["tca_or_epoch"], reverse=True)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    (out / f"{today}.json").write_text(json.dumps(payload, indent=2))

    feed = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(payload),
        "events": payload[:100],
    }
    (out / "feed.json").write_text(json.dumps(feed, indent=2))
    return {"written": len(payload), "feed": str(out / "feed.json")}
