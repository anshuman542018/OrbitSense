"""Weekly "State of the Orbits" auto-report.

Recurring, shareable content generated with zero marginal effort — the
audience-building artifact from the blueprint. Consumes the element ledger
and the week's event feeds; emits a Markdown post plus a JSON summary the
dashboard can render. No LLM required (deterministic prose), though the
headline can be upgraded via the analyst later.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from .detector import scan_ledger


@dataclass
class WeeklyStats:
    week_start: str
    week_end: str
    objects_tracked: int
    maneuvers_detected: int
    top_maneuvers: list[dict]
    conjunctions_screened: int
    closest_approach: dict | None
    busiest_object: dict | None


def _load_recent_ledger(ledger_dir: Path, months: int = 3) -> pd.DataFrame:
    files = sorted(ledger_dir.glob("*.parquet"))[-months:]
    if not files:
        return pd.DataFrame()
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def _load_week_events(events_dir: Path, week_start: datetime) -> list[dict]:
    events: list[dict] = []
    for i in range(7):
        day = (week_start + timedelta(days=i)).strftime("%Y-%m-%d")
        f = events_dir / f"{day}.json"
        if f.exists():
            events.extend(json.loads(f.read_text()))
    return events


def compute_stats(data_dir: str | Path = "data", week_start: datetime | None = None) -> WeeklyStats:
    data = Path(data_dir)
    now = datetime.now(timezone.utc)
    week_start = week_start or (now - timedelta(days=7))
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = week_start + timedelta(days=7)

    ledger = _load_recent_ledger(data / "ledger")
    events = _load_week_events(data / "events", week_start)

    # Maneuvers detected across the ledger, filtered to this week.
    maneuvers = []
    if not ledger.empty:
        for ev in scan_ledger(ledger):
            if week_start <= ev.epoch.replace(tzinfo=timezone.utc) < week_end:
                maneuvers.append(ev)
    maneuvers.sort(key=lambda e: abs(e.z_score), reverse=True)

    names = {}
    if not ledger.empty:
        latest = ledger.sort_values("epoch").groupby("norad_id").tail(1)
        names = dict(zip(latest["norad_id"], latest["name"]))

    top_maneuvers = [
        {
            "norad_id": ev.norad_id,
            "name": names.get(ev.norad_id, f"NORAD {ev.norad_id}"),
            "element": ev.column,
            "delta": round(ev.delta, 4),
            "z_score": round(ev.z_score, 1),
            "epoch": ev.epoch.isoformat(),
        }
        for ev in maneuvers[:10]
    ]

    conjunctions = [e for e in events if e.get("type") == "conjunction_notice"]
    closest = None
    if conjunctions:
        c = min(conjunctions, key=lambda e: e["evidence"].get("miss_distance_km", 1e9))
        closest = {
            "objects": [c["evidence"]["object_a"]["name"], c["evidence"]["object_b"]["name"]],
            "miss_distance_km": c["evidence"]["miss_distance_km"],
            "relative_speed_km_s": c["evidence"]["relative_speed_km_s"],
            "tca": c["evidence"]["tca"],
        }

    busiest = None
    if top_maneuvers:
        counts: dict[int, int] = {}
        for ev in maneuvers:
            counts[ev.norad_id] = counts.get(ev.norad_id, 0) + 1
        bid = max(counts, key=counts.get)
        busiest = {"norad_id": bid, "name": names.get(bid, f"NORAD {bid}"), "maneuvers": counts[bid]}

    return WeeklyStats(
        week_start=week_start.strftime("%Y-%m-%d"),
        week_end=(week_end - timedelta(days=1)).strftime("%Y-%m-%d"),
        objects_tracked=int(ledger["norad_id"].nunique()) if not ledger.empty else 0,
        maneuvers_detected=len(maneuvers),
        top_maneuvers=top_maneuvers,
        conjunctions_screened=len(conjunctions),
        closest_approach=closest,
        busiest_object=busiest,
    )


def render_markdown(stats: WeeklyStats) -> str:
    lines = [
        f"# State of the Orbits — {stats.week_start} to {stats.week_end}",
        "",
        f"OrbitSense tracked **{stats.objects_tracked:,} objects**, detected "
        f"**{stats.maneuvers_detected} maneuvers**, and screened "
        f"**{stats.conjunctions_screened} close approaches** this week.",
        "",
    ]

    if stats.closest_approach:
        ca = stats.closest_approach
        lines += [
            "## Closest approach of the week",
            "",
            f"**{ca['objects'][0]}** and **{ca['objects'][1]}** passed within "
            f"**{ca['miss_distance_km']:.2f} km** at {ca['tca'][:16].replace('T', ' ')} UTC, "
            f"closing at {ca['relative_speed_km_s']:.1f} km/s. Screening-level estimate "
            f"from public elements — no collision probability is claimed.",
            "",
        ]

    if stats.top_maneuvers:
        lines += ["## Notable maneuvers", "", "| Object | Element | Change | z-score | Date |", "|---|---|---|---|---|"]
        for m in stats.top_maneuvers:
            unit = "km" if m["element"] == "sma_km" else "deg"
            elem = "SMA" if m["element"] == "sma_km" else "inclination"
            lines.append(
                f"| {m['name']} | {elem} | {m['delta']:+.3f} {unit} | "
                f"{m['z_score']:.0f} | {m['epoch'][:10]} |"
            )
        lines.append("")

    if stats.busiest_object:
        b = stats.busiest_object
        lines += [
            f"The busiest object was **{b['name']}** with {b['maneuvers']} detected "
            f"maneuver{'s' if b['maneuvers'] != 1 else ''}.",
            "",
        ]

    lines += [
        "---",
        "*Generated by OrbitSense from public catalog data. "
        "Not an operational safety service.*",
    ]
    return "\n".join(lines)


def generate(data_dir: str | Path = "data", week_start: datetime | None = None) -> dict:
    stats = compute_stats(data_dir, week_start)
    md = render_markdown(stats)
    out = Path(data_dir) / "reports"
    out.mkdir(parents=True, exist_ok=True)
    slug = f"state-of-the-orbits-{stats.week_start}"
    (out / f"{slug}.md").write_text(md)
    from dataclasses import asdict

    (out / f"{slug}.json").write_text(json.dumps(asdict(stats), indent=2, default=str))
    (out / "latest.json").write_text(json.dumps(asdict(stats), indent=2, default=str))
    return {"report": str(out / f"{slug}.md"), "week": stats.week_start}
