"""Transparent risk scoring for normalized system telemetry."""

from models import NormalizedEvent


BASELINE_RISK = 0.03
CATEGORY_WEIGHTS = {"process": 0.26, "file": 0.26, "network": 0.32}


def score_events(events: list[NormalizedEvent]) -> float:
    """Score unique suspicious categories, avoiding duplicate-event inflation."""

    suspicious_categories = {event.category for event in events if event.suspicious}
    score = BASELINE_RISK + sum(
        CATEGORY_WEIGHTS[category] for category in suspicious_categories
    )
    return round(min(score, 1.0), 2)
