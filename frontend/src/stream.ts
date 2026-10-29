import type { StreamEvent } from "./monitoring";
/** Reusable transport, injectable socket/timers for deterministic reconnection tests. */
export function connectStream(
  url: string,
  onEvent: (event: StreamEvent) => void,
  onStatus: (status: string) => void,
  recover: () => Promise<void>,
  createSocket = (url: string) => new WebSocket(url),
) {
  let stopped = false;
  let socket: WebSocket;
  let timer: ReturnType<typeof setTimeout>;
  let attempt = 0;
  function connect() {
    if (stopped) return;
    onStatus("Connecting");
    socket = createSocket(url);
    socket.onopen = () => {
      attempt = 0;
      onStatus("Connected");
      void recover().catch(() => onStatus("History unavailable"));
    };
    socket.onmessage = (event) => {
      try {
        const value = JSON.parse(String(event.data)) as StreamEvent;
        if (value.event_type && value.event_id && value.data) onEvent(value);
      } catch {
        /* Invalid payloads cannot interrupt the stream. */
      }
    };
    socket.onerror = () => {
      onStatus("Reconnecting");
      socket.close();
    };
    socket.onclose = () => {
      if (stopped) return;
      onStatus("Reconnecting");
      timer = setTimeout(connect, Math.min(15000, 1000 * 2 ** attempt++));
    };
  }
  connect();
  return () => {
    stopped = true;
    clearTimeout(timer);
    socket.onclose = null;
    socket.onmessage = null;
    socket.onopen = null;
    socket.close();
  };
}
