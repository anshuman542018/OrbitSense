"""Two-stage conjunction screening.

Naive all-pairs screening of a 16k-object catalog is 128M pairs — infeasible
at fine time steps. The classic smart-filter design used here:

Stage 1 (geometry, no propagation):
  a) Altitude-band filter — a pair can only approach if their
     [perigee - pad, apogee + pad] shells overlap.
  b) Node-radius filter — two orbits in different planes can only come close
     near the mutual line of nodes. Each orbit's radius along the +/- node
     direction is computed from its ellipse; the pair survives only if the
     radii differ by less than the pad somewhere on the node line. Near-
     coplanar pairs (relative inclination below a few degrees) skip this
     test, since they can approach anywhere on the orbit.

Stage 2 (propagation):
  Every surviving object is propagated ONCE on a coarse grid (not per pair).
  Per-pair distance series are scanned for local minima below a conservative
  gate (a 1 km miss can look like hundreds of km at the nearest coarse
  sample, so the gate accounts for maximum closing speed x half step). Each
  candidate minimum is then refined by golden-section search on the true
  SGP4 relative distance, down to sub-second time resolution.

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
    coplanar_deg: float = 3.0,
) -> np.ndarray:
    """Keep pairs whose orbit radii can actually meet near the mutual node line."""
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

    i, j = pairs[:, 0], pairs[:, 1]
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
            rb = _radius_along(sma[jj], ecc[jj], inc[jj], raan[jj], argp[jj], -sign * node)
            # Node direction for orbit b is anti-parallel: h_i x h_j points along
            # ascending node of a relative to b's plane crossing; check both signs
            # for both orbits to be safe.
            rb2 = _radius_along(sma[jj], ecc[jj], inc[jj], raan[jj], argp[jj], sign * node)
            gap = np.minimum(np.abs(ra - rb), np.abs(ra - rb2))
            min_gap = np.minimum(min_gap, gap)
        keep[idx] = min_gap < pad_km
    return pairs[keep]


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

def _pair_minima(
    r: np.ndarray,
    v: np.ndarray,
    pairs: np.ndarray,
    step_s: float,
    threshold_km: float,
    chunk: int = 1000,
) -> list[tuple[int, int]]:
    """(pair_index, time_index) of coarse local distance minima worth refining.

    The gate is velocity-aware: a candidate minimum survives only if its
    coarse distance could hide a sub-threshold approach given the pair's
    ACTUAL closing speed there (relspeed x half-step, with 25% margin).
    A worst-case constant gate (~460 km in LEO) drowns stage 2 in
    same-shell constellation pairs; the dynamic gate keeps coplanar pairs
    (mm/s..m/s closing speeds) at a few-km gate while preserving the wide
    gate for genuine fast plane crossings.
    """
    hits: list[tuple[int, int]] = []
    r32 = r.astype(np.float32)
    v32 = v.astype(np.float32)
    for s in range(0, len(pairs), chunk):
        block = pairs[s:s + chunk]
        d = np.linalg.norm(r32[block[:, 0]] - r32[block[:, 1]], axis=2)
        interior = (d[:, 1:-1] <= d[:, :-2]) & (d[:, 1:-1] <= d[:, 2:])
        bi, ti = np.nonzero(interior)
        if len(bi) == 0:
            continue
        ti = ti + 1
        rel_speed = np.linalg.norm(
            v32[block[bi, 0], ti] - v32[block[bi, 1], ti], axis=1,
        )
        gate = rel_speed * (step_s / 2.0) * 1.25 + threshold_km
        keep = d[bi, ti] < gate
        for b, t in zip(bi[keep], ti[keep]):
            hits.append((s + int(b), int(t)))
    return hits


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
    pad_km: float = 25.0,
    coarse_step_s: float = 60.0,
) -> list[Conjunction]:
    """Full two-stage screen. Returns conjunctions under threshold, sorted by miss."""
    sats, names = to_satrecs(records)
    return screen_satrecs(
        sats, names, start,
        hours=hours, threshold_km=threshold_km,
        pad_km=pad_km, coarse_step_s=coarse_step_s,
    )


def screen_satrecs(
    sats: list[Satrec],
    names: list[str],
    start: datetime,
    hours: float = 72.0,
    threshold_km: float = 5.0,
    pad_km: float = 25.0,
    coarse_step_s: float = 60.0,
) -> list[Conjunction]:
    elems = orbit_elements(sats)

    pairs = altitude_band_pairs(elems["apogee"], elems["perigee"], pad_km)
    pairs = node_radius_filter(elems, pairs, pad_km)
    if len(pairs) == 0:
        return []

    # Propagate only objects that appear in surviving pairs — each exactly once.
    used = np.unique(pairs)
    remap = {int(g): k for k, g in enumerate(used)}
    sub = [sats[g] for g in used]
    e, r, v = propagate_many(sub, start, hours, coarse_step_s)
    bad = (e != 0)[:, :, None]
    r = np.where(bad, np.nan, r)
    v = np.where(bad, 0.0, v)
    local = np.array([[remap[int(a)], remap[int(b)]] for a, b in pairs])

    hits = _pair_minima(r, v, local, coarse_step_s, threshold_km)
    step = timedelta(seconds=coarse_step_s)
    results: dict[tuple[int, int, int], Conjunction] = {}
    for pi, ti in hits:
        gi, gj = int(pairs[pi, 0]), int(pairs[pi, 1])
        t_mid = start + ti * step
        tca, miss, rel_speed = _refine_tca(sats[gi], sats[gj], t_mid - step, t_mid + step)
        if miss <= threshold_km:
            key = (gi, gj, int(tca.timestamp() // 300))  # dedupe minima within 5 min
            existing = results.get(key)
            if existing is None or miss < existing.miss_distance_km:
                results[key] = Conjunction(
                    sats[gi].satnum, sats[gj].satnum, names[gi], names[gj],
                    tca, miss, rel_speed,
                )
    return sorted(results.values(), key=lambda c: c.miss_distance_km)
