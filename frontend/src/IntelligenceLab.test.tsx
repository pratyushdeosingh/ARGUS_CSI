// @vitest-environment jsdom
import { act, StrictMode, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { IntelligenceLab } from "./IntelligenceLab";
import { LAB_TEMPLATES } from "./labTemplates";
import type { AnalysisRequest, AnalysisResponse } from "./types";

let container: HTMLDivElement;
let root: Root;
let previousOverflow: string;
beforeEach(() => {
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement("div"); document.body.append(container); root = createRoot(container);
  previousOverflow = document.body.style.overflow;
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); document.body.style.overflow = previousOverflow; });
const analyze = vi.fn<(request: AnalysisRequest) => Promise<AnalysisResponse>>();
function Harness({ removeOpener = false, onAnalyze = analyze }: { removeOpener?: boolean; onAnalyze?: typeof analyze }) {
  const [open, setOpen] = useState(false);
  return <div className="m-app m-experience">
    <main>{!removeOpener && <button id="opener" onClick={() => setOpen(true)}>Open lab</button>}<button data-lab-launcher id="fallback" onClick={() => setOpen(true)}>Lab launcher</button><button id="outside">Outside</button></main>
    <aside inert id="already-inert">Previously inert</aside>
    <IntelligenceLab open={open} incidents={[]} onClose={() => setOpen(false)} onAnalyze={onAnalyze} />
  </div>;
}
const close = () => container.querySelector<HTMLButtonElement>('[aria-label="Close intelligence lab"]')!;
const run = () => container.querySelector<HTMLButtonElement>('.lab-run-button')!;
const key = async (target: Element, value: string, shiftKey = false) => act(async () => target.dispatchEvent(new KeyboardEvent("keydown", { key: value, shiftKey, bubbles: true, cancelable: true })));
const open = async () => act(async () => { const button = container.querySelector<HTMLButtonElement>('#opener')!; button.focus(); button.click(); });

it("traps both Tab boundaries, blocks background focus, closes on Escape and restores the opener and inert/scroll state", async () => {
  document.body.style.overflow = "scroll";
  await act(async () => root.render(<StrictMode><Harness /></StrictMode>));
  await open();
  expect(document.activeElement).toBe(close());
  expect(container.querySelector('main')?.hasAttribute('inert')).toBe(true);
  expect(document.body.style.overflow).toBe("hidden");
  expect(container.querySelector('[role="dialog"]')?.getAttribute('aria-describedby')).toBeTruthy();
  await key(close(), "Tab", true);
  expect(document.activeElement).toBe(run());
  await key(run(), "Tab");
  expect(document.activeElement).toBe(close());
  await act(async () => container.querySelector<HTMLButtonElement>('#outside')!.focus());
  expect(document.activeElement).toBe(close());
  const input = container.querySelector('textarea')!;
  await act(async () => input.focus());
  await key(input, "Escape");
  expect(container.querySelector('[role="dialog"]')).toBeNull();
  expect(document.activeElement?.id).toBe("opener");
  expect(container.querySelector('main')?.hasAttribute('inert')).toBe(false);
  expect(container.querySelector('#already-inert')?.hasAttribute('inert')).toBe(true);
  expect(document.body.style.overflow).toBe("scroll");
});

it("preserves editing focus across parent renders and restores an available launcher if the original opener disappears", async () => {
  await act(async () => root.render(<Harness />)); await open();
  const input = container.querySelector<HTMLInputElement>('.lab-meta-grid input')!;
  await act(async () => input.focus());
  await act(async () => root.render(<Harness removeOpener />));
  expect(document.activeElement).toBe(input);
  await act(async () => close().click());
  expect(document.activeElement?.id).toBe("fallback");
});

it("restores the launcher when responsive layout hides the opener's navigation", async () => {
  await act(async () => root.render(<Harness />));
  const opener = container.querySelector<HTMLButtonElement>('#opener')!;
  const navigation = document.createElement('nav');
  opener.before(navigation); navigation.append(opener);
  await open();
  navigation.style.display = 'none';
  await key(close(), "Escape");
  expect(document.activeElement?.id).toBe("fallback");
});

it("keeps a nested Canonical Lab interactive while making only its background siblings inert", async () => {
  function Nested() {
    const [shown, setShown] = useState(false);
    return <div className="m-app"><header id="background-header">Navigation</header><main><div className="m-legacy"><button id="opener" onClick={() => setShown(true)}>Data Lab</button><IntelligenceLab open={shown} incidents={[]} onClose={() => setShown(false)} onAnalyze={analyze} /></div></main></div>;
  }
  await act(async () => root.render(<Nested />)); await open();
  expect(container.querySelector('#background-header')?.hasAttribute('inert')).toBe(true);
  expect(container.querySelector('[role="dialog"]')?.closest('[inert]')).toBeNull();
  await key(close(), "Escape");
  expect(container.querySelector('#background-header')?.hasAttribute('inert')).toBe(false);
  expect(document.activeElement?.id).toBe("opener");
});

it("announces validation, keeps the original request payload and displays returned analysis without fabricating results", async () => {
  let complete!: (response: AnalysisResponse) => void;
  const onAnalyze = vi.fn<(request: AnalysisRequest) => Promise<AnalysisResponse>>(() => new Promise(resolve => { complete = resolve; }));
  await act(async () => root.render(<Harness onAnalyze={onAnalyze} />)); await open();
  const textarea = container.querySelector('textarea')!;
  const setText = async (value: string) => act(async () => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')!.set!.call(textarea, value);
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await setText('{'); await act(async () => run().click());
  expect(container.querySelector('[role="alert"]')?.textContent).toContain('Transactions is not valid JSON.');
  expect(onAnalyze).not.toHaveBeenCalled();
  const select = container.querySelector('select')!;
  await act(async () => { select.value = 'clean'; select.dispatchEvent(new Event('change', { bubbles: true })); });
  await act(async () => run().click());
  expect(onAnalyze).toHaveBeenCalledExactlyOnceWith(LAB_TEMPLATES.clean.request);
  expect(run().disabled).toBe(true);
  expect(container.querySelector('.lab-content')?.getAttribute('aria-busy')).toBe('true');
  const component = { availability: 'online' as const, origin: 'service' as const, mode: 'live' as const, detail: 'test' };
  await act(async () => complete({ analysis_id: 'ANALYSIS-test', mode: 'analysis', source_label: 'clean-control-lab', transactions: LAB_TEMPLATES.clean.request.transactions,
    graph_signal: { signal_id: 'GRAPH-test', source: 'graph_detector', timestamp: '2026-10-25T00:00:00Z', risk_score: .17, anomaly_type: 'test_result', suspicious_accounts: [], suspicious_transactions: [], related_ips: [], reasons: ['Returned test evidence'] },
    system_signal: null, detector_status: { graph: component, system: component }, incident: null }));
  expect(container.querySelector('[role="status"]')?.textContent).toContain('ANALYSIS-test');
  expect(container.querySelector('[role="status"]')?.textContent).toContain('Returned test evidence');
  expect(container.querySelector('.result-score-grid strong')?.textContent).toBe('17');
  expect(run().disabled).toBe(false);
  expect(container.querySelector('.lab-content')?.getAttribute('aria-busy')).toBe('false');
});
