"""Weekly report tests: stats computation and Markdown rendering."""

import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from orbitsense.report import compute_stats, generate, render_markdown

RNG = np.random.default_rng(7)


def _seed_ledger(ledger_dir, burn_day=3):
    """90-day SMA history for one object with one reboost this week."""
    week_start = (datetime.now(timezone.utc) - timedelta(days=7)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    start = week_start - timedelta(days=80)
    days = 90
    epochs = [start + timedelta(days=i) for i in range(days)]
    sma = 6795.0 - 0.03 * np.arange(days) + RNG.normal(0, 0.01, days)
    # Inject a reboost inside the target week.
    burn_idx = 80 + burn_day
    sma[burn_idx:] += 1.5
    df = pd.DataFrame({
        "norad_id": 25544, "name": "ISS (ZARYA)",
        "epoch": epochs, "sma_km": sma, "ecc": 0.0005, "inc_deg": 51.6,
        "raan_deg": 0.0, "argp_deg": 0.0, "mean_anomaly_deg": 0.0,
        "mean_motion_rev_day": 15.5, "bstar": 0.0,
        "apogee_km": sma - 6378, "perigee_km": sma - 6378,
    })
    month = df["epoch"].dt.strftime("%Y-%m")
    ledger_dir.mkdir(parents=True, exist_ok=True)
    for m, chunk in df.groupby(month):
        chunk.drop(columns=[]).to_parquet(ledger_dir / f"{m}.parquet", index=False)
    return week_start


def _seed_events(events_dir, week_start):
    events_dir.mkdir(parents=True, exist_ok=True)
    day = (week_start + timedelta(days=2)).strftime("%Y-%m-%d")
    events = [{
        "type": "conjunction_notice",
        "headline": "A and B close",
        "explanation": "...",
        "confidence": "high",
        "evidence": {
            "object_a": {"norad_id": 1, "name": "SAT-A"},
            "object_b": {"norad_id": 2, "name": "SAT-B"},
            "tca": f"{day}T03:15:00+00:00",
            "miss_distance_km": 0.42,
            "relative_speed_km_s": 12.1,
        },
        "object_ids": [1, 2],
        "tca_or_epoch": f"{day}T03:15:00+00:00",
        "generated_at": "x", "narrator": "template",
    }]
    (events_dir / f"{day}.json").write_text(json.dumps(events))


def test_compute_stats_finds_week_maneuver_and_conjunction(tmp_path):
    week_start = _seed_ledger(tmp_path / "ledger")
    _seed_events(tmp_path / "events", week_start)
    stats = compute_stats(tmp_path, week_start=week_start)
    assert stats.objects_tracked == 1
    assert stats.maneuvers_detected >= 1
    assert stats.top_maneuvers[0]["name"] == "ISS (ZARYA)"
    assert stats.conjunctions_screened == 1
    assert stats.closest_approach["miss_distance_km"] == 0.42


def test_render_markdown_has_sections(tmp_path):
    week_start = _seed_ledger(tmp_path / "ledger")
    _seed_events(tmp_path / "events", week_start)
    stats = compute_stats(tmp_path, week_start=week_start)
    md = render_markdown(stats)
    assert "State of the Orbits" in md
    assert "Closest approach of the week" in md
    assert "Notable maneuvers" in md
    assert "Not an operational safety service" in md


def test_generate_writes_files(tmp_path):
    week_start = _seed_ledger(tmp_path / "ledger")
    _seed_events(tmp_path / "events", week_start)
    result = generate(tmp_path, week_start=week_start)
    assert result["week"] == week_start.strftime("%Y-%m-%d")
    assert (tmp_path / "reports" / "latest.json").exists()


def test_empty_data_no_crash(tmp_path):
    stats = compute_stats(tmp_path)
    assert stats.objects_tracked == 0
    md = render_markdown(stats)
    assert "State of the Orbits" in md
