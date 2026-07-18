"""Phase 0 proof #1 (v2): ISS reboosts from the BI4PYM/AutoTLE git history.

That repo snapshots amateur-satellite TLEs (ISS first) several times a day.
One commit per day over ~90 days gives a dense, free ISS TLE history without
a Space-Track account. Reboosts appear as upward steps in semi-major axis.

Usage: python scripts/phase0_iss_history.py [days]
Requires: gh CLI authenticated (used for the commit listing only).
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import requests
from sgp4.api import Satrec

MU_EARTH = 398600.4418  # km^3/s^2
REPO = "BI4PYM/AutoTLE"
PATH = "AutoTLE.txt"


def daily_commits(days: int) -> dict[str, str]:
    """Return {YYYY-MM-DD: sha}, one commit per day touching active.txt."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    out: dict[str, str] = {}
    page = 1
    while True:
        raw = subprocess.run(
            ["gh", "api",
             f"repos/{REPO}/commits?path={PATH}&since={since}&per_page=100&page={page}"],
            capture_output=True, text=True, check=True,
        ).stdout
        commits = json.loads(raw)
        if not commits:
            break
        for c in commits:
            day = c["commit"]["author"]["date"][:10]
            out.setdefault(day, c["sha"])  # newest listed first; keep first per day
        page += 1
    return out


def iss_sma(sha: str) -> tuple[datetime, float] | None:
    url = f"https://raw.githubusercontent.com/{REPO}/{sha}/{PATH}"
    try:
        text = requests.get(url, timeout=120).text
    except requests.RequestException:
        return None
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip().replace(" ", "").startswith("ISS(ZARYA)") and i + 2 < len(lines):
            sat = Satrec.twoline2rv(lines[i + 1].strip(), lines[i + 2].strip())
            n = sat.no_kozai / 60.0  # rad/s
            a = (MU_EARTH / n**2) ** (1.0 / 3.0)
            year = sat.epochyr + (2000 if sat.epochyr < 57 else 1900)
            epoch = datetime(year, 1, 1) + timedelta(days=sat.epochdays - 1)
            return epoch, a
    return None


def main() -> int:
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 90
    print(f"Listing one commit per day over the last {days} days ...")
    commits = daily_commits(days)
    print(f"  {len(commits)} days with snapshots")

    points: dict[str, tuple[datetime, float]] = {}
    for day in sorted(commits):
        got = iss_sma(commits[day])
        if got is None:
            continue
        epoch, a = got
        points[epoch.isoformat()] = (epoch, a)
        print(f"  {day}  epoch={epoch:%Y-%m-%d %H:%M}  SMA={a:.3f} km")

    series = sorted(points.values())
    if len(series) < 20:
        print("Too few points; aborting.")
        return 1

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
    print(f"SMA range over window: {(max(smas) - min(smas)) * 1000:.0f} m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
