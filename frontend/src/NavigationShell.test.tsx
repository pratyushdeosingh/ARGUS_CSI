// @vitest-environment jsdom
import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NavigationShell, type Page } from "./NavigationShell";

let container: HTMLDivElement;
let root: Root;
const navigate = vi.fn();
const refresh = vi.fn();
const mediaListeners = new Set<() => void>();
let desktopMatches = false;
beforeEach(async () => {
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  navigate.mockClear(); refresh.mockClear();
  desktopMatches = false; mediaListeners.clear();
  vi.stubGlobal("matchMedia", vi.fn(() => ({
    get matches() { return desktopMatches; },
    addEventListener: (_type: string, listener: () => void) => mediaListeners.add(listener),
    removeEventListener: (_type: string, listener: () => void) => mediaListeners.delete(listener),
  })));
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  function Harness() {
    const [page, setPage] = useState<Page>("Overview");
    return <><NavigationShell page={page} alertCount={3} connection="Connected" onNavigate={destination => { navigate(destination); setPage(destination); }} onRefresh={refresh} /><button id="outside">Outside control</button></>;
  }
  await act(async () => root.render(<Harness />));
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); vi.unstubAllGlobals(); });
const trigger = () => container.querySelector<HTMLButtonElement>('[aria-expanded]')!;
const mobileNav = () => container.querySelector<HTMLElement>('[aria-label="Mobile navigation"]');

describe("responsive navigation disclosure", () => {
  it("hands focus to the desktop destination when a breakpoint hides the open menu", async () => {
    await act(async () => trigger().click());
    await act(async () => (document.activeElement as HTMLElement).blur());
    expect(document.activeElement).toBe(document.body);
    await act(async () => { desktopMatches = true; mediaListeners.forEach(listener => listener()); });
    expect(mobileNav()).toBeNull();
    expect(document.activeElement).toBe(container.querySelector('.m-desktop-nav [aria-current="page"]'));
    expect(navigate).not.toHaveBeenCalled();
  });

  it("exposes all destinations, focuses the current one, selects and restores focus", async () => {
    await act(async () => trigger().click());
    expect(trigger().getAttribute("aria-expanded")).toBe("true");
    expect(mobileNav()?.querySelectorAll("button")).toHaveLength(6);
    expect(document.activeElement?.getAttribute("aria-current")).toBe("page");
    const lab = Array.from(mobileNav()!.querySelectorAll("button")).find(button => button.textContent === "Lab")!;
    await act(async () => lab.click());
    expect(navigate).toHaveBeenCalledExactlyOnceWith("Lab");
    expect(mobileNav()).toBeNull();
    expect(document.activeElement).toBe(trigger());
    expect(trigger().getAttribute("aria-expanded")).toBe("false");
    expect(container.querySelector('.m-desktop-nav [aria-current="page"]')?.textContent).toBe("Lab");
  });
  it("dismisses on Escape and outside interaction without activating a destination", async () => {
    await act(async () => trigger().click());
    await act(async () => document.activeElement?.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
    expect(mobileNav()).toBeNull();
    expect(document.activeElement).toBe(trigger());
    await act(async () => trigger().click());
    await act(async () => container.querySelector('#outside')!.dispatchEvent(new Event("pointerdown", { bubbles: true })));
    expect(mobileNav()).toBeNull();
    expect(navigate).not.toHaveBeenCalled();
  });
  it("allows focus to leave the nonmodal navigation and keeps effects/refresh separate from navigation", async () => {
    await act(async () => trigger().click());
    await act(async () => container.querySelector<HTMLButtonElement>('#outside')!.focus());
    expect(mobileNav()).toBeNull();
    expect(document.activeElement?.id).toBe("outside");
    const effects = container.querySelector<HTMLButtonElement>('[aria-label="Reduce transparency"]')!;
    await act(async () => effects.click());
    expect(effects.getAttribute("aria-pressed")).toBe("true");
    expect(container.querySelector('header')?.dataset.opaque).toBe("true");
    await act(async () => container.querySelector<HTMLButtonElement>('[aria-label="Refresh detector health"]')!.click());
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(navigate).not.toHaveBeenCalled();
  });
});
