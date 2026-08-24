"""HTTP adapters and fallback policy for the two detector services."""

import asyncio
from typing import Any

import httpx

from .config import Settings
from .models import (
    DetectorComponentStatus,
    DetectorStatus,
    GraphSignal,
    RawTelemetryEvent,
    SystemSignal,
    Transaction,
)
from .simulator import load_mock_signals
from .state import DemoState, demo_state


class DetectorUnavailable(RuntimeError):
    """Raised when required detector mode cannot obtain both signals."""


class DetectorGateway:
    def __init__(
        self,
        settings: Settings,
        state: DemoState = demo_state,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.state = state
        self.transport = transport

    async def collect(
        self, transactions: list[Transaction]
    ) -> tuple[GraphSignal, SystemSignal, DetectorStatus]:
        if self.settings.detector_mode == "fixture":
            graph, system = load_mock_signals()
            return graph, system, DetectorStatus(
                graph=self._fixture_status("Fixture-only mode is configured."),
                system=self._fixture_status("Fixture-only mode is configured."),
            )

        timeout = httpx.Timeout(self.settings.detector_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout, transport=self.transport) as client:
            graph_result, system_result = await asyncio.gather(
                self._fetch_graph(client, transactions),
                self._fetch_system(client),
                return_exceptions=True,
            )

        graph, graph_status = self._resolve_graph(graph_result)
        system, system_status = self._resolve_system(system_result)
        return graph, system, DetectorStatus(graph=graph_status, system=system_status)

    async def analyze_payload(
        self,
        transactions: list[Transaction],
        *,
        baseline_transactions: list[Transaction] | None = None,
        telemetry_events: list[RawTelemetryEvent] | None = None,
        supplied_system_signal: SystemSignal | None = None,
        correlate_with_latest_system: bool = False,
        telemetry_host: str = "payment-node-01",
        telemetry_service: str = "payment-api",
    ) -> tuple[GraphSignal, SystemSignal | None, DetectorStatus]:
        """Analyze caller data without ever substituting canonical fixtures."""

        if self.settings.detector_mode == "fixture":
            raise DetectorUnavailable(
                "Arbitrary analysis is unavailable in fixture mode. Start the detector services."
            )

        timeout = httpx.Timeout(self.settings.detector_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout, transport=self.transport) as client:
            try:
                graph = await self._fetch_graph(
                    client,
                    transactions,
                    baseline_transactions=baseline_transactions,
                )
            except Exception as error:
                raise DetectorUnavailable(
                    f"Graph detector could not analyze this batch: {self._error_detail(error)}"
                ) from error

            graph_status = DetectorComponentStatus(
                availability="online",
                origin="service",
                detail="Graph detector analyzed caller-supplied transactions.",
            )
            self.state.last_graph_signal = graph

            system: SystemSignal | None = None
            if supplied_system_signal is not None:
                system = supplied_system_signal
                system_status = DetectorComponentStatus(
                    availability="online",
                    origin="service",
                    mode="unknown",
                    detail="Contract-valid infrastructure signal supplied by the caller.",
                )
            elif telemetry_events:
                try:
                    system = await self._fetch_telemetry(
                        client,
                        telemetry_events,
                        host=telemetry_host,
                        service=telemetry_service,
                    )
                except Exception as error:
                    raise DetectorUnavailable(
                        f"eBPF detector could not analyze telemetry: {self._error_detail(error)}"
                    ) from error
                system_status = DetectorComponentStatus(
                    availability="online",
                    origin="service",
                    mode="unknown",
                    detail="eBPF detector analyzed caller-supplied telemetry.",
                )
            elif correlate_with_latest_system:
                try:
                    system = await self._fetch_latest_system(client)
                except Exception as error:
                    raise DetectorUnavailable(
                        f"No usable latest infrastructure signal: {self._error_detail(error)}"
                    ) from error
                system_status = DetectorComponentStatus(
                    availability="online",
                    origin="service",
                    mode="unknown",
                    detail="Correlated with the detector's latest infrastructure signal.",
                )
            else:
                system_status = DetectorComponentStatus(
                    availability="offline",
                    origin="none",
                    mode="unknown",
                    detail="No infrastructure telemetry was supplied; graph-only analysis completed.",
                )

        if system is not None:
            self.state.last_system_signal = system
        return graph, system, DetectorStatus(graph=graph_status, system=system_status)

    async def status(self) -> DetectorStatus:
        if self.settings.detector_mode == "fixture":
            return DetectorStatus(
                graph=self._fixture_status("Fixture-only mode is configured."),
                system=self._fixture_status("Fixture-only mode is configured."),
            )

        timeout = httpx.Timeout(self.settings.detector_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout, transport=self.transport) as client:
            graph_result, system_result = await asyncio.gather(
                self._probe(client, self.settings.graph_detector_url),
                self._probe(client, self.settings.ebpf_detector_url),
                return_exceptions=True,
            )
        return DetectorStatus(
            graph=self._probe_status(graph_result, "graph"),
            system=self._probe_status(system_result, "system"),
        )

    async def _fetch_graph(
        self,
        client: httpx.AsyncClient,
        transactions: list[Transaction],
        baseline_transactions: list[Transaction] | None = None,
    ) -> GraphSignal:
        if baseline_transactions:
            response = await client.post(
                f"{self.settings.graph_detector_url}/analyze-context",
                json={
                    "transactions": [
                        transaction.model_dump(mode="json") for transaction in transactions
                    ],
                    "baseline_transactions": [
                        transaction.model_dump(mode="json")
                        for transaction in baseline_transactions
                    ],
                },
            )
            response.raise_for_status()
            return GraphSignal.model_validate(response.json())
        response = await client.post(
            f"{self.settings.graph_detector_url}/analyze",
            json=[transaction.model_dump(mode="json") for transaction in transactions],
        )
        response.raise_for_status()
        return GraphSignal.model_validate(response.json())

    async def _fetch_system(
        self, client: httpx.AsyncClient
    ) -> tuple[SystemSignal, str]:
        simulation = await client.post(f"{self.settings.ebpf_detector_url}/simulate")
        simulation.raise_for_status()
        reported_mode = "unknown"
        try:
            payload = simulation.json()
            if isinstance(payload, dict) and payload.get("mode") in {"live", "replay"}:
                reported_mode = payload["mode"]
        except ValueError:
            pass
        response = await client.get(f"{self.settings.ebpf_detector_url}/signals/latest")
        response.raise_for_status()
        return SystemSignal.model_validate(response.json()), reported_mode

    async def _fetch_telemetry(
        self,
        client: httpx.AsyncClient,
        events: list[RawTelemetryEvent],
        *,
        host: str,
        service: str,
    ) -> SystemSignal:
        response = await client.post(
            f"{self.settings.ebpf_detector_url}/analyze-events",
            json={
                "events": [event.model_dump(mode="json") for event in events],
                "host": host,
                "service": service,
            },
        )
        response.raise_for_status()
        return SystemSignal.model_validate(response.json())

    async def _fetch_latest_system(self, client: httpx.AsyncClient) -> SystemSignal:
        response = await client.get(f"{self.settings.ebpf_detector_url}/signals/latest")
        response.raise_for_status()
        return SystemSignal.model_validate(response.json())

    async def _probe(self, client: httpx.AsyncClient, base_url: str) -> dict[str, Any]:
        response = await client.get(f"{base_url}/health")
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("status") != "ok":
            raise ValueError("Health response must contain status=ok")
        return payload

    def _resolve_graph(
        self, result: GraphSignal | BaseException
    ) -> tuple[GraphSignal, DetectorComponentStatus]:
        if isinstance(result, GraphSignal):
            self.state.last_graph_signal = result
            return result, DetectorComponentStatus(
                availability="online",
                origin="service",
                detail="Graph detector returned a contract-valid signal.",
            )
        return self._graph_fallback(self._error_detail(result))

    def _resolve_system(
        self, result: tuple[SystemSignal, str] | BaseException
    ) -> tuple[SystemSignal, DetectorComponentStatus]:
        if isinstance(result, tuple):
            signal, mode = result
            self.state.last_system_signal = signal
            return signal, DetectorComponentStatus(
                availability="online",
                origin="service",
                mode=mode,  # type: ignore[arg-type]
                detail="eBPF detector returned a contract-valid signal.",
            )
        return self._system_fallback(self._error_detail(result))

    def _graph_fallback(
        self, detail: str
    ) -> tuple[GraphSignal, DetectorComponentStatus]:
        if self.settings.detector_mode == "required":
            raise DetectorUnavailable(f"Graph detector unavailable: {detail}")
        if self.state.last_graph_signal is not None:
            return self.state.last_graph_signal, DetectorComponentStatus(
                availability="degraded",
                origin="last_known",
                detail=f"Graph detector unavailable; using last valid signal. {detail}",
            )
        graph, _ = load_mock_signals()
        return graph, DetectorComponentStatus(
            availability="offline",
            origin="fixture",
            mode="fixture",
            detail=f"Graph detector unavailable; using canonical fixture. {detail}",
        )

    def _system_fallback(
        self, detail: str
    ) -> tuple[SystemSignal, DetectorComponentStatus]:
        if self.settings.detector_mode == "required":
            raise DetectorUnavailable(f"eBPF detector unavailable: {detail}")
        if self.state.last_system_signal is not None:
            return self.state.last_system_signal, DetectorComponentStatus(
                availability="degraded",
                origin="last_known",
                detail=f"eBPF detector unavailable; using last valid signal. {detail}",
            )
        _, system = load_mock_signals()
        return system, DetectorComponentStatus(
            availability="offline",
            origin="fixture",
            mode="fixture",
            detail=f"eBPF detector unavailable; using canonical replay fixture. {detail}",
        )

    def _probe_status(
        self, result: dict[str, Any] | BaseException, component: str
    ) -> DetectorComponentStatus:
        if isinstance(result, dict):
            mode = result.get("mode", "unknown")
            if mode not in {"live", "replay"}:
                mode = "unknown"
            return DetectorComponentStatus(
                availability="online",
                origin="service",
                mode=mode,
                detail=f"{component.title()} detector health check passed.",
            )
        cached = (
            self.state.last_graph_signal
            if component == "graph"
            else self.state.last_system_signal
        )
        if cached is not None:
            return DetectorComponentStatus(
                availability="degraded",
                origin="last_known",
                detail=f"Health check failed; a last valid {component} signal is cached. "
                f"{self._error_detail(result)}",
            )
        origin = "none" if self.settings.detector_mode == "required" else "fixture"
        mode = "unknown" if origin == "none" else "fixture"
        return DetectorComponentStatus(
            availability="offline",
            origin=origin,  # type: ignore[arg-type]
            mode=mode,  # type: ignore[arg-type]
            detail=f"Health check failed. {self._error_detail(result)}",
        )

    @staticmethod
    def _fixture_status(detail: str) -> DetectorComponentStatus:
        return DetectorComponentStatus(
            availability="offline", origin="fixture", mode="fixture", detail=detail
        )

    @staticmethod
    def _error_detail(error: BaseException) -> str:
        if isinstance(error, httpx.HTTPStatusError):
            return f"HTTP {error.response.status_code}."
        if isinstance(error, httpx.TimeoutException):
            return "Request timed out."
        return str(error) or error.__class__.__name__


def get_detector_gateway() -> DetectorGateway:
    return DetectorGateway(Settings.from_env())
