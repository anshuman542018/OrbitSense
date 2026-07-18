# Data Sources

## CelesTrak GP data (primary, no auth)

- `https://celestrak.org/NORAD/elements/gp.php?GROUP=<group>&FORMAT=tle`
- Groups used: `active` (~16k objects) daily; smaller groups for tests.
- **Rate rules**: GP data updates roughly every 2 hours; CelesTrak returns 403 to
  clients that re-download the same query inside that window. OrbitSense fetches each
  group at most once per pipeline run, once per day, with an identifying User-Agent.
- Attribution: data courtesy of CelesTrak (T.S. Kelso).

## Space-Track (planned, free account required)

- Historical element sets for backfill and detector calibration.
- **Redistribution rules matter**: the Space-Track user agreement restricts bulk
  redistribution of raw element sets. OrbitSense publishes *derived* products
  (events, per-object element time series it computed, plots) — never bulk raw TLE dumps.
- Rate limits: respect the documented API throttles (batched, off-peak queries).

## BI4PYM/AutoTLE git history (bootstrap only)

- An open GitHub repository that snapshots amateur-satellite TLEs (including the ISS)
  several times daily. Its git history provided the 90-day ISS semi-major-axis series
  used for the Phase 0 proof and detector calibration, without an account.
- Upstream source is CelesTrak; same attribution applies.

## navsuite/celestrak-orbital-data (fallback mirror)

- Open GitHub repo archiving daily per-constellation TLE snapshots from CelesTrak
  (Starlink, OneWeb, Kuiper, Iridium, ...), organized `constellation/YYYY/DDD/`.
- Used as a fallback when a CelesTrak group is inside its 2h block window, and as
  a free source of constellation history. Upstream attribution: CelesTrak.

## UCS Satellite Database (planned)

- Owner, operator, mission metadata for narrative context in event cards.
- Free CSV; attribution to the Union of Concerned Scientists.

## What OrbitSense claims — and does not

TLEs carry km-scale position error that grows with epoch age. OrbitSense therefore
reports **screening-level** conjunctions (miss distances from public elements), not
collision probabilities, which require covariance data the public catalog does not have.
