# OrbitSense

**A copilot for everything happening in Earth orbit.**

### 🛰️ Live dashboard → **[orbitsense.vercel.app](https://orbitsense.vercel.app)**

Every day, OrbitSense pulls the public catalog of tracked space objects, propagates their
orbits, screens for close approaches, and detects maneuvers. An AI analyst then explains
each event in plain language, with the numbers to back it up.

> "Starlink-4521 raised its orbit 2 km yesterday, consistent with routine station-keeping."

The live site has three views: a plain-language **event feed**, an interactive **3D orbit
globe** of the day's close approaches, and a **chat copilot** grounded in the screened data.

## What works today

- **Physics proven**: ISS reboosts are clearly visible in 90 days of public TLE history —
  recovered entirely from free data.
- **Full-catalog propagation**: ~16k objects × 72 h propagated in ~40 s on a laptop —
  the whole pipeline fits on free CI compute.
- **Conjunction screener**: per-timestep KD-tree spatial hashing that survives
  mega-constellations (10k Starlink objects screened in ~256 s). Benchmarked against
  CelesTrak SOCRATES: **85.8% recall on non-Starlink pairs, closest-approach times
  matching to the second, miss distances to ~90 m.**
- **Maneuver detector**: per-object noise floors + changepoint detection —
  **100% recall on real ISS reboosts** (z-scores of 87 and 102 against a 5σ threshold).
- **Element ledger**: daily TLE ingestion into a monthly-partitioned Parquet time-series,
  the foundation for maneuver detection.
- **Live pipeline**: a daily GitHub Action fetches the catalog, screens 72 h ahead,
  detects maneuvers, regenerates the cards + globe, and publishes to the `data` branch —
  the dashboard reads it automatically, no server required.

## Quick start

```bash
pip install -e .
orbitsense run --group active --hours 72   # full pipeline: ingest → screen → detect → narrate → feed
```

## Email alerts (optional)

The daily pipeline can email you when a conjunction breaches a tight critical
threshold. It flags only genuine high-energy near-misses — co-located assemblies
and near-zero-closing-speed formation neighbours are filtered out — and the email
is capped to the tightest few with a total count. Alerts go **only** to the
addresses you configure; the tool never notifies third parties.

Enable it by setting these on the repo (Settings → Secrets and variables → Actions):

| Secret | Purpose |
|---|---|
| `ORBITSENSE_ALERT_TO` | Comma-separated recipient address(es). Required to send. |
| `ORBITSENSE_SMTP_USER` | Sending mailbox (e.g. a Gmail address). |
| `ORBITSENSE_SMTP_PASS` | SMTP password / [Gmail app password](https://support.google.com/accounts/answer/185833). |

Optional variables: `ORBITSENSE_ALERT_KM` (critical miss threshold, default `1.0`),
`ORBITSENSE_SMTP_HOST` (default `smtp.gmail.com`), `ORBITSENSE_SMTP_PORT` (default `587`).

> These are **screening-level** notices from public elements — not
> collision-probability warnings and not an operational safety service.

## Architecture — "The Watchtower"

```
[1] CATALOG    -> daily TLE snapshot (CelesTrak / Space-Track)
[2] PROPAGATOR -> vectorized SGP4 propagation, 72h lookahead
[3] SCREENER   -> KD-tree spatial-hash conjunction detection
[4] DETECTOR   -> maneuver detection via element-history changepoints
[5] ANALYST    -> AI classification + plain-English event cards
[6] HERALD     -> dashboard feed + 3D globe + chat
```

**Deterministic math produces the facts; the AI only classifies, contextualizes, and
narrates** — grounded in numbers the pipeline computed. It never invents orbital states,
and every event card cites the numbers that triggered it.

## Scope & honesty

Built entirely on public data. **Not an operational safety service.** Conjunctions are
screening-level estimates from public elements — no collision probabilities are claimed
(that requires covariance data the public catalog does not have). Maneuvers are described
conservatively ("consistent with", never "is"), and anomalies are held to a validated
detection standard before they are ever surfaced. The fastest way to lose credibility in
space situational awareness is to overclaim — so OrbitSense doesn't.

## Tech

Python (sgp4, skyfield, numpy, scipy, ruptures, DuckDB/Parquet) for the pipeline;
Next.js + three.js on Vercel for the dashboard; GitHub Actions for the free daily compute.
