"""Screener tests built on synthetic orbits with known geometry.

The ground truth for the end-to-end test is brute-force SGP4 stepping at 1 s
resolution — the screener's smart filters must reproduce it.
"""

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
from sgp4.api import WGS72, Satrec

from orbitsense.catalog import MU_EARTH
from orbitsense.propagator import _julian_date
from orbitsense.screener import (
    altitude_band_pairs, node_radius_filter, orbit_elements, screen_satrecs,
)

EPOCH = datetime(2026, 7, 17, tzinfo=timezone.utc)
EPOCH_1949 = _julian_date(EPOCH) - 2433281.5


def make_sat(satnum, sma_km, ecc=0.0002, inc_deg=51.6, raan_deg=0.0,
             argp_deg=0.0, ma_deg=0.0):
    no_kozai = np.sqrt(MU_EARTH / sma_km**3) * 60.0  # rad/min
    sat = Satrec()
    sat.sgp4init(
        WGS72, "i", satnum, EPOCH_1949, 1e-5, 0.0, 0.0,
        ecc, np.radians(argp_deg), np.radians(inc_deg), np.radians(ma_deg),
        no_kozai, np.radians(raan_deg),
    )
    return sat


def brute_force_min(sat_a, sat_b, start, hours, step_s=1.0):
    n = int(hours * 3600 / step_s) + 1
    jd0 = _julian_date(start)
    jd = np.full(n, np.floor(jd0) + 0.5)
    fr = (jd0 - jd[0]) + np.arange(n) * (step_s / 86400.0)
    ea, ra, _ = sat_a.sgp4_array(jd, fr)
    eb, rb, _ = sat_b.sgp4_array(jd, fr)
    d = np.linalg.norm(ra - rb, axis=1)
    d[(ea != 0) | (eb != 0)] = np.inf
    k = int(np.argmin(d))
    return start + timedelta(seconds=k * step_s), float(d[k])


def test_altitude_band_filter_separates_leo_geo():
    leo = make_sat(1, 6795.0)
    geo = make_sat(2, 42164.0, inc_deg=0.1)
    elems = orbit_elements([leo, geo])
    pairs = altitude_band_pairs(elems["apogee"], elems["perigee"], pad_km=25)
    assert len(pairs) == 0


def test_altitude_band_filter_keeps_overlapping_shells():
    a = make_sat(1, 6795.0)
    b = make_sat(2, 6800.0, inc_deg=97.5, raan_deg=120.0)
    elems = orbit_elements([a, b])
    pairs = altitude_band_pairs(elems["apogee"], elems["perigee"], pad_km=25)
    assert pairs.tolist() == [[0, 1]]


def test_node_radius_filter_drops_separated_crossing_orbits():
    # Same plane-crossing geometry, but radii differ by 300 km everywhere.
    a = make_sat(1, 6878.0)   # ~500 km circular
    b = make_sat(2, 7178.0, inc_deg=97.5, raan_deg=45.0)  # ~800 km circular
    elems = orbit_elements([a, b])
    pairs = np.array([[0, 1]])
    kept = node_radius_filter(elems, pairs, pad_km=25)
    assert len(kept) == 0


def test_node_radius_filter_keeps_matching_radii():
    a = make_sat(1, 6878.0)
    b = make_sat(2, 6879.0, inc_deg=97.5, raan_deg=45.0)
    elems = orbit_elements([a, b])
    kept = node_radius_filter(elems, np.array([[0, 1]]), pad_km=25)
    assert len(kept) == 1


def test_screen_matches_brute_force():
    # Near-coplanar pair a few km apart along-track: a guaranteed close,
    # slow conjunction whose geometry brute force can pin down exactly.
    a = make_sat(1, 6795.0, ma_deg=0.0)
    b = make_sat(2, 6795.5, inc_deg=51.7, ma_deg=0.08)
    results = screen_satrecs([a, b], ["A", "B"], EPOCH, hours=24,
                             threshold_km=30.0)
    assert results, "screener found nothing for a designed close pair"
    best = results[0]

    tca_bf, miss_bf = brute_force_min(a, b, EPOCH, hours=24)
    assert best.miss_distance_km == pytest.approx(miss_bf, abs=0.5)
    assert abs((best.tca - tca_bf).total_seconds()) <= 60


def test_screen_fast_crossing_geometry_found():
    # Two circular orbits at the same altitude in different planes: a
    # head-on-style node crossing at ~10+ km/s. The coarse grid alone
    # cannot see it; the gate + refinement must still catch it.
    a = make_sat(1, 6878.0, inc_deg=51.6, ma_deg=0.0)
    b = make_sat(2, 6878.0, inc_deg=97.5, raan_deg=60.0, ma_deg=17.0)
    tca_bf, miss_bf = brute_force_min(a, b, EPOCH, hours=24, step_s=0.5)
    results = screen_satrecs([a, b], ["A", "B"], EPOCH, hours=24,
                             threshold_km=max(30.0, miss_bf + 5))
    assert results, f"missed crossing conjunction (brute force: {miss_bf:.1f} km)"
    best = min(results, key=lambda c: abs((c.tca - tca_bf).total_seconds()))
    assert abs((best.tca - tca_bf).total_seconds()) <= 60
    assert best.miss_distance_km <= miss_bf + 5
