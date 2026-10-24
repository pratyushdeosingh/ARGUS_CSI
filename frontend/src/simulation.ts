import type { Transaction } from "./types";

export const SCENARIOS = [
  {
    id: "normal",
    name: "Normal financial activity",
    description:
      "Customer spending, merchant settlements, salaries, refunds and peer transfers.",
    expected:
      "Mostly clean controls. Large legitimate payments can still trigger a false positive.",
  },
  {
    id: "mule",
    name: "Mule account network",
    description:
      "Connected incoming funds forwarded through three intermediaries with a diminishing balance.",
    expected:
      "Rapid forwarding and multi-hop paths; detector results may vary with context.",
  },
  {
    id: "takeover",
    name: "Account takeover",
    description:
      "An established sender changes device and IP, then pays new beneficiaries at higher values.",
    expected:
      "Device change and beneficiary novelty. The detector may need more baseline history.",
  },
  {
    id: "fanout",
    name: "Scam fan-out",
    description:
      "A single source rapidly transfers to unfamiliar recipients in a coordinated burst.",
    expected: "High out-degree and repeated outgoing transfers.",
  },
  {
    id: "velocity",
    name: "High-velocity burst",
    description:
      "Repeated transfers from one account within seconds, alongside regular customer payments.",
    expected: "Short inter-arrival times and transfer frequency.",
  },
  {
    id: "mixed",
    name: "Mixed activity",
    description:
      "Everyday payments interleaved with mule paths, takeover, fan-out and velocity patterns.",
    expected:
      "A mixture of clean controls and suspicious patterns; no guaranteed verdict.",
  },
  {
    id: "random",
    name: "Randomized demo",
    description:
      "A seeded combination of connected patterns and legitimate payments.",
    expected:
      "Replay the same seed and start time to reproduce the exact financial sequence.",
  },
] as const;
export type ScenarioId = (typeof SCENARIOS)[number]["id"];
export interface SyntheticRecord {
  transaction: Transaction;
  truth: "legitimate" | "suspicious pattern";
  category: string;
}
export interface RunConfig {
  session: string;
  seed: number;
  scenario: ScenarioId;
  start: string;
  count: number;
  accounts: number;
}
export function random(seed: number) {
  let a = seed | 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
export function generateRun(config: RunConfig): SyntheticRecord[] {
  const rng = random(config.seed);
  const result: SyntheticRecord[] = [];
  const account = (n: number) =>
    `${config.session}-A${String(n).padStart(3, "0")}`;
  const accounts = Math.max(40, Math.min(400, config.accounts));
  const count = Math.max(1, Math.min(5000, config.count));
  const randomPatterns = Array.from(
    { length: Math.ceil(count / 20) },
    () =>
      ["mule", "takeover", "fanout", "velocity", "normal"][
        Math.floor(rng() * 5)
      ],
  );
  for (let i = 0; i < count; i++) {
    const block = Math.floor(i / 20);
    const step = i % 20;
    const kind =
      config.scenario === "random"
        ? randomPatterns[block]
        : config.scenario === "mixed"
          ? ["mule", "takeover", "fanout", "velocity"][block % 4]
          : config.scenario;
    // Each block has clean baseline followed by one connected pattern.
    const suspicious = kind !== "normal" && step >= 12;
    let source = 10 + Math.floor(rng() * (accounts - 10));
    let destination = 10 + Math.floor(rng() * (accounts - 10));
    if (source === destination)
      destination = 10 + ((destination - 9) % (accounts - 10));
    let category =
      i > 0 && i % 97 === 0
        ? "Salary"
        : i > 0 && i % 149 === 0
          ? "Large-value transfer"
          : [
              "Merchant payment",
              "Peer transfer",
              "Refund",
              "Customer spending",
            ][i % 4];
    if (category === "Merchant payment" || category === "Customer spending")
      destination = 6 + (i % 4);
    if (category === "Salary") source = 9;
    if (category === "Refund") source = 8;
    if (category === "Peer transfer")
      destination = 10 + ((source - 10 + 3) % (accounts - 10));
    let amount =
      Math.round(
        (category === "Salary"
          ? 25000 + rng() * 90000
          : category === "Large-value transfer"
            ? 100000 + rng() * 300000
            : 200 + rng() * 1600) * 100,
      ) / 100;
    if (suspicious) {
      category = `${kind} pattern`;
      if (kind === "mule") {
        const hop = (step - 12) % 4;
        source = hop;
        destination = hop + 1;
        amount = 180000 - hop * 4500;
      } else {
        source = kind === "takeover" ? 10 : 5;
        destination = 20 + step;
        amount =
          kind === "takeover"
            ? 275000 + (step - 12) * 10000
            : kind === "fanout"
              ? 48000
              : 9500;
      }
    }
    // Legitimate takeover baseline belongs to the same source and known device.
    if (kind === "takeover" && !suspicious) source = 10;
    result.push({
      truth: suspicious ? "suspicious pattern" : "legitimate",
      category,
      transaction: {
        transaction_id: `${config.session}-${String(i + 1).padStart(5, "0")}`,
        timestamp: new Date(
          Date.parse(config.start) + (config.scenario === "normal" ? i * 180000 : block * 60000 + step * 1000),
        ).toISOString(),
        source_account: account(source),
        destination_account: account(destination),
        amount,
        currency: "INR",
        device_id:
          suspicious && kind === "takeover"
            ? "SYN-NEW-DEVICE"
            : `SYN-DEVICE-${source}`,
        ip_address:
          suspicious && kind === "takeover"
            ? "198.51.100.199"
            : `192.0.2.${(source % 200) + 1}`,
        status: suspicious
          ? "completed"
          : i % 19 === 0
            ? "pending"
            : i % 23 === 0
              ? "cancelled"
              : "completed",
      },
    });
  }
  return result;
}
export const DATA_SOURCES = {
  synthetic: { label: "Synthetic Data", available: true },
  real: { label: "Real Data — Not Connected", available: false },
} as const;
