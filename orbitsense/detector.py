"""Maneuver detection: changepoint analysis on the element-history ledger.

A maneuver shows up as a step change in mean elements (SMA for in-track
burns, inclination for plane changes) on top of smooth secular drift (drag
decay, J2 precession) and TLE noise. Detection runs on first differences of
the per-object series:

  1. Estimate the object's own noise floor robustly (median/MAD of epoch-to-
     epoch differences) — every object gets a personal baseline, so a quiet
     GEO bird and a wobbly cubesat are judged by their own history.
  2. Flag differences that are simultaneously statistical outliers
     (|z| >= z_thresh on the MAD scale) and physically meaningful
     (|delta| >= abs_floor_km).
  3. Merge flags closer together than min_gap so one burn spread over two
     TLE epochs reports as one event.

`ruptures` (PELT) is used as a cross-check segmentation for calibration
work; the MAD detector is the production path because it is O(n), robust to
uneven epoch spacing, and its threshold has physical units.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd


@dataclass
class ManeuverEvent:
    norad_id: int
    column: str
    epoch: datetime            # epoch of the post-maneuver element set
    delta: float               # step size in the column's units (km, deg, ...)
    z_score: float             # robust z of the step vs this object's noise
    baseline_mad: float        # the noise floor used (same units)


def _robust_scale(diffs: np.ndarray) -> tuple[float, float]:
    med = float(np.median(diffs))
    mad = float(np.median(np.abs(diffs - med)))
    return med, 1.4826 * mad  # MAD -> sigma-equivalent


def detect_steps(
    series: pd.DataFrame,
    norad_id: int,
    column: str = "sma_km",
    z_thresh: float = 5.0,
    abs_floor: float = 0.05,
    min_gap_hours: float = 36.0,  # > daily TLE cadence, so a burn spread
                                  # across consecutive daily epochs merges
) -> list[ManeuverEvent]:
    """Detect step changes in one element column of one object's history.

    `series` needs columns [epoch, <column>]; uneven epoch spacing is fine.
    `abs_floor` is in the column's units (0.05 km = 50 m of SMA).
    """
    df = (
        series[["epoch", column]]
        .dropna()
        .drop_duplicates(subset="epoch")
        .sort_values("epoch")
        .reset_index(drop=True)
    )
    if len(df) < 8:
        return []

    values = df[column].to_numpy(dtype=float)
    epochs = df["epoch"]
    diffs = np.diff(values)

    med, scale = _robust_scale(diffs)
    if scale == 0:
        scale = max(np.std(diffs), 1e-12)
    z = (diffs - med) / scale

    flagged = np.nonzero((np.abs(z) >= z_thresh) & (np.abs(diffs) >= abs_floor))[0]
    if len(flagged) == 0:
        return []

    events: list[ManeuverEvent] = []
    gap = pd.Timedelta(hours=min_gap_hours)
    group: list[int] = [int(flagged[0])]
    for k in flagged[1:]:
        if epochs.iloc[int(k) + 1] - epochs.iloc[group[-1] + 1] <= gap:
            group.append(int(k))
        else:
            events.append(_merge_group(group, epochs, diffs, z, scale, norad_id, column))
            group = [int(k)]
    events.append(_merge_group(group, epochs, diffs, z, scale, norad_id, column))
    return events


def _merge_group(group, epochs, diffs, z, scale, norad_id, column) -> ManeuverEvent:
    delta = float(diffs[group].sum())
    peak = max(group, key=lambda k: abs(z[k]))
    return ManeuverEvent(
        norad_id=norad_id,
        column=column,
        epoch=epochs.iloc[peak + 1].to_pydatetime(),
        delta=delta,
        z_score=float(z[peak]),
        baseline_mad=float(scale),
    )


def segment_series(values: np.ndarray, penalty: float = 3.0) -> list[int]:
    """PELT changepoint indices (ruptures) — calibration cross-check only."""
    import ruptures as rpt

    if len(values) < 10:
        return []
    algo = rpt.Pelt(model="rbf", min_size=3).fit(values.reshape(-1, 1))
    return [int(i) for i in algo.predict(pen=penalty)[:-1]]


def scan_ledger(
    ledger: pd.DataFrame,
    column: str = "sma_km",
    z_thresh: float = 5.0,
    abs_floor: float = 0.05,
) -> list[ManeuverEvent]:
    """Run step detection for every object in a ledger frame."""
    events: list[ManeuverEvent] = []
    for norad_id, group in ledger.groupby("norad_id"):
        events.extend(
            detect_steps(group, int(norad_id), column=column,
                         z_thresh=z_thresh, abs_floor=abs_floor)
        )
    return sorted(events, key=lambda e: e.epoch)
