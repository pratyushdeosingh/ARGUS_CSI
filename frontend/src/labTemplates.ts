import type { AnalysisRequest, RawTelemetryEvent, Transaction } from "./types";

export interface LabTemplate {
  label: string;
  description: string;
  request: AnalysisRequest;
}

const transaction = (
  transaction_id: string,
  timestamp: string,
  source_account: string,
  destination_account: string,
  amount: number,
  device_id: string,
  ip_address: string,
): Transaction => ({
  transaction_id,
  timestamp,
  source_account,
  destination_account,
  amount,
  currency: "INR",
  device_id,
  ip_address,
  status: "completed",
});

const telemetry = (
  timestamp: string,
  event_type: RawTelemetryEvent["event_type"],
  process: string,
  details: Record<string, unknown>,
): RawTelemetryEvent => ({ timestamp, event_type, process, details });

export const LAB_TEMPLATES: Record<string, LabTemplate> = {
  adaptive_ato: {
    label: "Adaptive account takeover",
    description: "Train on APEX-741 history, then detect a new identity and rapid three-hop drain.",
    request: {
      source_label: "adaptive-ato-lab",
      telemetry_host: "payout-node-west",
      telemetry_service: "instant-payouts",
      baseline_transactions: [
        transaction("BASE-741-01", "2026-08-20T08:00:00Z", "APEX-741", "MERCHANT-GROCER", 1400, "APEX-PHONE-1", "203.0.113.41"),
        transaction("BASE-741-02", "2026-08-21T08:30:00Z", "APEX-741", "UTILITY-ELECTRIC", 2300, "APEX-PHONE-1", "203.0.113.41"),
        transaction("BASE-741-03", "2026-08-22T09:15:00Z", "APEX-741", "MERCHANT-PHARMACY", 900, "APEX-PHONE-1", "203.0.113.41"),
      ],
      transactions: [
        transaction("LIVE-ATO-01", "2026-08-24T10:30:00Z", "APEX-741", "RELAY-8F", 125000, "UNKNOWN-BROWSER-88", "45.77.12.9"),
        transaction("LIVE-ATO-02", "2026-08-24T10:30:35Z", "RELAY-8F", "RELAY-2K", 121500, "RELAY-DEVICE-8F", "198.51.100.81"),
        transaction("LIVE-ATO-03", "2026-08-24T10:31:10Z", "RELAY-2K", "VAULT-77", 118000, "RELAY-DEVICE-2K", "198.51.100.82"),
      ],
      telemetry_events: [
        telemetry("2026-08-24T10:30:50Z", "process_exec", "payout-worker", { unexpected_child: true, child: "/bin/sh" }),
        telemetry("2026-08-24T10:30:54Z", "file_open", "payout-worker", { path: "/opt/argus-lab/fake-sensitive-config.json" }),
        telemetry("2026-08-24T10:31:18Z", "network_connect", "payout-worker", { destination_ip: "45.77.12.9", suspicious_destination: true }),
      ],
    },
  },
  fanout: {
    label: "Structuring fan-out",
    description: "Detect a business account dispersing funds to four new beneficiaries plus host execution risk.",
    request: {
      source_label: "fanout-structuring-lab",
      telemetry_host: "settlement-node-3",
      telemetry_service: "merchant-settlement",
      baseline_transactions: [
        transaction("BASE-BIZ-01", "2026-08-20T12:00:00Z", "BIZ-204", "SUPPLIER-A", 5200, "BIZ-LAPTOP-2", "203.0.113.90"),
        transaction("BASE-BIZ-02", "2026-08-21T12:00:00Z", "BIZ-204", "PAYROLL-POOL", 6800, "BIZ-LAPTOP-2", "203.0.113.90"),
      ],
      transactions: [
        transaction("FAN-001", "2026-08-24T11:00:00Z", "BIZ-204", "DROP-A", 14800, "BIZ-LAPTOP-2", "91.214.124.17"),
        transaction("FAN-002", "2026-08-24T11:00:25Z", "BIZ-204", "DROP-B", 14600, "BIZ-LAPTOP-2", "91.214.124.17"),
        transaction("FAN-003", "2026-08-24T11:00:50Z", "BIZ-204", "DROP-C", 14400, "BIZ-LAPTOP-2", "91.214.124.17"),
        transaction("FAN-004", "2026-08-24T11:01:15Z", "BIZ-204", "DROP-D", 14200, "BIZ-LAPTOP-2", "91.214.124.17"),
      ],
      telemetry_events: [
        telemetry("2026-08-24T11:00:40Z", "process_exec", "settlement-worker", { unexpected_child: true }),
        telemetry("2026-08-24T11:01:18Z", "network_connect", "settlement-worker", { destination_ip: "91.214.124.17", suspicious_destination: true }),
      ],
    },
  },
  clean: {
    label: "Clean control batch",
    description: "A known device, known beneficiary, ordinary amount, and benign host telemetry.",
    request: {
      source_label: "clean-control-lab",
      telemetry_host: "payments-node-green",
      telemetry_service: "scheduled-payments",
      baseline_transactions: [
        transaction("BASE-CLEAN-01", "2026-08-20T07:00:00Z", "FAMILY-55", "RENT-AGENCY", 18000, "FAMILY-PHONE", "203.0.113.155"),
        transaction("BASE-CLEAN-02", "2026-08-21T07:00:00Z", "FAMILY-55", "GROCERY-STORE", 2400, "FAMILY-PHONE", "203.0.113.155"),
      ],
      transactions: [
        transaction("CLEAN-001", "2026-08-24T07:00:00Z", "FAMILY-55", "GROCERY-STORE", 2600, "FAMILY-PHONE", "203.0.113.155"),
      ],
      telemetry_events: [
        telemetry("2026-08-24T07:00:02Z", "process_exec", "scheduled-worker", { unexpected_child: false }),
        telemetry("2026-08-24T07:00:04Z", "network_connect", "scheduled-worker", { destination_ip: "192.0.2.20", suspicious_destination: false }),
      ],
    },
  },
};
