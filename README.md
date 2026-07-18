# OrbitSense

**A copilot for everything happening in Earth orbit.**

Every day, OrbitSense pulls the public catalog of tracked space objects, propagates their
orbits, screens for close approaches, and detects maneuvers. An AI analyst then explains
each event in plain language, with the numbers to back it up.

> "Starlink-4521 raised its orbit 2 km yesterday, consistent with routine station-keeping."

## Status

Early build. What works today:

- **Physics proven**: ISS reboosts are clearly visible in 90 days of public TLE history
  (see `scripts/phase0_iss_history.py` — the two upward steps in the plot are real
  reboost burns, recovered entirely from free data).
- **Full-catalog propagation benchmarked**: ~16k objects × 72 h at 60 s steps in ~40 s
  on a laptop (~1.7M position evaluations/s) — the whole pipeline fits on free CI compute.
- **Element ledger**: daily TLE ingestion into a monthly-partitioned Parquet time-series
  (`orbitsense ingest`), the foundation for maneuver detection.

## Quick start

```bash
pip install -e .
orbitsense ingest --group active
```

## Architecture — "The Watchtower"

```
[1] CATALOG    -> daily TLE snapshot (CelesTrak / Space-Track)
[2] PROPAGATOR -> SGP4 propagation, 72h lookahead
[3] SCREENER   -> two-stage conjunction detection
[4] DETECTOR   -> maneuver detection via element-history changepoints
[5] ANALYST    -> AI classification + plain-English event cards
[6] HERALD     -> dashboard feed + chat + alerts
```

Deterministic math produces the facts; the AI's job is classification, context, and
narrative — grounded in numbers the pipeline computed. It never invents orbital states.

Built on public data. **Not an operational safety service** — see `ETHICS_AND_SCOPE.md`
(coming with the analyst phase).

## Docs

- `DATA_SOURCES.md` — where the data comes from and the rules for using it
- `ARCHITECTURE.md`, `DETECTION_METHODS.md`, `EVENT_TAXONOMY.md` — land with Phases 2–4
