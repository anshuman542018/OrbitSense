"""Alert tests: thresholding, email building, and safe send-failure handling."""

from datetime import datetime, timezone

from orbitsense.alerts import (
    AlertConfig, build_email, critical_conjunctions, maybe_alert,
)
from orbitsense.screener import Conjunction


def conj(a, b, miss, relv=10.0):
    return Conjunction(
        norad_a=a, norad_b=b, name_a=f"SAT-{a}", name_b=f"SAT-{b}",
        tca=datetime(2026, 7, 20, 3, 15, tzinfo=timezone.utc),
        miss_distance_km=miss, relative_speed_km_s=relv,
    )


def test_critical_filter_threshold():
    conjs = [conj(1, 2, 0.3), conj(3, 4, 0.8), conj(5, 6, 2.5)]
    crit = critical_conjunctions(conjs, threshold_km=1.0)
    assert [c.miss_distance_km for c in crit] == [0.3, 0.8]  # sorted, <=1km only


def test_critical_filter_excludes_docked():
    # co-located pair: tiny miss AND ~0 relative speed -> not a real approach
    docked = conj(1, 2, 0.02, relv=0.01)
    real = conj(3, 4, 0.5, relv=12.0)
    crit = critical_conjunctions([docked, real], threshold_km=1.0)
    assert len(crit) == 1
    assert crit[0].norad_a == 3


def test_build_email_contains_evidence_and_disclaimer():
    subject, text, html = build_email([conj(1, 2, 0.42, 13.1)], threshold_km=1.0)
    assert "under 1 km" in subject
    assert "0.420 km" in text
    assert "NOT a collision-probability warning" in text
    assert "NOT a collision-probability warning" in html
    assert "orbitsense.vercel.app" in text


def test_config_from_env_requires_recipient(monkeypatch):
    monkeypatch.delenv("ORBITSENSE_ALERT_TO", raising=False)
    assert AlertConfig.from_env() is None
    monkeypatch.setenv("ORBITSENSE_ALERT_TO", "me@example.com, you@example.com")
    cfg = AlertConfig.from_env()
    assert cfg is not None
    assert cfg.to == ["me@example.com", "you@example.com"]


def test_maybe_alert_unconfigured_is_noop(monkeypatch):
    monkeypatch.delenv("ORBITSENSE_ALERT_TO", raising=False)
    result = maybe_alert([conj(1, 2, 0.1)])
    assert result == {"configured": False, "sent": 0}


def test_maybe_alert_no_critical_events(monkeypatch):
    monkeypatch.setenv("ORBITSENSE_ALERT_TO", "me@example.com")
    result = maybe_alert([conj(1, 2, 3.0)])  # 3km > 1km default threshold
    assert result == {"configured": True, "critical": 0, "sent": 0}


def test_maybe_alert_send_failure_does_not_raise(monkeypatch):
    # Configured with an unroutable SMTP host: must capture the error, not crash.
    monkeypatch.setenv("ORBITSENSE_ALERT_TO", "me@example.com")
    monkeypatch.setenv("ORBITSENSE_SMTP_HOST", "127.0.0.1")
    monkeypatch.setenv("ORBITSENSE_SMTP_PORT", "1")  # nothing listening
    result = maybe_alert([conj(1, 2, 0.3)])
    assert result["configured"] is True
    assert result["critical"] == 1
    assert result["sent"] == 0
    assert "error" in result
