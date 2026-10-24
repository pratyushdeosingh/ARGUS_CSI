import { useEffect, useMemo, useRef, useState } from "react";
import { apiBase, syntheticSource } from "./api";
import { applyEvent, emptyMonitor } from "./monitoring";
import { generateRun, type RunConfig } from "./simulation";
import { connectStream } from "./stream";

export function useMonitoring(
  config: RunConfig,
  running: boolean,
  speed: number,
  onComplete: () => void,
) {
  const [state, setState] = useState(emptyMonitor);
  const [connection, setConnection] = useState("Connecting");
  const [error, setError] = useState("");
  const [cursor, setCursor] = useState(0);
  const index = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const records = useMemo(() => generateRun(config), [config]);
  const completion = useRef(onComplete);
  completion.current = onComplete;
  const pace = useRef(speed);
  pace.current = speed;
  const active = useRef(running);
  active.current = running;
  const session = useRef(config.session);
  session.current = config.session;
  useEffect(() => {
    setState(emptyMonitor());
    setError("");
    index.current = 0;
    setCursor(0);
    let disposed = false;
    const recover = async () => {
      const [history, events] = await Promise.all([
        syntheticSource.history(config.session),
        syntheticSource.events(config.session),
      ]);
      if (disposed) return;
      setState((current) => {
        let next = current;
        for (const transaction of history)
          next = applyEvent(next, {
            event_id: `history:${transaction.transaction_id}`,
            event_type: "transaction.received",
            timestamp: transaction.timestamp,
            data: { ...transaction },
          });
        for (const event of events) next = applyEvent(next, event);
        return next;
      });
    };
    const stop = connectStream(
      `${apiBase.replace(/^http/, "ws")}/ws/transactions`,
      (event) => {
        // Never attribute an unscoped/global event to a synthetic run.
        if (disposed || event.session_id !== config.session) return;
        setState((current) => applyEvent(current, event));
      },
      (value) => {
        if (!disposed) setConnection(value);
      },
      recover,
    );
    void recover().catch(() => {
      if (!disposed)
        setError(
          "Backend unavailable. Start the API to ingest and score synthetic payments.",
        );
    });
    return () => {
      disposed = true;
      stop();
      controller.current?.abort();
    };
  }, [config]);
  useEffect(() => {
    if (!running) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    const run = async () => {
      if (disposed || !active.current || session.current !== config.session)
        return;
      if (index.current >= records.length) {
        completion.current();
        return;
      }
      const record = records[index.current];
      controller.current = new AbortController();
      try {
        const response = await syntheticSource.ingest(
          record.transaction,
          config.session,
          controller.current.signal,
        );
        if (disposed || session.current !== config.session) return;
        setState((current) =>
          applyEvent(current, {
            event_id: `http:${record.transaction.transaction_id}`,
            event_type: "transaction.received",
            timestamp: record.transaction.timestamp,
            data: { ...response.transaction },
          }),
        );
        index.current++;
        setCursor(index.current);
        setError("");
      } catch (reason) {
        if (!disposed && session.current === config.session) {
          setError(
            reason instanceof Error ? reason.message : "Ingestion failed",
          );
          completion.current();
        }
        return;
      }
      if (!disposed) timer = setTimeout(run, 1000 / pace.current);
    };
    void run();
    // Let an in-flight payment finish on pause; switching session aborts it separately.
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [running, config, records]);
  return { state, connection, error, cursor, records };
}
