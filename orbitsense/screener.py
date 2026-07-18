"""Conjunction screening: spatial hashing in time, geometric filters on the side.

The production path (`screen` / `screen_satrecs`) propagates the whole
catalog on a coarse grid and, at every timestep, builds a KD-tree over all
positions to find spatially-near pairs — O(n log n) per step instead of
O(pairs x steps). A linear relative-motion estimate turns each spatial hit
into an accurate predicted miss distance and TCA; only near-threshold
candidates reach golden-section SGP4 refinement (sub-second TCA precision).
This design was forced by data: dense constellations defeat pair-oriented
screening (Starlink alone: ~31M geometrically-plausible pairs x 5.7k steps
is 10^11 distance evaluations), while the standing population of
spatially-near pairs at any instant is only thousands.

The classic geometric pre-filters (altitude-band overlap, node-radius test)
are kept as public utilities: they answer "which pairs COULD ever meet"
without any propagation, which is useful for targeted analyses and is the
traditional first stage this design replaces.

All distances are TEME km; screening-level results only (no covariance).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
from sgp4.api import Satrec

from .catalog import MU_EARTH, R_EARTH, TleRecord
from .propagator import _julian_date, propagate_many, to_satrecs

GOLDEN = (np.sqrt(5) - 1) / 2


@dataclass
class Conjunction:
    norad_a: int
    norad_b: int
    name_a: str
    name_b: str
    tca: datetime                # time of closest approach (UTC)
    miss_distance_km: float
    relative_speed_km_s: float


# ---------------------------------------------------------------- stage 1

def orbit_elements(sats: list[Satrec]) -> dict[str, np.ndarray]:
    """Vectorized geometric elements for stage-1 filtering."""
    n = np.array([s.no_kozai for s in sats]) / 60.0          # rad/s
    ecc = np.array([s.ecco for s in sats])
    inc = np.array([s.inclo for s in sats])                   # rad
    raan = np.array([s.nodeo for s in sats])                  # rad
    argp = np.array([s.argpo for s in sats])                  # rad
    sma = (MU_EARTH / n**2) ** (1.0 / 3.0)
    return {
        "sma": sma, "ecc": ecc, "inc": inc, "raan": raan, "argp": argp,
        "apogee": sma * (1 + ecc), "perigee": sma * (1 - ecc),
    }


def altitude_band_pairs(apogee: np.ndarray, perigee: np.ndarray, pad_km: float) -> np.ndarray:
    """Index pairs (i<j) whose radial shells overlap, via sweep over sorted perigees."""
    lo = perigee - pad_km
    hi = apogee + pad_km
    order = np.argsort(lo)
    lo_s, hi_s = lo[order], hi[order]
    pairs = []
    # For each object, find the run of later-sorted objects whose lo <= my hi.
    ends = np.searchsorted(lo_s, hi_s, side="right")
    for k in range(len(order)):
        e = ends[k]
        if e > k + 1:
            js = order[k + 1:e]
            i = order[k]
            pairs.append(np.stack([np.full(len(js), i), js], axis=1))
    if not pairs:
        return np.empty((0, 2), dtype=int)
    out = np.concatenate(pairs)
    return np.sort(out, axis=1)


def node_radius_filter(
    elems: dict[str, np.ndarray], pairs: np.ndarray, pad_km: float,
    coplanar_deg: float = 3.0, chunk: int = 1_000_000,
) -> np.ndarray:
    """Keep pairs whose orbit radii can actually meet near the mutual node line.

    Processed in chunks: dense constellations can push tens of millions of
    pairs through here, and the intermediate 3-vectors would otherwise need
    several GB at once.
    """
    if len(pairs) == 0:
        return pairs
    inc, raan = elems["inc"], elems["raan"]
    sma, ecc, argp = elems["sma"], elems["ecc"], elems["argp"]

    # Unit angular-momentum vectors.
    h = np.stack([
        np.sin(inc) * np.sin(raan),
        -np.sin(inc) * np.cos(raan),
        np.cos(inc),
    ], axis=1)

    kept: list[np.ndarray] = []
    for s in range(0, len(pairs), chunk):
        block = pairs[s:s + chunk]
        i, j = block[:, 0], block[:, 1]
        cross = np.cross(h[i], h[j])
        norm = np.linalg.norm(cross, axis=1)
        rel_inc = np.arcsin(np.clip(norm, 0, 1))
        coplanar = rel_inc < np.radians(coplanar_deg)

        keep = coplanar.copy()  # near-coplanar pairs pass automatically
        idx = np.nonzero(~coplanar)[0]
        if len(idx):
            node = cross[idx] / norm[idx, None]
            ii, jj = i[idx], j[idx]
            min_gap = np.full(len(idx), np.inf)
            for sign in (1.0, -1.0):
                ra = _radius_along(sma[ii], ecc[ii], inc[ii], raan[ii], argp[ii], sign * node)
                # The node line pierces orbit b on both sides; check both.
                rb = _radius_along(sma[jj], ecc[jj], inc[jj], raan[jj], argp[jj], -sign * node)
                rb2 = _radius_along(sma[jj], ecc[jj], inc[jj], raan[jj], argp[jj], sign * node)
                gap = np.minimum(np.abs(ra - rb), np.abs(ra - rb2))
                min_gap = np.minimum(min_gap, gap)
            keep[idx] = min_gap < pad_km
        kept.append(block[keep])
    return np.concatenate(kept) if kept else np.empty((0, 2), dtype=int)


def _radius_along(sma, ecc, inc, raan, argp, u: np.ndarray) -> np.ndarray:
    """Orbit radius in direction u (unit, in-plane assumed via projection).

    True anomaly of u relative to perigee gives r = p / (1 + e cos nu).
    """
    # Perifocal basis in ECI.
    cos_o, sin_o = np.cos(raan), np.sin(raan)
    cos_i, sin_i = np.cos(inc), np.sin(inc)
    cos_w, sin_w = np.cos(argp), np.sin(argp)
    # P: unit vector toward perigee; Q: 90 deg ahead in-plane.
    P = np.stack([
        cos_o * cos_w - sin_o * sin_w * cos_i,
        sin_o * cos_w + cos_o * sin_w * cos_i,
        sin_w * sin_i,
    ], axis=1)
    Q = np.stack([
        -cos_o * sin_w - sin_o * cos_w * cos_i,
        -sin_o * sin_w + cos_o * cos_w * cos_i,
        cos_w * sin_i,
    ], axis=1)
    cos_nu = np.einsum("ij,ij->i", P, u)
    sin_nu = np.einsum("ij,ij->i", Q, u)
    mag = np.hypot(cos_nu, sin_nu)
    mag = np.where(mag == 0, 1.0, mag)
    cos_nu = cos_nu / mag
    p = sma * (1 - ecc**2)
    return p / (1 + ecc * cos_nu)


# ---------------------------------------------------------------- stage 2

def _refine_tca(
    sat_a: Satrec, sat_b: Satrec, t_lo: datetime, t_hi: datetime, tol_s: float = 0.1,
) -> tuple[datetime, float, float]:
    """Golden-section minimization of true SGP4 separation on [t_lo, t_hi]."""

    def dist(t: datetime) -> tuple[float, float]:
        jd = _julian_date(t)
        day = np.floor(jd) + 0.5
        e1, ra, va = sat_a.sgp4(day, jd - day)
        e2, rb, vb = sat_b.sgp4(day, jd - day)
        if e1 or e2:
            return np.inf, np.inf
        d = float(np.linalg.norm(np.subtract(ra, rb)))
        rv = float(np.linalg.norm(np.subtract(va, vb)))
        return d, rv

    a, b = t_lo, t_hi
    c = b - timedelta(seconds=GOLDEN * (b - a).total_seconds())
    d_ = a + timedelta(seconds=GOLDEN * (b - a).total_seconds())
    fc, _ = dist(c)
    fd, _ = dist(d_)
    while (b - a).total_seconds() > tol_s:
        if fc < fd:
            b, d_, fd = d_, c, fc
            c = b - timedelta(seconds=GOLDEN * (b - a).total_seconds())
            fc, _ = dist(c)
        else:
            a, c, fc = c, d_, fd
            d_ = a + timedelta(seconds=GOLDEN * (b - a).total_seconds())
            fd, _ = dist(d_)
    tca = a + (b - a) / 2
    miss, rel_speed = dist(tca)
    return tca, miss, rel_speed


def screen(
    records: list[TleRecord],
    start: datetime,
    hours: float = 72.0,
    threshold_km: float = 5.0,
    coarse_step_s: float = 15.0,
) -> list[Conjunction]:
    """Full catalog screen. Returns conjunctions under threshold, sorted by miss."""
    sats, names = to_satrecs(records)
    return screen_satrecs(
        sats, names, start,
        hours=hours, threshold_km=threshold_km, coarse_step_s=coarse_step_s,
    )


def screen_satrecs(
    sats: list[Satrec],
    names: list[str],
    start: datetime,
    hours: float = 72.0,
    threshold_km: float = 5.0,
    coarse_step_s: float = 15.0,
    max_rel_speed_km_s: float = 16.0,
    time_chunk_hours: float = 3.0,
) -> list[Conjunction]:
    """Spatial-hash screening: per-timestep KD-tree + linear miss estimate.

    Per-pair time scanning breaks down on dense constellations (Starlink
    alone yields ~31M geometrically-plausible pairs; times 5.7k steps that
    is 10^11 distance evaluations). Instead, each coarse timestep builds a
    KD-tree over all positions — O(n log n) — and queries pairs within a
    radius that bounds how far a sub-threshold approach can hide between
    samples (max closing speed x half step). Measured on live Starlink data
    this keeps ~6.5k standing pairs per step, and the whole tree pass runs
    in tens of milliseconds.

    For each spatial hit, the linear relative-motion closest approach
    (perpendicular component of separation w.r.t. relative velocity) gives
    an accurate miss estimate from a single sample — valid precisely near
    conjunctions, where relative motion is locally straight. Only hits whose
    estimate lands near the threshold reach golden-section SGP4 refinement.

    Time is processed in chunks of `time_chunk_hours` to bound memory
    (positions+velocities for 27k objects x 3h @ 15s stay under ~1 GB).
    """
    from scipy.spatial import cKDTree

    radius = max_rel_speed_km_s * (coarse_step_s / 2.0) * 1.1 + threshold_km
    refine_gate = threshold_km * 3.0 + 1.0
    step = timedelta(seconds=coarse_step_s)

    total_steps = int(hours * 3600 / coarse_step_s)
    steps_per_chunk = max(2, int(time_chunk_hours * 3600 / coarse_step_s))

    cand_i: list[np.ndarray] = []
    cand_j: list[np.ndarray] = []
    cand_t: list[np.ndarray] = []      # estimated TCA, seconds from start
    cand_est: list[np.ndarray] = []    # estimated miss, km
    cand_wide: list[np.ndarray] = []   # slow drifter: needs a wide bracket

    for s0 in range(0, total_steps + 1, steps_per_chunk):
        n = min(steps_per_chunk, total_steps + 1 - s0)
        chunk_start = start + s0 * step
        e, r, v = propagate_many(
            sats, chunk_start, (n - 1) * coarse_step_s / 3600.0, coarse_step_s,
        )
        # Park failed propagations far away so they can never pair.
        r = np.where((e != 0)[:, :, None], 1e12, r)
        for k in range(n):
            tree = cKDTree(r[:, k, :])
            pk = tree.query_pairs(radius, output_type="ndarray")
            if len(pk) == 0:
                continue
            dr = r[pk[:, 0], k] - r[pk[:, 1], k]
            dv = v[pk[:, 0], k] - v[pk[:, 1], k]
            d2 = np.einsum("ij,ij->i", dr, dr)
            drv = np.einsum("ij,ij->i", dr, dv)
            dv2 = np.maximum(np.einsum("ij,ij->i", dv, dv), 1e-12)
            est_miss2 = np.maximum(d2 - drv**2 / dv2, 0.0)
            dt_est = -drv / dv2  # seconds to linear closest approach

            # Candidate if the linear estimate is near threshold AND its TCA
            # falls by this sample (adjacent samples cover the rest), or the
            # pair is simply already inside the refine gate (slow drifters,
            # where curvature makes the linear TCA estimate unreliable —
            # they are flagged `wide` and get a bucket-sized refine bracket).
            near = (est_miss2 < refine_gate**2) & (np.abs(dt_est) <= coarse_step_s)
            close = d2 < refine_gate**2
            m = near | close
            if not m.any():
                continue
            t_off = (s0 + k) * coarse_step_s + np.where(near[m], dt_est[m], 0.0)
            cand_i.append(pk[m, 0])
            cand_j.append(pk[m, 1])
            cand_t.append(t_off)
            cand_est.append(np.where(near[m], np.sqrt(est_miss2[m]), np.sqrt(d2[m])))
            cand_wide.append(close[m] & ~near[m])

    if not cand_i:
        return []

    ci = np.concatenate(cand_i)
    cj = np.concatenate(cand_j)
    ct = np.concatenate(cand_t)
    ce = np.concatenate(cand_est)
    cw = np.concatenate(cand_wide)

    # One refinement per (pair, ~10 min bucket): keep the best estimate.
    bucket_s = 600.0
    buckets: dict[tuple[int, int, int], int] = {}
    for idx in range(len(ci)):
        key = (int(ci[idx]), int(cj[idx]), int(ct[idx] // bucket_s))
        best = buckets.get(key)
        if best is None or ce[idx] < ce[best]:
            buckets[key] = idx

    results: dict[tuple[int, int, int], Conjunction] = {}
    for (gi, gj, _), idx in buckets.items():
        t_mid = start + timedelta(seconds=float(ct[idx]))
        # Fast crossings have a trustworthy linear TCA: tight bracket.
        # Slow drifters' minima wander anywhere inside the bucket: the
        # bracket must span it (d(t) is unimodal on this scale — relative
        # oscillation periods are ~an orbit, far longer than a bucket).
        half = timedelta(seconds=bucket_s / 2 + 2 * coarse_step_s) if cw[idx] \
            else 2 * step
        tca, miss, rel_speed = _refine_tca(
            sats[gi], sats[gj], t_mid - half, t_mid + half,
        )
        if miss <= threshold_km:
            key = (gi, gj, int(tca.timestamp() // 300))  # dedupe within 5 min
            existing = results.get(key)
            if existing is None or miss < existing.miss_distance_km:
                results[key] = Conjunction(
                    sats[gi].satnum, sats[gj].satnum, names[gi], names[gj],
                    tca, miss, rel_speed,
                )
    return sorted(results.values(), key=lambda c: c.miss_distance_km)
