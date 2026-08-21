import { afterEach, describe, expect, it, vi } from "vitest";

import { loadDetectorStatus, simulateAttack } from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ARGUS API client", () => {
  it("loads detector provenance metadata", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      graph: { availability: "offline", origin: "fixture", mode: "fixture", detail: "offline demo" },
      system: { availability: "online", origin: "service", mode: "replay", detail: "replay ready" },
    }), { status: 200 })));

    const result = await loadDetectorStatus();

    expect(result.graph.origin).toBe("fixture");
    expect(result.system.mode).toBe("replay");
  });

  it("surfaces FastAPI error details", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: "Graph detector unavailable" }),
      { status: 503 },
    )));

    await expect(simulateAttack()).rejects.toThrow("Graph detector unavailable");
  });
});
