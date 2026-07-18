# Detection Methods

## Maneuver detection

Maneuvers are step changes in mean orbital elements on top of smooth secular
drift and TLE noise. The production detector (`orbitsense/detector.py`) works on
first differences of each object's element history:

1. **Per-object noise floor**: median + MAD of epoch-to-epoch differences over the
   object's own history. Every object is judged against its own baseline (a GEO bird's
   floor is millimeters of SMA; a tumbling cubesat's is tens of meters).
2. **Dual trigger**: a step must be both a statistical outlier
   (|z| ≥ 5 on the MAD scale) **and** physically meaningful (|ΔSMA| ≥ 50 m).
3. **Merge window**: flags within 36 h collapse into one event, so a burn spread
   across consecutive daily element sets reports once.

`ruptures` (PELT) segmentation is kept as a calibration cross-check
(`segment_series`); the MAD detector is production because it is O(n), robust to
uneven epoch spacing, and its thresholds have physical units.

## Validation: ISS reboosts (public ground truth)

ISS reboosts are regular, published, and unmistakable in element history — the
calibration standard for this detector.

**90-day window (2026-04-19 → 2026-07-17, 83 daily element points from public TLEs):**

| Detected epoch | ΔSMA | z-score | Assessment |
|---|---|---|---|
| 2026-06-10 09:59 | +1524 m | 86.8 | Reboost — matches visible step in SMA series |
| 2026-07-04 11:25 | +1794 m | 101.8 | Reboost — matches visible step in SMA series |
| 2026-05-24 04:43 | −139 m | −5.2 | Borderline: small deboost/DAM or density spike |

- **Recall on visually confirmed reboosts: 2/2 (100%)**, both at z > 85 —
  vastly above threshold. Noise floor for ISS: 18 m of SMA.
- The −139 m event sits just above threshold (z = 5.2). It is reported here for
  honesty: negative single-epoch steps can also be produced by atmospheric density
  spikes changing the decay rate, which violates the locally-constant-drift
  assumption. Production narration labels events in the 5 ≤ |z| < 8 band as
  *low-confidence* and never calls them maneuvers outright.
- Reproduce with `python scripts/validate_iss_detector.py`.

**Public-anomaly gate (per blueprint): no anomaly claim ships until the detector
shows >90% recall on ISS reboosts.** Current: 100% on this window; the window
extends automatically as the ledger accumulates history.

## Conjunction screening

See `ARCHITECTURE.md` for the two-stage design and its verification against
brute-force propagation.
