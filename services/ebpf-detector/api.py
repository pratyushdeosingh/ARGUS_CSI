"""FastAPI adapter for portable replay and Linux eBPF telemetry."""

import asyncio
import os
from dataclasses import dataclass, field
from threading import Lock
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from collector.bpftrace import availability, collect_live
from collector.replay import collect_replay
from models import SystemSignal
from normalizer import normalize_events
from signal_builder import build_signal

Mode = Literal["auto", "live", "replay"]


class SimulationResult(BaseModel):
    status: Literal["ok"] = "ok"
    mode: Literal["live", "replay"]
    signal_id: str
    events_collected: int
    detail: str


@dataclass
class DetectorRuntime:
    configured_mode: Mode = "auto"
    latest_signal: SystemSignal | None = None
    effective_mode: Literal["live", "replay"] = "replay"
    detail: str = "No simulation has run yet."
    _lock: Lock = field(default_factory=Lock)

    @classmethod
    def from_env(cls) -> "DetectorRuntime":
        configured = os.getenv("ARGUS_EBPF_MODE", "auto").lower()
        if configured not in {"auto", "live", "replay"}:
            raise RuntimeError("ARGUS_EBPF_MODE must be auto, live, or replay")
        return cls(configured_mode=configured)  # type: ignore[arg-type]

    def health(self) -> dict[str, object]:
        live_available, reason = availability()
        if self.configured_mode == "live":
            effective = "live"
        elif self.configured_mode == "auto" and live_available:
            effective = "live"
        else:
            effective = "replay"
        return {
            "status": "ok",
            "mode": effective,
            "configured_mode": self.configured_mode,
            "live_available": live_available,
            "detail": reason if effective == "live" else f"Replay ready; {reason}.",
        }

    def simulate(self, scenario: str) -> SimulationResult:
        with self._lock:
            live_available, reason = availability()
            use_live = self.configured_mode == "live" or (
                self.configured_mode == "auto" and live_available
            )
            if use_live and not live_available:
                raise RuntimeError(reason)
            if use_live and scenario != "attack":
                raise ValueError("live collection supports only the safe attack scenario")

            if use_live:
                events = collect_live()
                mode: Literal["live", "replay"] = "live"
                detail = "Collected synthetic payment-worker events with bpftrace."
            else:
                events = collect_replay(scenario)
                mode = "replay"
                detail = f"Loaded sanitized replay telemetry. Live collector status: {reason}."

            signal = build_signal(normalize_events(events))
            self.latest_signal = signal
            self.effective_mode = mode
            self.detail = detail
            return SimulationResult(
                mode=mode,
                signal_id=signal.signal_id,
                events_collected=len(events),
                detail=detail,
            )


runtime = DetectorRuntime.from_env()
app = FastAPI(
    title="ARGUS eBPF Detector",
    version="1.0.0",
    description="Safe Linux telemetry collector with deterministic replay fallback.",
)


@app.get("/health")
def health() -> dict[str, object]:
    return runtime.health()


@app.post("/simulate", response_model=SimulationResult)
async def simulate(
    scenario: Literal["attack", "normal"] = Query(default="attack"),
) -> SimulationResult:
    try:
        return await asyncio.to_thread(runtime.simulate, scenario)
    except (RuntimeError, ValueError) as error:
        status_code = 503 if isinstance(error, RuntimeError) else 422
        raise HTTPException(status_code=status_code, detail=str(error)) from error


@app.get("/signals/latest", response_model=SystemSignal)
def latest_signal() -> SystemSignal:
    if runtime.latest_signal is None:
        raise HTTPException(status_code=404, detail="No signal available. Run POST /simulate first.")
    return runtime.latest_signal
