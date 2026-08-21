"""Build the exact SystemSignal contract from normalized observations."""

from datetime import datetime, timezone

from models import NormalizedEvent, SystemSignal
from normalizer import CANONICAL_PROCESS
from scorer import score_events


def build_signal(
    events: list[NormalizedEvent],
    *,
    signal_id: str = "EBPF-001",
) -> SystemSignal:
    suspicious = [event for event in events if event.suspicious]
    timestamp = max(
        (event.timestamp for event in events),
        default=datetime.now(timezone.utc),
    )
    indicators = list(
        dict.fromkeys(
            event.indicator for event in suspicious if event.indicator is not None
        )
    )
    related_ips = list(
        dict.fromkeys(
            event.related_ip for event in suspicious if event.related_ip is not None
        )
    )
    categories = {event.category for event in suspicious}
    if len(categories) > 1:
        event_type = "suspicious_process_and_network_activity"
    elif categories:
        event_type = f"suspicious_{next(iter(categories))}_activity"
    else:
        event_type = "normal_payment_service_activity"

    return SystemSignal(
        signal_id=signal_id,
        timestamp=timestamp,
        risk_score=score_events(events),
        host="payment-node-01",
        service="payment-api",
        process=CANONICAL_PROCESS,
        event_type=event_type,
        related_ips=related_ips,
        indicators=indicators,
    )
