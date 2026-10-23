"""WebSocket connection manager and streaming event dispatcher for ARGUS CSI."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import Any
import uuid

from fastapi import WebSocket


logger = logging.getLogger("argus.websocket")


def create_stream_event(
    event_type: str,
    data: dict[str, Any],
    event_id: str | None = None,
    timestamp: datetime | None = None,
) -> dict[str, Any]:
    """Create a standardized event envelope for ARGUS WebSocket streaming."""
    ts = timestamp or datetime.now(timezone.utc)
    # Ensure UTC string formatted with 'Z'
    ts_str = ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "event_id": event_id or f"EVT-{uuid.uuid4().hex[:12].upper()}",
        "event_type": event_type,
        "timestamp": ts_str,
        "data": data,
    }


class WebSocketManager:
    """Thread-safe asynchronous WebSocket connection manager."""

    def __init__(self) -> None:
        self._active_connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    @property
    def active_count(self) -> int:
        return len(self._active_connections)

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register an incoming WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self._active_connections.add(websocket)
        logger.info(f"WebSocket client connected. Total active: {len(self._active_connections)}")

    async def disconnect(self, websocket: WebSocket) -> None:
        """Unregister a disconnected WebSocket client."""
        async with self._lock:
            self._active_connections.discard(websocket)
        logger.info(f"WebSocket client disconnected. Total active: {len(self._active_connections)}")

    async def send_personal(self, websocket: WebSocket, event: dict[str, Any]) -> None:
        """Send a single message directly to a specific connected client."""
        try:
            await websocket.send_json(event)
        except Exception as error:
            logger.warning(f"Failed to send personal message: {error}")
            await self.disconnect(websocket)

    async def broadcast(self, event: dict[str, Any]) -> None:
        """Broadcast a JSON event envelope to all connected clients concurrently.
        
        Failed or disconnected clients are pruned cleanly without interrupting
        delivery to other healthy clients.
        """
        async with self._lock:
            connections = list(self._active_connections)

        if not connections:
            return

        async def _send(ws: WebSocket) -> WebSocket | None:
            try:
                await ws.send_json(event)
                return None
            except Exception as error:
                logger.debug(f"Failed to send to client ({error}); marking for removal.")
                return ws

        # Broadcast to all clients concurrently
        results = await asyncio.gather(*[_send(ws) for ws in connections], return_exceptions=True)
        dead_connections = [res for res in results if isinstance(res, WebSocket)]

        if dead_connections:
            async with self._lock:
                for dead in dead_connections:
                    self._active_connections.discard(dead)
            logger.info(
                f"Pruned {len(dead_connections)} disconnected client(s). "
                f"Remaining active: {len(self._active_connections)}"
            )


websocket_manager = WebSocketManager()


def get_websocket_manager() -> WebSocketManager:
    """Dependency provider for FastAPI."""
    return websocket_manager
