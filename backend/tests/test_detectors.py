import json

import httpx
import pytest

from backend.app.config import Settings
from backend.app.detectors import DetectorGateway, DetectorUnavailable
from backend.app.simulator import load_attack_transactions, load_mock_signals
from backend.app.state import DemoState


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def settings(mode: str = "auto") -> Settings:
    return Settings(
        detector_mode=mode,
        graph_detector_url="http://graph.test",
        ebpf_detector_url="http://ebpf.test",
        detector_timeout_seconds=0.2,
    )


@pytest.mark.anyio
async def test_collects_contract_valid_service_signals() -> None:
    graph, system = load_mock_signals()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/analyze":
            transactions = json.loads(request.content)
            assert transactions[0]["transaction_id"] == "TX-1001"
            return httpx.Response(200, json=graph.model_dump(mode="json"))
        if request.url.path == "/simulate":
            return httpx.Response(200, json={"status": "ok", "mode": "replay"})
        if request.url.path == "/signals/latest":
            return httpx.Response(200, json=system.model_dump(mode="json"))
        return httpx.Response(404)

    gateway = DetectorGateway(
        settings(), DemoState(), httpx.MockTransport(handler)
    )
    result_graph, result_system, status = await gateway.collect(
        load_attack_transactions()
    )

    assert result_graph.signal_id == graph.signal_id
    assert result_system.signal_id == system.signal_id
    assert status.graph.origin == "service"
    assert status.system.mode == "replay"


@pytest.mark.anyio
async def test_auto_mode_uses_fixture_for_unavailable_services() -> None:
    gateway = DetectorGateway(
        settings(), DemoState(), httpx.MockTransport(lambda _: httpx.Response(503))
    )
    graph, system, status = await gateway.collect(load_attack_transactions())

    assert graph.signal_id == "GRAPH-001"
    assert system.signal_id == "EBPF-001"
    assert status.graph.origin == "fixture"
    assert status.system.availability == "offline"


@pytest.mark.anyio
async def test_auto_mode_retains_last_valid_signals() -> None:
    graph, system = load_mock_signals()
    state = DemoState()
    state.last_graph_signal = graph
    state.last_system_signal = system
    gateway = DetectorGateway(
        settings(), state, httpx.MockTransport(lambda _: httpx.Response(503))
    )

    _, _, status = await gateway.collect(load_attack_transactions())

    assert status.graph.origin == "last_known"
    assert status.system.origin == "last_known"


@pytest.mark.anyio
async def test_required_mode_fails_when_service_is_unavailable() -> None:
    gateway = DetectorGateway(
        settings("required"),
        DemoState(),
        httpx.MockTransport(lambda _: httpx.Response(503)),
    )

    with pytest.raises(DetectorUnavailable):
        await gateway.collect(load_attack_transactions())


@pytest.mark.anyio
async def test_malformed_signal_is_rejected_and_falls_back() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/analyze":
            return httpx.Response(200, json={"source": "graph_detector"})
        return httpx.Response(503)

    gateway = DetectorGateway(
        settings(), DemoState(), httpx.MockTransport(handler)
    )
    _, _, status = await gateway.collect(load_attack_transactions())

    assert status.graph.origin == "fixture"
    assert "validation" in status.graph.detail.lower()


@pytest.mark.anyio
async def test_timeout_is_reported_without_fabricating_connectivity() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow detector", request=request)

    gateway = DetectorGateway(
        settings(), DemoState(), httpx.MockTransport(handler)
    )
    _, _, status = await gateway.collect(load_attack_transactions())

    assert status.graph.availability == "offline"
    assert status.system.availability == "offline"
    assert "timed out" in status.graph.detail.lower()
