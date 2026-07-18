from datetime import datetime, timezone

import pandas as pd

from orbitsense.catalog import (
    TleRecord, append_to_ledger, elements_row, parse_3le, records_to_frame,
)

ISS_TLE = TleRecord(
    "ISS (ZARYA)",
    "1 25544U 98067A   26198.83085672  .00003846  00000+0  77850-4 0  9996",
    "2 25544  51.6316 148.4431 0006791 307.8623  52.1750 15.49035972576509",
)


def test_parse_3le():
    text = "\n".join([ISS_TLE.name, ISS_TLE.line1, ISS_TLE.line2])
    records = parse_3le(text)
    assert len(records) == 1
    assert records[0].name == "ISS (ZARYA)"


def test_elements_row_iss():
    row = elements_row(ISS_TLE)
    assert row is not None
    assert row["norad_id"] == 25544
    # ISS orbits at ~420 km altitude -> SMA ~6795 km
    assert 6770 < row["sma_km"] < 6820
    assert 51.5 < row["inc_deg"] < 51.7
    assert row["epoch"].year == 2026
    assert 350 < row["perigee_km"] < row["apogee_km"] < 500


def test_ledger_roundtrip(tmp_path):
    frame = records_to_frame([ISS_TLE])
    written = append_to_ledger(frame, tmp_path)
    assert len(written) == 1
    # Re-appending the same rows must not duplicate
    append_to_ledger(frame, tmp_path)
    stored = pd.read_parquet(written[0])
    assert len(stored) == 1
    assert stored.iloc[0]["norad_id"] == 25544


def test_ledger_monthly_partitions(tmp_path):
    frame = records_to_frame([ISS_TLE])
    other = frame.copy()
    other["epoch"] = datetime(2026, 1, 15, tzinfo=timezone.utc)
    written = append_to_ledger(pd.concat([frame, other]), tmp_path)
    assert len(written) == 2
