"""Phase 0 proof #1: ISS reboosts are visible in public TLE history.

Space-Track needs an account, so this script reconstructs ISS TLE history from
Wayback Machine snapshots of CelesTrak's stations file and plots semi-major
axis over time. Reboosts appear as upward steps; drag decay as the downward
slope between them. If the steps are visible, the maneuver-detection concept
works on public data.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import requests
from sgp4.api import Satrec

MU_EARTH = 398600.4418  # km^3/s^2
CDX_URL = "http://web.archive.org/cdx/search/cdx"
STATIONS_URL = "celestrak.org/NORAD/elements/stations.txt"


def list_snapshots(days: int = 130) -> list[str]:
    since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y%m%d")
    r = requests.get(
        CDX_URL,
        params={
            "url": STATIONS_URL,
            "from": since,
            "output": "json",
            "filter": "statuscode:200",
            "collapse": "timestamp:8",  # at most one snapshot per day
            "fl": "timestamp",
        },
        timeout=60,
    )
    r.raise_for_status()
    rows = json.loads(r.text)
    return [row[0] for row in rows[1:]]  # skip header row


def fetch_iss_tle(timestamp: str) -> tuple[str, str] | None:
    url = f"http://web.archive.org/web/{timestamp}id_/https://{STATIONS_URL}"
    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
    except requests.RequestException:
        return None
    lines = r.text.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("ISS (ZARYA)") and i + 2 < len(lines):
            return lines[i + 1].strip(), lines[i + 2].strip()
    return None


def sma_km(line1: str, line2: str) -> tuple[datetime, float]:
    sat = Satrec.twoline2rv(line1, line2)
    n_rad_s = sat.no_kozai / 60.0  # rad/min -> rad/s
    a = (MU_EARTH / n_rad_s**2) ** (1.0 / 3.0)
    year = sat.epochyr + (2000 if sat.epochyr < 57 else 1900)
    epoch = datetime(year, 1, 1) + timedelta(days=sat.epochdays - 1)
    return epoch, a


def main() -> int:
    print("Listing Wayback snapshots of CelesTrak stations.txt ...")
    snapshots = list_snapshots()
    print(f"  {len(snapshots)} daily snapshots found")

    points: dict[str, tuple[datetime, float]] = {}
    for ts in snapshots:
        tle = fetch_iss_tle(ts)
        if tle is None:
            continue
        epoch, a = sma_km(*tle)
        points[epoch.isoformat()] = (epoch, a)  # dedupe identical epochs
        print(f"  {ts[:8]}  epoch={epoch:%Y-%m-%d %H:%M}  SMA={a:.3f} km")

    if len(points) < 10:
        print("Not enough snapshots to plot — try increasing the day range.")
        return 1

    series = sorted(points.values())
    epochs = [p[0] for p in series]
    smas = [p[1] for p in series]

    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(epochs, smas, marker="o", markersize=3, linewidth=1)
    ax.set_title("ISS (ZARYA) semi-major axis from public TLEs — reboosts are the upward steps")
    ax.set_xlabel("TLE epoch")
    ax.set_ylabel("Semi-major axis (km)")
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    out = "scripts/phase0_iss_sma.png"
    fig.savefig(out, dpi=150)
    print(f"\nSaved plot: {out}  ({len(series)} points, "
          f"{epochs[0]:%Y-%m-%d} .. {epochs[-1]:%Y-%m-%d})")
    rng = max(smas) - min(smas)
    print(f"SMA range over window: {rng*1000:.0f} m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
