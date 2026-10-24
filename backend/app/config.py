"""Runtime configuration for detector integration."""

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    detector_mode: str
    graph_detector_url: str
    ebpf_detector_url: str
    detector_timeout_seconds: float
    fraud_alert_threshold: float = 0.70
    scam_alert_threshold: float = 70.0
    analysis_window_minutes: int = 15
    analysis_max_transactions: int = 100

    @classmethod
    def from_env(cls) -> "Settings":
        mode = os.getenv("ARGUS_DETECTOR_MODE", "auto").lower()
        if mode not in {"auto", "fixture", "required"}:
            raise ValueError(
                "ARGUS_DETECTOR_MODE must be one of: auto, fixture, required"
            )
        timeout = float(os.getenv("DETECTOR_TIMEOUT_SECONDS", "2.5"))
        if timeout <= 0:
            raise ValueError("DETECTOR_TIMEOUT_SECONDS must be greater than zero")
        threshold = float(os.getenv("FRAUD_ALERT_THRESHOLD", "0.70"))
        scam_threshold = float(os.getenv("SCAM_ALERT_THRESHOLD", "70.0"))
        window_minutes = int(os.getenv("ANALYSIS_WINDOW_MINUTES", "15"))
        max_transactions = int(os.getenv("ANALYSIS_MAX_TRANSACTIONS", "100"))
        if not 0 <= threshold <= 1:
            raise ValueError("FRAUD_ALERT_THRESHOLD must be between zero and one")
        if not 0 <= scam_threshold <= 100:
            raise ValueError("SCAM_ALERT_THRESHOLD must be between zero and 100")
        if window_minutes <= 0:
            raise ValueError("ANALYSIS_WINDOW_MINUTES must be positive")
        if not 1 <= max_transactions <= 5000:
            raise ValueError("ANALYSIS_MAX_TRANSACTIONS must be between 1 and 5000")
        return cls(
            detector_mode=mode,
            graph_detector_url=os.getenv(
                "GRAPH_DETECTOR_URL", "http://127.0.0.1:8001"
            ).rstrip("/"),
            ebpf_detector_url=os.getenv(
                "EBPF_DETECTOR_URL", "http://127.0.0.1:8002"
            ).rstrip("/"),
            detector_timeout_seconds=timeout,
            fraud_alert_threshold=threshold,
            scam_alert_threshold=scam_threshold,
            analysis_window_minutes=window_minutes,
            analysis_max_transactions=max_transactions,
        )


def get_settings() -> Settings:
    """Dependency provider for FastAPI."""
    return Settings.from_env()
