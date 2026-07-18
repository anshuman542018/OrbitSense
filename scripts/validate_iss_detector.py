"""Validate the maneuver detector against real ISS history.

Builds the same 90-day ISS SMA series as phase0_iss_history.py (cached to
CSV), runs the production step detector, and reports what it found. Ground
truth for this window: the SMA plot shows exactly two reboosts (~2026-06-10
and ~2026-07-03).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from phase0_iss_history import daily_commits, iss_sma  # noqa: E402

from orbitsense.detector import detect_steps  # noqa: E402

CACHE = Path("data/cache/iss_history_90d.csv")


def build_series(days: int = 90) -> pd.DataFrame:
    if CACHE.exists():
        return pd.read_csv(CACHE, parse_dates=["epoch"])
    commits = daily_commits(days)
    rows = []
    for day in sorted(commits):
        got = iss_sma(commits[day])
        if got:
            rows.append({"epoch": got[0], "sma_km": got[1]})
    df = pd.DataFrame(rows).drop_duplicates(subset="epoch").sort_values("epoch")
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(CACHE, index=False)
    return df


def main() -> int:
    df = build_series()
    print(f"{len(df)} ISS element points, {df.epoch.min():%Y-%m-%d} .. {df.epoch.max():%Y-%m-%d}")
    events = detect_steps(df, norad_id=25544, column="sma_km")
    print(f"\nDetected {len(events)} maneuver event(s):")
    for e in events:
        print(f"  {e.epoch:%Y-%m-%d %H:%M}  dSMA={e.delta*1000:+.0f} m  "
              f"z={e.z_score:.1f}  noise_floor={e.baseline_mad*1000:.0f} m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
