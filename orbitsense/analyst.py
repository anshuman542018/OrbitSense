"""The ANALYST: turns pipeline events into taxonomy-constrained event cards.

Hard rule (see EVENT_TAXONOMY.md): the AI classifies and narrates; it never
invents numbers. Every card is built from pipeline-computed evidence, the
`type` is validated against the controlled vocabulary, and the numeric fields
in the card are copied from the evidence — not from the model. If the model is
unavailable or returns anything off-spec, a deterministic template card is
emitted instead, so the pipeline always produces valid output.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from .detector import ManeuverEvent
from .llm import LLMUnavailable, get_provider
from .screener import Conjunction

TAXONOMY = {
    "conjunction_notice", "station_keeping", "orbit_raise", "orbit_lower",
    "plane_change", "phasing_maneuver", "deorbit_burn", "decay_reentry_watch",
    "anomalous_approach",
}

SYSTEM_PROMPT = """You are the ANALYST for OrbitSense, a space situational \
awareness tool. You explain orbital events in plain language for a general \
audience (journalists, students). You are given pipeline-computed EVIDENCE and \
must return a JSON object with exactly these fields:

  "type": one of {taxonomy}
  "headline": one sentence, <= 120 chars, naming the object and the magnitude
  "explanation": exactly three sentences: what happened, how it compares to \
this object's own history, and what it is consistent with
  "confidence": "high" or "low"

RULES:
- Use ONLY numbers present in the EVIDENCE. Never invent or estimate values.
- Interpretations use "consistent with", never "is" or "confirms".
- No speculation about intent (military or otherwise). Describe behavior.
- If z-score is between 5 and 8, confidence is "low" and language is hedged.
- Return ONLY the JSON object.""".replace("{taxonomy}", ", ".join(sorted(TAXONOMY)))


@dataclass
class EventCard:
    type: str
    headline: str
    explanation: str
    confidence: str
    evidence: dict[str, Any]
    object_ids: list[int]
    tca_or_epoch: str
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    narrator: str = "template"


# ---------------------------------------------------------------- classification

def classify_maneuver(ev: ManeuverEvent, station_keeping_envelope_km: float = 0.6) -> str:
    if ev.column == "inc_deg":
        return "plane_change"
    if ev.column == "sma_km":
        if ev.delta < 0 and abs(ev.delta) > 5.0:
            return "deorbit_burn"
        if abs(ev.delta) <= station_keeping_envelope_km:
            return "station_keeping"
        return "orbit_raise" if ev.delta > 0 else "orbit_lower"
    return "station_keeping"


def maneuver_evidence(ev: ManeuverEvent) -> dict[str, Any]:
    unit = "km" if ev.column == "sma_km" else "deg"
    return {
        "norad_id": ev.norad_id,
        "element": ev.column,
        "delta": round(ev.delta, 4),
        "delta_unit": unit,
        "z_score": round(ev.z_score, 1),
        "noise_floor": round(ev.baseline_mad, 4),
        "epoch": ev.epoch.isoformat(),
    }


def conjunction_evidence(c: Conjunction) -> dict[str, Any]:
    return {
        "object_a": {"norad_id": c.norad_a, "name": c.name_a},
        "object_b": {"norad_id": c.norad_b, "name": c.name_b},
        "tca": c.tca.isoformat(),
        "miss_distance_km": round(c.miss_distance_km, 3),
        "relative_speed_km_s": round(c.relative_speed_km_s, 2),
    }


# ---------------------------------------------------------------- template fallback

def template_maneuver_card(ev: ManeuverEvent, name: str | None = None) -> EventCard:
    etype = classify_maneuver(ev)
    obj = name or f"NORAD {ev.norad_id}"
    conf = "low" if abs(ev.z_score) < 8 else "high"
    if ev.column == "sma_km":
        mag = f"{ev.delta * 1000:+.0f} m"
        verb = {"orbit_raise": "raised its orbit", "orbit_lower": "lowered its orbit",
                "station_keeping": "adjusted its orbit", "deorbit_burn": "sharply lowered its orbit"}.get(etype, "changed its orbit")
        headline = f"{obj} {verb} by {abs(ev.delta):.2f} km"
        hedge = "possibly " if conf == "low" else ""
        explanation = (
            f"On {ev.epoch:%Y-%m-%d} the semi-major axis of {obj} changed by "
            f"{mag} (z = {ev.z_score:.0f} against a {ev.baseline_mad*1000:.0f} m "
            f"noise floor). "
            f"That is {abs(ev.z_score):.0f} times this object's typical epoch-to-epoch "
            f"variation. "
            f"The step is {hedge}consistent with a {etype.replace('_', ' ')}."
        )
    else:
        headline = f"{obj} changed inclination by {abs(ev.delta):.3f} deg"
        explanation = (
            f"On {ev.epoch:%Y-%m-%d} the inclination of {obj} changed by "
            f"{ev.delta:+.3f} deg (z = {ev.z_score:.0f}). "
            f"Plane changes are energetically expensive and rare for most objects. "
            f"The step is consistent with a deliberate plane_change maneuver."
        )
    return EventCard(
        type=etype, headline=headline[:120], explanation=explanation,
        confidence=conf, evidence=maneuver_evidence(ev),
        object_ids=[ev.norad_id], tca_or_epoch=ev.epoch.isoformat(),
    )


def template_conjunction_card(c: Conjunction) -> EventCard:
    headline = f"{c.name_a} and {c.name_b} predicted to pass within {c.miss_distance_km:.2f} km"
    explanation = (
        f"{c.name_a} and {c.name_b} are predicted to pass within "
        f"{c.miss_distance_km:.2f} km at {c.tca:%Y-%m-%d %H:%M} UTC, closing at "
        f"{c.relative_speed_km_s:.1f} km/s. "
        f"This is a screening-level estimate from public elements. "
        f"No collision probability is claimed; public data carries km-scale uncertainty."
    )
    return EventCard(
        type="conjunction_notice", headline=headline[:120], explanation=explanation,
        confidence="high", evidence=conjunction_evidence(c),
        object_ids=[c.norad_a, c.norad_b], tca_or_epoch=c.tca.isoformat(),
    )


# ---------------------------------------------------------------- LLM narration

def _narrate(evidence: dict, fallback: EventCard, provider_spec: str | None) -> EventCard:
    try:
        provider = get_provider(provider_spec)
        result = provider.complete_json(
            SYSTEM_PROMPT, "EVIDENCE:\n" + _json(evidence),
        )
    except (LLMUnavailable, Exception):
        return fallback

    # Validate: type must be in-taxonomy; otherwise keep the template card but
    # accept the model's prose only if the type checks out.
    if result.get("type") not in TAXONOMY:
        return fallback
    headline = str(result.get("headline", "")).strip()
    explanation = str(result.get("explanation", "")).strip()
    if not headline or not explanation:
        return fallback
    return EventCard(
        type=result["type"],
        headline=headline[:120],
        explanation=explanation,
        confidence="low" if result.get("confidence") == "low" else fallback.confidence,
        evidence=fallback.evidence,          # numbers ALWAYS from the pipeline
        object_ids=fallback.object_ids,
        tca_or_epoch=fallback.tca_or_epoch,
        narrator=(provider_spec or "llm"),
    )


def narrate_maneuver(ev: ManeuverEvent, name: str | None = None,
                     provider_spec: str | None = None) -> EventCard:
    fallback = template_maneuver_card(ev, name)
    ev_dict = dict(fallback.evidence)
    ev_dict["object_name"] = name or f"NORAD {ev.norad_id}"
    ev_dict["suggested_type"] = fallback.type
    return _narrate(ev_dict, fallback, provider_spec)


def narrate_conjunction(c: Conjunction, provider_spec: str | None = None) -> EventCard:
    fallback = template_conjunction_card(c)
    return _narrate(fallback.evidence, fallback, provider_spec)


def _json(obj: Any) -> str:
    import json
    return json.dumps(obj, indent=2, default=str)


def card_to_dict(card: EventCard) -> dict:
    return asdict(card)
