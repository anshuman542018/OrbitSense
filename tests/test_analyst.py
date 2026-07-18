"""Analyst tests: taxonomy discipline and the no-invented-numbers guarantee."""

from datetime import datetime, timezone

from orbitsense.analyst import (
    TAXONOMY, classify_maneuver, narrate_conjunction, narrate_maneuver,
    template_conjunction_card, template_maneuver_card,
)
from orbitsense.detector import ManeuverEvent
from orbitsense.screener import Conjunction


def mk_maneuver(delta, column="sma_km", z=90.0):
    return ManeuverEvent(
        norad_id=25544, column=column, epoch=datetime(2026, 6, 10, tzinfo=timezone.utc),
        delta=delta, z_score=z, baseline_mad=0.018,
    )


def mk_conj():
    return Conjunction(
        norad_a=25544, norad_b=48274, name_a="ISS (ZARYA)", name_b="STARLINK-1234",
        tca=datetime(2026, 7, 20, 3, 15, tzinfo=timezone.utc),
        miss_distance_km=1.23, relative_speed_km_s=14.1,
    )


def test_classify_maneuver_types():
    assert classify_maneuver(mk_maneuver(1.5)) == "orbit_raise"
    assert classify_maneuver(mk_maneuver(-1.5)) == "orbit_lower"
    assert classify_maneuver(mk_maneuver(0.3)) == "station_keeping"
    assert classify_maneuver(mk_maneuver(-8.0)) == "deorbit_burn"
    assert classify_maneuver(mk_maneuver(0.5, column="inc_deg")) == "plane_change"


def test_template_card_in_taxonomy_and_cites_numbers():
    card = template_maneuver_card(mk_maneuver(1.524), name="ISS (ZARYA)")
    assert card.type in TAXONOMY
    assert card.evidence["delta"] == 1.524
    assert card.evidence["z_score"] == 90.0
    # headline mentions the object and a magnitude
    assert "ISS" in card.headline
    assert "consistent with" in card.explanation


def test_low_confidence_band():
    card = template_maneuver_card(mk_maneuver(0.6, z=6.0), name="OBJECT X")
    assert card.confidence == "low"
    high = template_maneuver_card(mk_maneuver(1.5, z=90.0), name="OBJECT Y")
    assert high.confidence == "high"


def test_conjunction_card_disclaims_probability():
    card = template_conjunction_card(mk_conj())
    assert card.type == "conjunction_notice"
    assert card.evidence["miss_distance_km"] == 1.23
    assert "no collision probability" in card.explanation.lower()


def test_narrate_falls_back_without_provider():
    # provider_spec="none" -> LLMUnavailable -> template card, never crashes
    card = narrate_maneuver(mk_maneuver(1.5), name="ISS (ZARYA)", provider_spec="none")
    assert card.narrator == "template"
    assert card.type in TAXONOMY
    conj = narrate_conjunction(mk_conj(), provider_spec="none")
    assert conj.type == "conjunction_notice"


def test_narrator_never_overrides_numbers():
    # Even if a (hypothetical) model returned garbage numbers, evidence is the
    # template's pipeline evidence. Here we just confirm the evidence dict is
    # exactly the pipeline evidence regardless of narration path.
    ev = mk_maneuver(2.1)
    card = narrate_maneuver(ev, name="TEST", provider_spec="none")
    assert card.evidence["delta"] == 2.1
    assert card.evidence["noise_floor"] == 0.018
