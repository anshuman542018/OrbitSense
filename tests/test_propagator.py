from datetime import datetime, timezone

import numpy as np
from sgp4.api import Satrec, jday

from orbitsense.catalog import TleRecord
from orbitsense.propagator import (
    _julian_date, grid_datetimes, propagate_many, propagate_one, to_satrecs,
)

ISS = TleRecord(
    "ISS (ZARYA)",
    "1 25544U 98067A   26198.83085672  .00003846  00000+0  77850-4 0  9996",
    "2 25544  51.6316 148.4431 0006791 307.8623  52.1750 15.49035972576509",
)


def test_julian_date_matches_sgp4_jday():
    dt = datetime(2026, 7, 17, 12, 30, 45, tzinfo=timezone.utc)
    jd, fr = jday(2026, 7, 17, 12, 30, 45)
    assert abs(_julian_date(dt) - (jd + fr)) < 1e-9


def test_propagate_one_altitude_sane():
    sat = Satrec.twoline2rv(ISS.line1, ISS.line2)
    times = grid_datetimes(datetime(2026, 7, 17, tzinfo=timezone.utc), hours=1, step_s=300)
    r, v = propagate_one(sat, times)
    radii = np.linalg.norm(r, axis=1)
    # ISS stays within ~370-470 km altitude
    assert ((radii > 6740) & (radii < 6860)).all()
    speeds = np.linalg.norm(v, axis=1)
    assert ((speeds > 7.5) & (speeds < 7.8)).all()


def test_propagate_many_shapes():
    sats, names = to_satrecs([ISS, ISS])
    e, r, v = propagate_many(sats, datetime(2026, 7, 17, tzinfo=timezone.utc), hours=1, step_s=600)
    assert e.shape == (2, 7)
    assert r.shape == (2, 7, 3)
    assert (e == 0).all()
