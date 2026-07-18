# Event Taxonomy — the Analyst's Constitution

The ANALYST (AI narration layer) may only classify events into this controlled
vocabulary, may only use the listed narrative stances, and must cite the listed
evidence fields for every claim. This file exists to prevent hype drift: one
overclaimed anomaly costs more credibility than a hundred good cards earn.

## Language rules (all types)

- Quantify everything: "ΔSMA = +1.5 km (z = 87 vs 18 m noise floor)".
- Interpretations use "consistent with", never "is" / "confirms".
- No speculation about intent, military or otherwise. Describe behavior, cite
  numbers, stop.
- Events with 5 ≤ |z| < 8 are labeled **low-confidence** and use hedged phrasing.
- TLE limitations named when relevant ("screening-level; public elements carry
  km-scale uncertainty").

## Types

### conjunction_notice
- **Trigger**: predicted miss distance < 5 km within the 72 h screening window.
- **Evidence**: TCA (UTC), miss distance (km), relative speed (km/s), both object
  names + NORAD IDs + owners.
- **Template**: "{A} and {B} are predicted to pass within {miss} km at {tca}
  ({relspeed} km/s relative). Screening-level estimate from public elements —
  no collision probability is claimed."

### station_keeping
- **Trigger**: ΔSMA step within the object's historical maneuver envelope,
  restoring altitude lost to drag (LEO) or maintaining slot (GEO).
- **Evidence**: ΔSMA, z-score, days since previous maneuver, object baseline.
- **Template**: "{A} raised its orbit {delta} km on {date}, consistent with
  routine station-keeping ({n}th such maneuver this year)."

### orbit_raise / orbit_lower
- **Trigger**: sustained SMA trend across ≥ 3 epochs beyond drag modeling, or a
  single step much larger than the station-keeping envelope.
- **Evidence**: total ΔSMA, duration, start/end altitudes.

### plane_change
- **Trigger**: Δinclination step ≥ detector threshold (expensive, hence rare and
  notable).
- **Evidence**: Δinc (deg), z-score, ΔV estimate order-of-magnitude.

### phasing_maneuver
- **Trigger**: SMA step followed by opposite step within days (drift-and-stop
  signature).
- **Evidence**: both steps, resulting along-track drift rate.

### deorbit_burn / decay_reentry_watch
- **Trigger**: large negative ΔSMA taking perigee below ~200 km, or B*/decay-rate
  runaway on an object with falling perigee.
- **Evidence**: perigee history, estimated decay window (wide, honest bounds).

### anomalous_approach
- **Trigger**: repeated conjunctions (≥ 2 in 30 days) between the same pair where
  one object maneuvered between passes. The interesting one — and therefore the
  most conservatively worded.
- **Evidence**: full pass history table, the maneuver events between passes,
  both objects' catalog identities.
- **Template**: "{A} has passed within {d} km of {B} {n} times since {date},
  with {A} maneuvering between approaches. The pattern is consistent with an
  intentional proximity operation; public data cannot establish intent."
- **Gate**: never published while detector recall on the ISS benchmark is
  below 90% (see DETECTION_METHODS.md).

## Required card structure

1. One-sentence headline (type + object + magnitude).
2. Three-sentence explanation (what happened, how it compares to this object's
   history, what it is consistent with).
3. Evidence table (every number the pipeline computed).
4. Confidence: high / low-confidence per the z-band rule.
