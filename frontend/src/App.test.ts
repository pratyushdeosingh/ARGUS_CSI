import { describe, expect, it } from "vitest";

import { detectorSourceLabel } from "./App";
import type { DetectorComponentStatus } from "./types";

function status(
  overrides: Partial<DetectorComponentStatus>,
): DetectorComponentStatus {
  return {
    availability: "online",
    origin: "service",
    mode: "unknown",
    detail: "test",
    ...overrides,
  };
}

describe("detectorSourceLabel", () => {
  it("shows live and replay service modes", () => {
    expect(detectorSourceLabel(status({ mode: "live" }))).toBe("LIVE SERVICE");
    expect(detectorSourceLabel(status({ mode: "replay" }))).toBe("REPLAY SERVICE");
  });

  it("does not present fallbacks as live services", () => {
    expect(detectorSourceLabel(status({ availability: "degraded", origin: "last_known" }))).toBe("LAST KNOWN");
    expect(detectorSourceLabel(status({ availability: "offline", origin: "fixture", mode: "fixture" }))).toBe("FIXTURE");
    expect(detectorSourceLabel(status({ availability: "offline", origin: "none" }))).toBe("UNAVAILABLE");
  });
});
