"""Critical-conjunction email alerts.

After the daily screen, any conjunction whose predicted miss falls below a
tight *critical* threshold (much smaller than the 5 km screening threshold)
is collected and, if alerting is configured, emailed to the operator's own
address list.

Scope discipline (see ETHICS_AND_SCOPE.md): these are screening-level
notices from public elements, NOT collision-probability warnings and NOT an
operational safety service. The email says so explicitly. Recipients are
whatever the operator configures in ORBITSENSE_ALERT_TO — the tool never
notifies third parties on its own.

Configuration (all via environment, e.g. GitHub Actions secrets):
  ORBITSENSE_ALERT_TO     comma-separated recipient addresses (required to send)
  ORBITSENSE_ALERT_KM     critical miss threshold in km (default 1.0)
  ORBITSENSE_SMTP_HOST    default smtp.gmail.com
  ORBITSENSE_SMTP_PORT    default 587 (STARTTLS)
  ORBITSENSE_SMTP_USER    SMTP username (the sending mailbox)
  ORBITSENSE_SMTP_PASS    SMTP password / app-password
  ORBITSENSE_ALERT_FROM   From address (default: SMTP_USER)
"""

from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .herald import is_docked_or_formation
from .screener import Conjunction


@dataclass
class AlertConfig:
    to: list[str]
    threshold_km: float = 1.0
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    from_addr: str = ""

    @classmethod
    def from_env(cls) -> "AlertConfig | None":
        to_raw = os.environ.get("ORBITSENSE_ALERT_TO", "").strip()
        if not to_raw:
            return None
        to = [a.strip() for a in to_raw.split(",") if a.strip()]
        if not to:
            return None
        user = os.environ.get("ORBITSENSE_SMTP_USER", "")
        return cls(
            to=to,
            threshold_km=float(os.environ.get("ORBITSENSE_ALERT_KM", "1.0")),
            smtp_host=os.environ.get("ORBITSENSE_SMTP_HOST", "smtp.gmail.com"),
            smtp_port=int(os.environ.get("ORBITSENSE_SMTP_PORT", "587")),
            smtp_user=user,
            smtp_pass=os.environ.get("ORBITSENSE_SMTP_PASS", ""),
            from_addr=os.environ.get("ORBITSENSE_ALERT_FROM", user),
        )


def critical_conjunctions(
    conjunctions: list[Conjunction],
    threshold_km: float,
    min_relative_speed_km_s: float = 0.2,
) -> list[Conjunction]:
    """Genuinely risky conjunctions below the critical miss threshold.

    Two extra filters keep the alert meaningful rather than noisy:
      - drop docked/co-located assemblies (handled by is_docked_or_formation);
      - drop near-zero closing-speed pairs. Constellation neighbors (Kuiper,
        Starlink within a plane) routinely sit tens of metres apart at ~0 km/s
        while station-keeping — that is formation flying, not an impending
        collision, and it would otherwise dominate every alert. A real
        collision risk has a meaningful relative velocity.
    """
    out = [
        c for c in conjunctions
        if c.miss_distance_km <= threshold_km
        and c.relative_speed_km_s >= min_relative_speed_km_s
        and not is_docked_or_formation(c)
    ]
    return sorted(out, key=lambda c: c.miss_distance_km)


def build_email(
    critical: list[Conjunction], threshold_km: float, max_items: int = 20
) -> tuple[str, str, str]:
    """Return (subject, text_body, html_body) for the alert.

    `critical` is the full sorted list; the email shows the tightest
    `max_items` and states the total so a dense day stays readable.
    """
    n = len(critical)
    shown = critical[:max_items]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    subject = f"[OrbitSense] {n} close approach{'es' if n != 1 else ''} under {threshold_km:g} km"
    more = f"\n…and {n - len(shown)} more below {threshold_km:g} km.\n" if n > len(shown) else ""

    rows_txt = []
    rows_html = []
    for c in shown:
        line = (
            f"{c.name_a}  x  {c.name_b}\n"
            f"    miss {c.miss_distance_km:.3f} km   rel {c.relative_speed_km_s:.2f} km/s"
            f"   TCA {c.tca:%Y-%m-%d %H:%M:%S} UTC\n"
        )
        rows_txt.append(line)
        rows_html.append(
            f"<tr><td>{c.name_a}</td><td>{c.name_b}</td>"
            f"<td style='text-align:right'><b>{c.miss_distance_km:.3f} km</b></td>"
            f"<td style='text-align:right'>{c.relative_speed_km_s:.2f} km/s</td>"
            f"<td>{c.tca:%Y-%m-%d %H:%M} UTC</td></tr>"
        )

    disclaimer = (
        "Screening-level estimate from public catalog elements (km-scale "
        "uncertainty). This is NOT a collision-probability warning and NOT an "
        "operational safety service. No covariance data is used."
    )

    text = (
        f"OrbitSense critical close-approach alert — {now}\n"
        f"{n} conjunction(s) predicted within {threshold_km:g} km in the next window.\n\n"
        + "\n".join(rows_txt)
        + more
        + f"\n{disclaimer}\n\nDashboard: https://orbitsense.vercel.app\n"
    )

    html = (
        f"<h2>OrbitSense close-approach alert</h2>"
        f"<p>{now} — <b>{n}</b> conjunction(s) predicted within "
        f"<b>{threshold_km:g} km</b>.</p>"
        f"<table cellpadding='6' style='border-collapse:collapse;font-family:sans-serif;font-size:13px'>"
        f"<tr style='border-bottom:1px solid #ccc'><th align='left'>Object A</th>"
        f"<th align='left'>Object B</th><th>Miss</th><th>Rel. speed</th><th>TCA</th></tr>"
        + "".join(rows_html)
        + f"</table>"
        + (f"<p style='color:#666'>…and {n - len(shown)} more below "
           f"{threshold_km:g} km.</p>" if n > len(shown) else "")
        + f"<p style='color:#666;font-size:12px;margin-top:16px'>{disclaimer}</p>"
        f"<p><a href='https://orbitsense.vercel.app'>Open the live dashboard</a></p>"
    )
    return subject, text, html


def send_email(cfg: AlertConfig, subject: str, text: str, html: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg.from_addr or cfg.smtp_user
    msg["To"] = ", ".join(cfg.to)
    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=60) as server:
        server.starttls()
        if cfg.smtp_user:
            server.login(cfg.smtp_user, cfg.smtp_pass)
        server.sendmail(msg["From"], cfg.to, msg.as_string())


def maybe_alert(conjunctions: list[Conjunction], cfg: AlertConfig | None = None) -> dict:
    """Send an alert if configured and any conjunction breaches the threshold.

    Returns a summary dict; never raises on send failure (logged into the dict)
    so a mail outage cannot break the pipeline.
    """
    cfg = cfg or AlertConfig.from_env()
    if cfg is None:
        return {"configured": False, "sent": 0}

    critical = critical_conjunctions(conjunctions, cfg.threshold_km)
    if not critical:
        return {"configured": True, "critical": 0, "sent": 0}

    subject, text, html = build_email(critical, cfg.threshold_km)
    try:
        send_email(cfg, subject, text, html)
        return {"configured": True, "critical": len(critical), "sent": len(cfg.to),
                "recipients": cfg.to}
    except Exception as e:  # noqa: BLE001 — never break the pipeline on mail failure
        return {"configured": True, "critical": len(critical), "sent": 0,
                "error": f"{type(e).__name__}: {e}"}
