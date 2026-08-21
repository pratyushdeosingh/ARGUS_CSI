"""Runtime configuration for detector integration."""

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    detector_mode: str
    graph_detector_url: str
    ebpf_detector_url: str
    detector_timeout_seconds: float

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
        return cls(
            detector_mode=mode,
            graph_detector_url=os.getenv(
                "GRAPH_DETECTOR_URL", "http://127.0.0.1:8001"
            ).rstrip("/"),
            ebpf_detector_url=os.getenv(
                "EBPF_DETECTOR_URL", "http://127.0.0.1:8002"
            ).rstrip("/"),
            detector_timeout_seconds=timeout,
        )
