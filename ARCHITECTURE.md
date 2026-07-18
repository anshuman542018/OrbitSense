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

## Two-stage conjunction screening

Naive all-pairs screening of ~16k objects is 128M pairs — infeasible at fine time
steps. The screener (`orbitsense/screener.py`) uses the classic smart-filter design:

### Stage 1 — pure geometry, no propagation

a) **Altitude-band filter.** A pair can only meet if the radial shells
   `[perigee − pad, apogee + pad]` overlap. Implemented as a sweep over
   perigee-sorted intervals (O(n log n + k), no n² matrix).

b) **Node-radius filter.** Orbits in different planes can only come close near
   their mutual line of nodes (`ĥ₁ × ĥ₂`). Each orbit's radius along ± that
   direction comes from its ellipse (r = p / (1 + e·cos ν), ν from the perifocal
   projection of the node vector). Survive only if radii agree within the pad
   somewhere on the node line. Near-coplanar pairs (< 3° relative inclination)
   skip this test — they can approach anywhere along the orbit.

### Stage 2 — propagate once, gate dynamically, refine precisely

- Every object that survives stage 1 is propagated **once** on a coarse grid
  (60 s), never per pair.
- Per-pair distance series are scanned for local minima. A minimum is kept only if
  its coarse distance could hide a sub-threshold approach given the pair's **actual
  closing speed at that sample** (relspeed × step/2 × 1.25 + threshold). This
  velocity-aware gate is what keeps dense constellations tractable: coplanar
  Starlink neighbors close at mm/s–m/s and get a few-km gate, while genuine
  ~14 km/s plane crossings keep the wide gate they need. A worst-case constant
  gate (~460 km in LEO) drowns stage 2 in same-shell false candidates.
- Each surviving candidate is refined by golden-section search on the true SGP4
  separation down to 0.1 s, yielding TCA, miss distance, and relative speed.

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
