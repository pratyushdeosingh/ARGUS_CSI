# eBPF detector — Nitin

## Mission

Observe harmless Linux payment-service activity, identify suspicious process/file/network behavior, and return a contract-valid `SystemSignal` to ARGUS.

## Environment requirement

eBPF requires a Linux kernel. macOS is not the target kernel. Use an Ubuntu VM, a Linux cloud instance, or another verified Linux host. Record the kernel version and chosen tool in the setup documentation.

## Safe simulation

Create a harmless local `payment-worker` process that:

- launches a known test child process;
- reads a dedicated fake “sensitive” file containing no secret; and
- performs a controlled test network connection represented with the canonical suspicious IP in normalized output.

Do not access real credentials, real banking data, or unrelated system files. Do not perform destructive containment.

## Suggested structure

```text
services/ebpf-detector/
  api.py
  collector/
  normalizer.py
  scorer.py
  simulator/
  fixtures/
  requirements.txt
  tests/
  SETUP_LINUX.md
```

## Required interface

```text
GET  /health
POST /simulate
GET  /signals/latest
```

Live and replay modes must both return `contracts/system-signal.schema.json`.

## Testing target

- Raw process/file/network records normalize correctly.
- Suspicious combinations score higher than normal activity.
- Output uses the canonical host, service, process, and shared IP.
- Replay mode works without eBPF permissions.

## AI handoff

Use the Nitin prompt in the root README. Tell the AI the work is an authorized synthetic lab, but require safe paths, no secrets, and no destructive behavior.
