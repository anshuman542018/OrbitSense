# Architecture — "The Watchtower"

```
[1] CATALOG    -> daily TLE snapshot (CelesTrak, cached; Space-Track planned)
[2] PROPAGATOR -> vectorized SGP4 (SatrecArray), TEME frame
[3] SCREENER   -> two-stage conjunction detection
[4] DETECTOR   -> element-history changepoints (dSMA, dInc, dEcc)
[5] ANALYST    -> AI classification + plain-English event cards
[6] HERALD     -> dashboard feed + chat + alerts
```

**Design rule: deterministic math produces the facts; AI only classifies,
contextualizes, and narrates.** The analyst never invents an orbital state; every
claim in an event card cites a number the pipeline computed.

## Conjunction screening: spatial hashing in time

Naive all-pairs screening of ~16k objects is 128M pairs. The classic remedy —
geometric pair filters (altitude-band overlap, node-radius test, both implemented
and kept as utilities) — **fails on mega-constellations**: measured on live data,
Starlink alone leaves ~31M of 34M same-shell pairs standing, because satellites at
the same altitude in crossing planes genuinely *can* meet. Pair-oriented screening
is the wrong shape; 31M pairs × 5.7k timesteps is 10¹¹ distance evaluations.

The production screener (`orbitsense/screener.py`) is position-oriented instead:

1. **Propagate everything once** on a coarse grid (15 s), in time chunks that
   bound memory (~1 GB for the full catalog).
2. **Per timestep, build a KD-tree** over all positions — O(n log n) — and query
   pairs within a radius that bounds how far a sub-threshold approach can hide
   between samples (max closing speed × half step ≈ 130 km). Measured: ~6.5k
   standing pairs per step for Starlink, ~20 ms per tree including queries.
3. **Linear relative-motion estimate** per spatial hit: near closest approach
   relative motion is locally straight, so the perpendicular component of
   separation w.r.t. relative velocity predicts the true miss from a single
   sample, and −(Δr·Δv)/|Δv|² predicts the TCA. Only estimates near the
   threshold survive.
4. **Golden-section refinement** on true SGP4 separation to 0.1 s. Fast
   crossings get a tight bracket around the linear TCA; slow drifters (whose
   curvature defeats the linear estimate) get a bucket-wide bracket — their
   relative motion is unimodal on that scale.

**Measured**: 10,784 Starlink objects, 24 h window, 5 km threshold → 22,349
conjunctions in 256 s on a commodity laptop. Full-catalog 72 h screening fits in
~15 min of free CI compute.

**Verification** (in `tests/test_screener.py`): screener output matches 1 s / 0.5 s
brute-force propagation on designed conjunction geometries — slow coplanar drift
approaches (miss within 0.5 km, TCA within 60 s) and fast node crossings that
coarse sampling alone cannot see.

## Element-history ledger

One row per object per TLE epoch: SMA, ecc, inc, RAAN, argp, mean anomaly, mean
motion, B*, apogee/perigee. Monthly-partitioned Parquet
(`data/ledger/YYYY-MM.parquet`), deduped on (norad_id, epoch), queryable directly
with DuckDB. The ledger is both the detector's input and a publishable derived
dataset (~1–2 MB/day compressed for the active catalog).

## TLE accuracy bounds every claim

Public element sets carry km-scale position error that grows with epoch age.
Therefore: screening-level conjunctions only (miss distance, no collision
probability without covariance), maneuver deltas reported with the object's own
noise floor, and conservative language for anomalies (see forthcoming
`ETHICS_AND_SCOPE.md`).

## Cost model

- Compute: one daily GitHub Actions run (free on public repos). Full-catalog
  propagation benchmarks at ~40 s for 16k objects × 72 h @ 60 s on commodity CPU.
- Storage: Parquet in-repo (`data` branch), ~0.5 GB/year.
- AI: free-tier LLM during development; Claude (Haiku routine / Sonnet anomalies,
  Batch API) at launch — narration cost scales with event count, not catalog size.
