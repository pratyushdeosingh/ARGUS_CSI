import { memo, useEffect, useRef } from "react";
import type { Core } from "cytoscape";
import type { Transaction } from "./types";
export const MoneyGraph = memo(function MoneyGraph({
  transactions,
  selected,
  suspicious,
  onTransaction,
  onAccount,
}: {
  transactions: Transaction[];
  selected?: string;
  suspicious: string[];
  onTransaction: (id: string) => void;
  onAccount: (account: string) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const graph = useRef<Core | undefined>(undefined);
  const callbacks = useRef({ onTransaction, onAccount });
  callbacks.current = { onTransaction, onAccount };
  useEffect(() => {
    let disposed = false;
    let observer: ResizeObserver;
    void import("cytoscape").then(({ default: cytoscape }) => {
      if (disposed || !container.current) return;
      graph.current = cytoscape({
        container: container.current,
        minZoom: 0.25,
        maxZoom: 3,
        elements: [],
        style: [
          {
            selector: "node",
            style: {
              label: "data(label)",
              width: 40,
              height: 40,
              "background-color": "#303936",
              "border-color": "#71867a",
              "border-width": 1,
              color: "#c9cfcb",
              "font-size": 9,
              "text-valign": "bottom",
              "text-margin-y": 7,
            },
          },
          {
            selector: "node.risk",
            style: { "border-color": "#c17c74", "background-color": "#4b3432" },
          },
          {
            selector: "node.endpoint",
            style: { "border-width": 3, "border-color": "#e3d8b5" },
          },
          {
            selector: "edge",
            style: {
              label: "data(label)",
              width: 1.5,
              "curve-style": "bezier",
              "target-arrow-shape": "triangle",
              "line-color": "#5d6560",
              "target-arrow-color": "#5d6560",
              color: "#a5aaa6",
              "font-size": 9,
              "text-background-color": "#1b1d1f",
              "text-background-opacity": 1,
              "text-background-padding": "3px",
            },
          },
          {
            selector: "edge.selected",
            style: {
              width: 3,
              "line-color": "#d3c59e",
              "target-arrow-color": "#d3c59e",
              color: "#f2e8cd",
            },
          },
          { selector: "edge.cancelled", style: { "line-style": "dashed" } },
        ],
      });
      graph.current.on("tap", "edge", (event) =>
        callbacks.current.onTransaction(event.target.id()),
      );
      graph.current.on("tap", "node", (event) =>
        callbacks.current.onAccount(event.target.id()),
      );
      observer = new ResizeObserver(() => {
        graph.current?.resize();
        graph.current?.fit(undefined, 35);
      });
      observer.observe(container.current);
      update();
    });
    function update() {
      const cy = graph.current;
      if (!cy) return;
      cy.elements().remove();
      const chosen = transactions.find((t) => t.transaction_id === selected);
      const endpoints = new Set([
        chosen?.source_account,
        chosen?.destination_account,
      ]);
      const nodes = [
        ...new Set(
          transactions.flatMap((t) => [
            t.source_account,
            t.destination_account,
          ]),
        ),
      ];
      const labeledPairs = new Set<string>();
      function edgeLabel(t: Transaction) {
        const pair = `${t.source_account}:${t.destination_account}`;
        if (labeledPairs.has(pair)) return "";
        labeledPairs.add(pair);
        return `INR ${t.amount.toLocaleString("en-IN")}${t.status === "completed" ? "" : ` · ${t.status}`}`;
      }
      cy.add([
        ...nodes.map((id) => ({
          data: { id, label: id.split("-").at(-1) },
          classes: `${suspicious.includes(id) ? "risk" : ""} ${endpoints.has(id) ? "endpoint" : ""}`,
        })),
        ...transactions.map((t) => ({
          data: {
            id: t.transaction_id,
            source: t.source_account,
            target: t.destination_account,
            label: edgeLabel(t),
          },
          classes: `${t.transaction_id === selected ? "selected" : ""} ${t.status !== "completed" ? "cancelled" : ""}`,
        })),
      ]);
      cy.layout({
        name: "breadthfirst",
        directed: true,
        padding: 35,
        spacingFactor: 1.2,
        animate: false,
      }).run();
    }
    return () => {
      disposed = true;
      observer?.disconnect();
      graph.current?.destroy();
      graph.current = undefined;
    };
  }, [transactions, selected, suspicious]);
  return (
    <div className="m-graph">
      <div className="m-graph-tools">
        <button
          onClick={() =>
            graph.current?.zoom((graph.current?.zoom() ?? 1) * 1.2)
          }
          aria-label="Zoom in"
        >
          +
        </button>
        <button
          onClick={() =>
            graph.current?.zoom((graph.current?.zoom() ?? 1) / 1.2)
          }
          aria-label="Zoom out"
        >
          −
        </button>
        <button onClick={() => graph.current?.fit(undefined, 35)}>
          Fit view
        </button>
      </div>
      <div
        ref={container}
        className="m-canvas"
        aria-label="Interactive money-flow graph"
      />
      {!transactions.length && (
        <div className="m-graph-empty">
          Select a payment to explore its account relationships.
        </div>
      )}
    </div>
  );
});
