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

See `ARCHITECTURE.md` for the spatial-hash design and its verification against
brute-force propagation.

### Benchmark against CelesTrak SOCRATES Plus

SOCRATES Plus is the reference open conjunction service. OrbitSense screened the
full active catalog (16,063 objects) for a 24 h window and matched results against
the same-window SOCRATES conjunctions (`scripts/benchmark_socrates.py`, matching by
unordered NORAD pair with TCA within 5 minutes).

| Population | Recall vs SOCRATES | Median TCA agreement | Median miss agreement |
|---|---|---|---|
| **Non-Starlink pairs** (1,812 events) | **85.8%** | **0.0 s** | **90 m** (p90 610 m) |
| Starlink-Starlink pairs (763 events) | 22% | 0.3 s | 662 m |

**The non-Starlink number is the real measure of the screener.** When both systems
work from comparably-fresh elements, agreement is excellent: identical TCAs to the
second and sub-100 m miss distances, on a completely independent implementation.

**Why Starlink recall looks low — and why it is not a screener bug.** Starlink
satellites maneuver almost daily. SOCRATES predicts conjunctions up to 7 days out
from the elements it had; OrbitSense used free public TLEs that were a median of
~12 h older. For a satellite that raises its orbit between the two epochs, the
predicted close approach simply does not exist in the newer data — brute-force
1-second propagation on our elements confirms the "missed" pairs are genuinely
tens of km apart, not screener misses. Recall even falls monotonically with the
age of the elements SOCRATES used (26% at 1–2 days stale → 18% at 2–4 days),
exactly the fingerprint of a data-freshness gap rather than a math gap. With
Space-Track supplemental GP (operator ephemerides) this closes; it is documented
honestly rather than hidden.

Performance: full active catalog, 24 h, 5 km threshold → 46,240 conjunctions in
236 s on a laptop.
