"""Detector tests on synthetic element histories with known injected burns."""

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from orbitsense.detector import detect_steps, scan_ledger

RNG = np.random.default_rng(42)
START = datetime(2026, 4, 1, tzinfo=timezone.utc)


def synthetic_sma(days=90, decay_km_day=-0.03, noise_km=0.01, burns=()):
    """Daily SMA series: linear drag decay + noise + step burns at given days."""
    epochs = [START + timedelta(days=i) for i in range(days)]
    sma = 6795.0 + decay_km_day * np.arange(days) + RNG.normal(0, noise_km, days)
    for day, dv_km in burns:
        sma[day:] += dv_km
    return pd.DataFrame({"epoch": epochs, "sma_km": sma})


def test_quiet_series_no_false_positives():
    df = synthetic_sma()
    events = detect_steps(df, norad_id=1)
    assert events == []


def test_single_reboost_detected():
    df = synthetic_sma(burns=[(45, 1.5)])
    events = detect_steps(df, norad_id=25544)
    assert len(events) == 1
    ev = events[0]
    assert abs((ev.epoch - (START + timedelta(days=45))).days) <= 1
    assert 1.2 < ev.delta < 1.8
    assert ev.z_score > 5


def test_multiple_burns_and_direction():
    df = synthetic_sma(burns=[(30, 1.5), (70, -0.8)])
    events = detect_steps(df, norad_id=1)
    assert len(events) == 2
    assert events[0].delta > 0 and events[1].delta < 0


def test_small_burn_below_floor_ignored():
    # 20 m step is under the 50 m physical floor: must stay quiet even if
    # statistically visible.
    df = synthetic_sma(noise_km=0.002, burns=[(45, 0.02)])
    events = detect_steps(df, norad_id=1)
    assert events == []


def test_burn_split_across_two_epochs_merges():
    df = synthetic_sma(burns=[(45, 0.7), (46, 0.7)])
    events = detect_steps(df, norad_id=1)
    assert len(events) == 1
    assert 1.1 < events[0].delta < 1.7


def test_scan_ledger_multiple_objects():
    quiet = synthetic_sma()
    quiet["norad_id"] = 100
    active = synthetic_sma(burns=[(50, 2.0)])
    active["norad_id"] = 200
    ledger = pd.concat([quiet, active], ignore_index=True)
    events = scan_ledger(ledger)
    assert [e.norad_id for e in events] == [200]
