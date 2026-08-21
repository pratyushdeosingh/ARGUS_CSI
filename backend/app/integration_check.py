"""Live contract smoke test for teammate detector services."""

import asyncio
from dataclasses import replace

from .config import Settings
from .detectors import DetectorGateway, DetectorUnavailable
from .simulator import load_attack_transactions
from .state import DemoState


async def _run() -> int:
    settings = replace(Settings.from_env(), detector_mode="required")
    gateway = DetectorGateway(settings, DemoState())
    try:
        graph, system, status = await gateway.collect(load_attack_transactions())
    except DetectorUnavailable as error:
        print(f"INTEGRATION CHECK FAILED: {error}")
        return 1

    print("INTEGRATION CHECK PASSED")
    print(f"Graph: {graph.signal_id} risk={graph.risk_score:.2f} ({status.graph.origin})")
    print(
        f"eBPF: {system.signal_id} risk={system.risk_score:.2f} "
        f"({status.system.origin}, mode={status.system.mode})"
    )
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
