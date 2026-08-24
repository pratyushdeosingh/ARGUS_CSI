"""Convert collector-specific records into stable, explainable evidence."""

from models import NormalizedEvent, RawEvent


CANONICAL_PROCESS = "payment-worker"
CANONICAL_SUSPICIOUS_IP = "185.220.101.10"
SENSITIVE_FILE_MARKER = "fake-sensitive-config.json"


def normalize_event(event: RawEvent) -> NormalizedEvent:
    details = event.details

    if event.event_type == "process_exec":
        unexpected = bool(details.get("unexpected_child"))
        return NormalizedEvent(
            timestamp=event.timestamp,
            category="process",
            process=event.process,
            suspicious=unexpected,
            indicator="Unexpected child process" if unexpected else None,
        )

    if event.event_type == "file_open":
        path = str(details.get("path", ""))
        sensitive = SENSITIVE_FILE_MARKER in path
        return NormalizedEvent(
            timestamp=event.timestamp,
            category="file",
            process=event.process,
            suspicious=sensitive,
            indicator=(
                "Sensitive configuration file accessed" if sensitive else None
            ),
        )

    destination = str(details.get("destination_ip", ""))
    suspicious = bool(details.get("suspicious_destination")) or (
        destination == CANONICAL_SUSPICIOUS_IP
    )
    return NormalizedEvent(
        timestamp=event.timestamp,
        category="network",
        process=event.process,
        suspicious=suspicious,
        indicator=(
            "Connection to suspicious external IP" if suspicious else None
        ),
        related_ip=destination or (CANONICAL_SUSPICIOUS_IP if suspicious else None),
    )


def normalize_events(events: list[RawEvent]) -> list[NormalizedEvent]:
    return [normalize_event(event) for event in events]
