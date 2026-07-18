"""TLE ingestion and the element-history ledger.

Pulls GP data from CelesTrak (no auth), extracts mean orbital elements per
object, and appends them to a monthly-partitioned Parquet ledger. The ledger
is the time-series foundation for maneuver detection: one row per object per
TLE epoch.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests
from sgp4.api import Satrec

MU_EARTH = 398600.4418  # km^3/s^2
R_EARTH = 6378.137  # km

CELESTRAK_GP = "https://celestrak.org/NORAD/elements/gp.php"

# CelesTrak blocks clients that re-download the same GP group more than once
# per ~2h window (the data only updates on that cadence). Fetch each group at
# most once per pipeline run and identify ourselves politely.
USER_AGENT = "OrbitSense/0.1 (open-source SDA copilot; github.com/orbitsense)"

LEDGER_COLUMNS = [
    "norad_id", "name", "epoch", "sma_km", "ecc", "inc_deg",
    "raan_deg", "argp_deg", "mean_anomaly_deg", "mean_motion_rev_day",
    "bstar", "apogee_km", "perigee_km",
]


@dataclass
class TleRecord:
    name: str
    line1: str
    line2: str


def fetch_group_tles(group: str = "active", session: requests.Session | None = None) -> list[TleRecord]:
    """Fetch a CelesTrak GP group as 3-line TLE records."""
    sess = session or requests
    resp = sess.get(
        CELESTRAK_GP,
        params={"GROUP": group, "FORMAT": "tle"},
        headers={"User-Agent": USER_AGENT},
        timeout=120,
    )
    resp.raise_for_status()
    return parse_3le(resp.text)


def parse_3le(text: str) -> list[TleRecord]:
    lines = [l.rstrip() for l in text.splitlines() if l.strip()]
    records = []
    i = 0
    while i < len(lines) - 2:
        if lines[i + 1].startswith("1 ") and lines[i + 2].startswith("2 "):
            records.append(TleRecord(lines[i].strip(), lines[i + 1], lines[i + 2]))
            i += 3
        else:
            i += 1
    return records


def tle_epoch(sat: Satrec) -> datetime:
    year = sat.epochyr + (2000 if sat.epochyr < 57 else 1900)
    return datetime(year, 1, 1, tzinfo=timezone.utc) + timedelta(days=sat.epochdays - 1)


def elements_row(rec: TleRecord) -> dict | None:
    """Mean elements for one TLE, or None if the TLE fails to parse."""
    sat = Satrec.twoline2rv(rec.line1, rec.line2)
    if sat.error != 0:
        return None
    n_rad_s = sat.no_kozai / 60.0
    if n_rad_s <= 0:
        return None
    sma = (MU_EARTH / n_rad_s**2) ** (1.0 / 3.0)
    return {
        "norad_id": sat.satnum,
        "name": rec.name,
        "epoch": tle_epoch(sat),
        "sma_km": sma,
        "ecc": sat.ecco,
        "inc_deg": math.degrees(sat.inclo),
        "raan_deg": math.degrees(sat.nodeo),
        "argp_deg": math.degrees(sat.argpo),
        "mean_anomaly_deg": math.degrees(sat.mo),
        "mean_motion_rev_day": sat.no_kozai * 1440.0 / (2.0 * math.pi),
        "bstar": sat.bstar,
        "apogee_km": sma * (1 + sat.ecco) - R_EARTH,
        "perigee_km": sma * (1 - sat.ecco) - R_EARTH,
    }


def records_to_frame(records: list[TleRecord]) -> pd.DataFrame:
    rows = [r for r in (elements_row(rec) for rec in records) if r is not None]
    return pd.DataFrame(rows, columns=LEDGER_COLUMNS)


def append_to_ledger(frame: pd.DataFrame, ledger_dir: str | Path) -> list[Path]:
    """Append element rows into monthly parquet partitions, deduped by (norad_id, epoch)."""
    ledger = Path(ledger_dir)
    ledger.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    frame = frame.copy()
    frame["month"] = frame["epoch"].dt.strftime("%Y-%m")
    for month, chunk in frame.groupby("month"):
        path = ledger / f"{month}.parquet"
        chunk = chunk.drop(columns="month")
        if path.exists():
            existing = pd.read_parquet(path)
            chunk = pd.concat([existing, chunk], ignore_index=True)
        chunk = (
            chunk.drop_duplicates(subset=["norad_id", "epoch"], keep="last")
            .sort_values(["norad_id", "epoch"])
            .reset_index(drop=True)
        )
        chunk.to_parquet(path, index=False)
        written.append(path)
    return written


def ingest(group: str = "active", ledger_dir: str | Path = "data/ledger") -> dict:
    """Daily ingestion entry point: fetch, extract elements, append to ledger."""
    records = fetch_group_tles(group)
    frame = records_to_frame(records)
    written = append_to_ledger(frame, ledger_dir)
    return {
        "fetched": len(records),
        "parsed": len(frame),
        "partitions": [str(p) for p in written],
    }
