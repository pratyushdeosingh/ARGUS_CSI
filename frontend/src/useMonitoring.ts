import { useEffect, useRef, useState } from "react";
import { apiBase, syntheticSource } from "./api";
import { applyEvent, emptyMonitor } from "./monitoring";
import {
  generateRun,
  type RunConfig,
  type SyntheticRecord,
} from "./simulation";
import { connectStream } from "./stream";

const NO_RECORDS: SyntheticRecord[] = [];

export function useMonitoring(
  config: RunConfig,
  running: boolean,
  speed: number,
  onComplete: () => void,
  onInvestigationsChanged?: () => void,
) {
  const [state, setState] = useState(emptyMonitor);
  const [connection, setConnection] = useState("Connecting");
  const [error, setError] = useState("");
  const [cursor, setCursor] = useState(0);
  const index = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const [generated, setGenerated] = useState<{
    config: RunConfig;
    records: SyntheticRecord[];
  } | null>(null);
  const records = generated?.config === config ? generated.records : NO_RECORDS;
  const casesChanged = useRef(onInvestigationsChanged);
  casesChanged.current = onInvestigationsChanged;
  const inFlight = useRef<{ session: string; task: Promise<boolean> } | null>(
    null,
  );
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
    setGenerated(null);
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
      casesChanged.current?.();
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
        if (!disposed && event.event_type === "investigation.updated")
          casesChanged.current?.();
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
    if (running && generated?.config !== config)
      setGenerated({ config, records: generateRun(config) });
  }, [running, config, generated]);
  useEffect(() => {
    if (!running || records.length === 0) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    const run = async () => {
      if (disposed || !active.current || session.current !== config.session)
        return;
      if (index.current >= records.length) {
        completion.current();
        return;
      }
      const pending = inFlight.current;
      if (pending?.session === config.session) {
        const succeeded = await pending.task;
        if (succeeded && !disposed) void run();
        return;
      }
      const record = records[index.current];
      controller.current = new AbortController();
      const task = (async () => {
        try {
          const response = await syntheticSource.ingest(
            record.transaction,
            config.session,
            controller.current!.signal,
            config.scenario,
          );
          // Pause does not discard an accepted payment or advance it twice on resume.
          if (session.current !== config.session) return false;
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
          return true;
        } catch (reason) {
          if (session.current === config.session) {
            setError(
              reason instanceof Error ? reason.message : "Ingestion failed",
            );
            completion.current();
          }
          return false;
        }
      })();
      const entry = { session: config.session, task };
      inFlight.current = entry;
      const succeeded = await task;
      if (inFlight.current === entry) inFlight.current = null;
      if (!succeeded) return;
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
