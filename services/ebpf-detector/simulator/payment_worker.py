"""Harmless payment-worker activity used only by the live eBPF demo."""

import ctypes
import socket
import subprocess
from pathlib import Path


def _set_process_name() -> None:
    libc = ctypes.CDLL(None)
    libc.prctl(15, b"payment-worker", 0, 0, 0)


def _controlled_loopback_connection() -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    client = socket.create_connection(server.getsockname(), timeout=1)
    connection, _ = server.accept()
    client.sendall(b"ARGUS_SAFE_TEST")
    connection.recv(64)
    client.close()
    connection.close()
    server.close()


def main() -> None:
    _set_process_name()
    subprocess.run(["/bin/echo", "argus-safe-child"], check=True)  # noqa: S603
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "fake-sensitive-config.json"
    fixture.read_text(encoding="utf-8")
    _controlled_loopback_connection()


if __name__ == "__main__":
    main()
