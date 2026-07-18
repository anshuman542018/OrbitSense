# Ethics and Scope

OrbitSense exists to make public space-object behavior legible to non-experts.
That is only valuable if it is trustworthy. These are hard rules, not aspirations.

## What OrbitSense does

- Analyzes **only public catalog data** (CelesTrak, Space-Track, and open mirrors).
- Reports **screening-level** conjunctions: predicted miss distances from public
  elements. It does **not** claim collision probabilities, which require covariance
  data the public catalog does not contain.
- Describes maneuvers **conservatively**: "consistent with a station-keeping burn,"
  never "performed a station-keeping burn." Every claim cites the number that
  triggered it (ΔSMA, z-score, the object's own noise floor).
- Publishes **derived events**, honoring Space-Track's redistribution terms — never
  bulk raw element sets.

## What OrbitSense does not do

- **No operational safety claims.** It is not a collision-avoidance service and must
  not be used as one.
- **No intent attribution.** It describes behavior and cites numbers. It never
  speculates about military purpose, ownership motives, or geopolitical meaning.
- **No hype.** A single overclaimed anomaly destroys more credibility than a hundred
  careful cards earn. The taxonomy (`EVENT_TAXONOMY.md`) is the guardrail: events
  with 5 ≤ |z| < 8 are labeled low-confidence; the `anomalous_approach` type is not
  published while detector recall on the ISS benchmark is below 90%.

## Newsworthy findings

When the pipeline surfaces something genuinely notable (an unusual proximity pattern,
an unexpected maneuver), it is described **factually, with full evidence, and with the
limitations stated**. The goal is that an expert reading the card respects both the
finding and the restraint. Screening-level, public-data caveats are features, not
disclaimers to bury.

## Why this file exists

The fastest way to lose standing in space situational awareness is to overclaim.
Rigor about what public data can and cannot support is the entire credibility of the
project. This document is the contract the analyst and the maintainer both sign.
