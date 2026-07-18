# Roadmap

Status as of the current build. Checked = shipped and validated.

## Phase 0 — Prove the physics ✅
- [x] ISS reboosts recovered from 90 days of public TLEs (two clear step-changes)
- [x] Full-catalog vectorized propagation benchmarked (16k objects × 72h in ~40s)

## Phase 1 — Catalog + ledger ✅
- [x] Daily CelesTrak ingestion → monthly-partitioned Parquet element ledger
- [x] Disk cache respecting CelesTrak's 2h update window
- [x] Daily GitHub Actions pipeline (free CI, commits to the `data` branch)

## Phase 2 — Conjunction screener ✅
- [x] Spatial-hash screening (per-timestep KD-tree) — survives mega-constellations
- [x] Linear miss/TCA estimate + golden-section SGP4 refinement
- [x] Verified against brute-force propagation (tests)
- [x] SOCRATES benchmark: 85.8% recall on non-Starlink pairs, median TCA 0.0s,
      median miss 90m; Starlink gap shown to be TLE staleness, not math

## Phase 3 — Maneuver detector ✅
- [x] Per-object MAD noise floors, dual statistical+physical trigger
- [x] Validated on real ISS reboosts (100% recall, z=87 & z=102)
- [x] EVENT_TAXONOMY.md, DETECTION_METHODS.md

## Phase 4 — Analyst + Herald ✅
- [x] LLM provider abstraction (Gemini free / Claude launch / template fallback)
- [x] Taxonomy-constrained cards; numbers always from the pipeline, never the model
- [x] Docked/formation filter (excludes co-located false positives)
- [x] Next.js dashboard on Vercel: server-rendered feed with evidence tables
- [x] Grounded chat copilot (answers only from screened events)
- [x] Pipeline orchestrator (`orbitsense run`), ETHICS_AND_SCOPE.md

## Phase 5 — Wow + launch (in progress)
- [ ] 3D orbit view (CesiumJS / three.js globe)
- [ ] Weekly auto-generated "State of the Orbits" report
- [ ] Space-Track supplemental GP integration (closes the Starlink freshness gap)
- [ ] Swap narration to Claude (Haiku routine / Sonnet anomalies, Batch API)
- [ ] Run quietly for two weeks; launch post with best real cards + benchmarks

## Definition of "shipped"
A live dashboard narrating real orbital events daily, a validated maneuver detector
(ISS benchmark published), a SOCRATES agreement benchmark, a chat copilot over the
feed, and a launch post. **Stretch:** catch one genuinely notable maneuver before
mainstream coverage.
