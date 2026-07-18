"""Phase 0 proof #2: full-catalog SGP4 propagation is feasible on free compute.

Fetches the CelesTrak active-satellite catalog (no auth) and times a
vectorized SatrecArray propagation over a 72h window. Scales linearly, so
the timing here predicts the full ~27k-object catalog cost on a GitHub
Actions runner.
"""

from __future__ import annotations

import sys
import time

import numpy as np
import requests
from sgp4.api import Satrec, SatrecArray

CELESTRAK = "https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle"


def fetch_catalog() -> list[Satrec]:
    text = requests.get(CELESTRAK, timeout=120).text
    lines = [l.rstrip() for l in text.splitlines() if l.strip()]
    sats = []
    for i in range(0, len(lines) - 2, 3):
        if lines[i + 1].startswith("1 ") and lines[i + 2].startswith("2 "):
            sats.append(Satrec.twoline2rv(lines[i + 1], lines[i + 2]))
    return sats


def main() -> int:
    print("Fetching CelesTrak active catalog ...")
    t0 = time.perf_counter()
    sats = fetch_catalog()
    print(f"  {len(sats)} objects in {time.perf_counter() - t0:.1f}s")

    arr = SatrecArray(sats)
    # 72h at 60s steps — the fine end of what stage-2 screening would ever need
    # across the whole catalog at once.
    epoch_jd = sats[0].jdsatepoch
    steps = 72 * 60
    jd = np.full(steps, epoch_jd)
    fr = np.arange(steps) * (60.0 / 86400.0)

    print(f"Propagating {len(sats)} objects x {steps} steps (72h @ 60s) ...")
    t0 = time.perf_counter()
    e, r, v = arr.sgp4(jd, fr)
    dt = time.perf_counter() - t0
    ok = int((e == 0).all(axis=1).sum())
    n_pos = r.shape[0] * r.shape[1]
    print(f"  {dt:.1f}s total — {n_pos/dt/1e6:.1f}M position evaluations/s")
    print(f"  {ok}/{len(sats)} objects propagated cleanly across the window")
    full_catalog = 27000
    print(f"  Extrapolated to {full_catalog} objects: ~{dt * full_catalog / len(sats):.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
