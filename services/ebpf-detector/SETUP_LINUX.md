# Linux live-telemetry setup

Replay mode is portable and is the default fallback. Live mode requires a Linux host with eBPF enabled; Ubuntu 22.04 or 24.04 and Python 3.11+ are the tested target. The service checks the operating system, `bpftrace` executable, and effective user privileges before tracing.

## Install and verify

```bash
sudo apt-get update
sudo apt-get install -y bpftrace python3-venv
uname -a
bpftrace --version
sudo bpftrace -l 'tracepoint:syscalls:sys_enter_execve' | head
```

Record `uname -a` and `bpftrace --version` in demo notes so the live evidence is reproducible. Some cloud kernels disable eBPF or tracing even for root; use replay mode there.

## Verified environment

The live path was verified on 2026-08-21 using Ubuntu 24.04 under WSL2,
kernel `6.18.33.2-microsoft-standard-WSL2`, and bpftrace `0.20.2`. The opt-in
live API test captured process execution, access to the fake configuration
file, and the controlled loopback connection, producing the canonical risk
score of `0.87` and all three expected indicators.

## Run

```bash
cd services/ebpf-detector
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
ARGUS_EBPF_MODE=replay uvicorn api:app --host 127.0.0.1 --port 8002
sudo --preserve-env=PATH ARGUS_EBPF_MODE=live .venv/bin/uvicorn api:app --host 127.0.0.1 --port 8002

# Optional end-to-end live collector test
sudo --preserve-env=PATH ARGUS_RUN_LIVE_EBPF_TEST=1 .venv/bin/pytest -q tests/test_live.py
```

`auto` selects live mode only when every prerequisite is present; otherwise it reports and uses replay mode. `live` is strict and returns HTTP 503 when eBPF cannot run.

## Safety boundary

- The trace is filtered to the synthetic process name `payment-worker`.
- The collector records syscall metadata only and never reads captured files.
- The fake configuration file contains no credential or banking data.
- The worker opens a loopback socket only. It does **not** contact `185.220.101.10`; replay/normalization maps the controlled observation to that canonical synthetic IOC.
- No containment, firewall, process-kill, or filesystem mutation is performed.

Stop the API with `Ctrl+C`. The short-lived tracer is terminated after each simulation request.
