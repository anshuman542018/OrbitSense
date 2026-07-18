"""SGP4 propagation wrappers and ephemeris generation.

All positions are TEME frame, kilometers. Vectorized propagation via
SatrecArray keeps the full catalog tractable on a single free CI runner
(~16k objects x 72h @ 60s benchmarks at ~40s).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
from sgp4.api import SGP4_ERRORS, Satrec, SatrecArray

from .catalog import TleRecord


def to_satrecs(records: list[TleRecord]) -> tuple[list[Satrec], list[str]]:
    """Parse TLE records; returns (satrecs, names) with unparseable ones dropped."""
    sats, names = [], []
    for rec in records:
        sat = Satrec.twoline2rv(rec.line1, rec.line2)
        if sat.error == 0:
            sats.append(sat)
            names.append(rec.name)
    return sats, names


def time_grid(start: datetime, hours: float, step_s: float) -> tuple[np.ndarray, np.ndarray]:
    """Julian date arrays (jd, fr) for SatrecArray over [start, start+hours]."""
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    n = int(hours * 3600 / step_s) + 1
    offsets = np.arange(n) * (step_s / 86400.0)
    jd0 = _julian_date(start)
    jd = np.full(n, np.floor(jd0) + 0.5)
    fr = (jd0 - jd) + offsets
    return jd, fr


def _julian_date(dt: datetime) -> float:
    dt = dt.astimezone(timezone.utc)
    year, month = dt.year, dt.month
    if month <= 2:
        year -= 1
        month += 12
    a = year // 100
    b = 2 - a + a // 4
    day_frac = (dt.hour + dt.minute / 60 + (dt.second + dt.microsecond / 1e6) / 3600) / 24
    return (
        int(365.25 * (year + 4716))
        + int(30.6001 * (month + 1))
        + dt.day + b - 1524.5 + day_frac
    )


def propagate_many(
    sats: list[Satrec], start: datetime, hours: float, step_s: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Propagate many satellites over a time grid.

    Returns (errors[n_sats, n_times], positions_km[n_sats, n_times, 3],
    velocities_km_s[n_sats, n_times, 3]) in TEME.
    """
    jd, fr = time_grid(start, hours, step_s)
    arr = SatrecArray(sats)
    e, r, v = arr.sgp4(jd, fr)
    return e, r, v


def propagate_one(
    sat: Satrec, times: list[datetime]
) -> tuple[np.ndarray, np.ndarray]:
    """Positions/velocities for one satellite at arbitrary datetimes."""
    jds = np.array([_julian_date(t) for t in times])
    jd = np.floor(jds) + 0.5
    fr = jds - jd
    e, r, v = sat.sgp4_array(jd, fr)
    bad = e != 0
    if bad.any():
        first = int(np.argmax(bad))
        raise ValueError(f"SGP4 error at {times[first]}: {SGP4_ERRORS.get(int(e[first]), e[first])}")
    return np.asarray(r), np.asarray(v)


def grid_datetimes(start: datetime, hours: float, step_s: float) -> list[datetime]:
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    n = int(hours * 3600 / step_s) + 1
    return [start + timedelta(seconds=i * step_s) for i in range(n)]
