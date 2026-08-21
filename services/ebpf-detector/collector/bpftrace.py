"""Linux-only bpftrace collector for the synthetic payment worker.

The trace program observes exec, open, and connect syscalls. It is deliberately
filtered to the synthetic process name and never reads file contents or sends
traffic to the canonical suspicious IP.
"""

import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from models import RawEvent
from normalizer import CANONICAL_PROCESS, CANONICAL_SUSPICIOUS_IP


TRACE_PROGRAM = r'''
tracepoint:syscalls:sys_enter_execve /comm == "payment-worker"/ {
  printf("{\"event_type\":\"process_exec\",\"value\":\"%s\"}\n", str(args->filename));
}
tracepoint:syscalls:sys_enter_openat /comm == "payment-worker"/ {
  printf("{\"event_type\":\"file_open\",\"value\":\"%s\"}\n", str(args->filename));
}
tracepoint:syscalls:sys_enter_connect /comm == "payment-worker"/ {
  printf("{\"event_type\":\"network_connect\",\"value\":\"observed\"}\n");
}
'''


def availability() -> tuple[bool, str]:
    if platform.system() != "Linux":
        return False, "live collection requires Linux"
    if shutil.which("bpftrace") is None:
        return False, "bpftrace is not installed"
    if not hasattr(os, "geteuid") or os.geteuid() != 0:
        return False, "live collection requires root eBPF privileges"
    return True, "bpftrace and required privileges are available"


def collect_live(timeout_seconds: float = 8.0) -> list[RawEvent]:
    available, reason = availability()
    if not available:
        raise RuntimeError(reason)

    command = ["bpftrace", "-q", "-e", TRACE_PROGRAM]
    tracer = subprocess.Popen(  # noqa: S603 - fixed executable and arguments
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        time.sleep(1.0)
        worker = Path(__file__).resolve().parents[1] / "simulator" / "payment_worker.py"
        subprocess.run(  # noqa: S603 - trusted local simulator path
            [sys.executable, str(worker)],
            check=True,
            timeout=5,
            capture_output=True,
            text=True,
        )
        time.sleep(0.5)
    finally:
        tracer.terminate()

    stdout, stderr = tracer.communicate(timeout=timeout_seconds)
    if tracer.returncode not in {0, -15} and not stdout:
        raise RuntimeError(f"bpftrace failed: {stderr.strip() or 'unknown error'}")

    timestamp = datetime.now(timezone.utc)
    events: list[RawEvent] = []
    for line in stdout.splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        event_type = record.get("event_type")
        value = str(record.get("value", ""))
        if event_type == "process_exec":
            details = {"child": value, "unexpected_child": True}
        elif event_type == "file_open":
            details = {"path": value}
        elif event_type == "network_connect":
            # The worker connects only to loopback. The synthetic scenario maps
            # that observed connect to the canonical threat-intelligence IOC.
            details = {
                "observed_destination": "127.0.0.1",
                "destination_ip": CANONICAL_SUSPICIOUS_IP,
                "suspicious_destination": True,
            }
        else:
            continue
        events.append(
            RawEvent(
                timestamp=timestamp,
                event_type=event_type,
                process=CANONICAL_PROCESS,
                details=details,
            )
        )

    if not events:
        raise RuntimeError("bpftrace returned no synthetic worker events")
    return events
