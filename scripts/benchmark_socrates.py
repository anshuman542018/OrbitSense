"""Benchmark OrbitSense screening against CelesTrak SOCRATES Plus.

SOCRATES Plus publishes ~7 days of conjunctions for the full catalog. This
script compares the subset both systems can see — Starlink-vs-Starlink
events inside a shared 24 h window — and reports recall + agreement stats.

Differences to expect (documented, not hidden): the two systems run on
different TLE epochs, and SOCRATES applies operational-status logic; ranges
at TCA will differ by TLE drift. Matching is by unordered NORAD pair with
TCA within 5 minutes.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from orbitsense.catalog import fetch_group_tles
from orbitsense.screener import screen

SOCRATES_CSV = "data/cache/socrates-minRange.csv"
THRESHOLD_KM = 5.0
WINDOW_H = 24.0
MATCH_TCA_S = 300.0


def main() -> int:
    soc = pd.read_csv(SOCRATES_CSV)
    soc["TCA"] = pd.to_datetime(soc["TCA"], utc=True)

    records = fetch_group_tles("starlink", max_age_hours=48)
    print(f"{len(records)} Starlink TLEs; {len(soc)} SOCRATES rows")

    start = datetime.now(timezone.utc)
    end = start + timedelta(hours=WINDOW_H)

    is_sl_1 = soc["OBJECT_NAME_1"].str.contains("STARLINK", case=False)
    is_sl_2 = soc["OBJECT_NAME_2"].str.contains("STARLINK", case=False)
    ref = soc[
        is_sl_1 & is_sl_2
        & (soc["TCA"] >= start) & (soc["TCA"] <= end)
        & (soc["TCA_RANGE"] <= THRESHOLD_KM)
    ].copy()
    print(f"SOCRATES Starlink-Starlink events in window under {THRESHOLD_KM} km: {len(ref)}")

    print(f"Screening {WINDOW_H:.0f}h from {start:%Y-%m-%d %H:%M} ...")
    ours = screen(records, start, hours=WINDOW_H, threshold_km=THRESHOLD_KM)
    print(f"OrbitSense events: {len(ours)}")

    ours_ix: dict[tuple[int, int], list] = {}
    for c in ours:
        key = (min(c.norad_a, c.norad_b), max(c.norad_a, c.norad_b))
        ours_ix.setdefault(key, []).append(c)

    matched, range_deltas, tca_deltas = 0, [], []
    misses = []
    for _, row in ref.iterrows():
        key = (min(row.NORAD_CAT_ID_1, row.NORAD_CAT_ID_2),
               max(row.NORAD_CAT_ID_1, row.NORAD_CAT_ID_2))
        best = None
        for c in ours_ix.get(key, []):
            dt = abs((c.tca - row.TCA.to_pydatetime()).total_seconds())
            if dt <= MATCH_TCA_S and (best is None or dt < best[0]):
                best = (dt, c)
        if best:
            matched += 1
            tca_deltas.append(best[0])
            range_deltas.append(abs(best[1].miss_distance_km - row.TCA_RANGE))
        else:
            misses.append((key, row.TCA, row.TCA_RANGE))

    recall = matched / len(ref) * 100 if len(ref) else float("nan")
    print(f"\n=== BENCHMARK ===")
    print(f"Recall vs SOCRATES: {matched}/{len(ref)}  ({recall:.1f}%)")
    if range_deltas:
        print(f"TCA agreement:   median {np.median(tca_deltas):.1f}s, p90 {np.percentile(tca_deltas, 90):.1f}s")
        print(f"Range agreement: median {np.median(range_deltas)*1000:.0f} m, p90 {np.percentile(range_deltas, 90)*1000:.0f} m")

    # Recall vs SOCRATES element age: Starlink maneuvers daily, so agreement
    # should collapse as the elements SOCRATES used grow stale. If it does,
    # the disagreement is data freshness, not screening math.
    matched_keys = set()
    for _, row in ref.iterrows():
        key = (min(row.NORAD_CAT_ID_1, row.NORAD_CAT_ID_2),
               max(row.NORAD_CAT_ID_1, row.NORAD_CAT_ID_2))
        for c in ours_ix.get(key, []):
            if abs((c.tca - row.TCA.to_pydatetime()).total_seconds()) <= MATCH_TCA_S:
                matched_keys.add((key, row.TCA))
                break
    ref["dse_max"] = ref[["DSE_1", "DSE_2"]].max(axis=1)
    ref["hit"] = [
        ((min(r.NORAD_CAT_ID_1, r.NORAD_CAT_ID_2),
          max(r.NORAD_CAT_ID_1, r.NORAD_CAT_ID_2)), r.TCA) in matched_keys
        for r in ref.itertuples()
    ]
    print("\nRecall vs age of the elements SOCRATES used (max of the pair):")
    for lo, hi in [(0, 1), (1, 2), (2, 4), (4, 20)]:
        band = ref[(ref.dse_max >= lo) & (ref.dse_max < hi)]
        if len(band):
            print(f"  DSE {lo}-{hi} days: {band.hit.sum()}/{len(band)}"
                  f"  ({band.hit.mean()*100:.0f}%)")

    for key, tca, rng in misses[:5]:
        print(f"  missed: {key}  tca={tca:%m-%d %H:%M:%S}  range={rng:.3f} km")
    return 0


if __name__ == "__main__":
    sys.exit(main())
