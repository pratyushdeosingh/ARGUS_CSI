# Fintech demo walkthrough

Use synthetic data and say which interface is being demonstrated. The core batch/stream assessment and React financial case workflow now share
financial.v1. Live React event subscription and the legacy specialist demo are
still separate. Do not describe them as one completed financial investigation flow.

## 1. Show the implemented financial analysis

1. Start the stack using the README. Open the React dashboard and Data Lab.
2. Run a clean control, then an account-takeover or fan-out batch.
3. Inspect account connections, suspicious transactions, score and rule evidence.
4. Leave optional infrastructure evidence unchecked. Show the detector
   breakdown and resulting financial-only case; a clean control stays below
   the case threshold.
5. Open INVESTIGATE, assign an analyst, select investigating and save a note.
6. Show the revision and DOWNLOAD DRAFT JSON. Explain that it is not a filing.
7. Close the dialogs, approve simulated containment and verify the action audit.

## 2. Show payment streaming

1. Run `python scripts/watch_transactions.py` in a separate terminal.
2. Replay `data/generated/normal.json` using a fresh `--run-id`.
3. Replay `data/generated/mule.json` with another fresh `--run-id`.
4. Inspect received/scored events and the mule alert. The score describes the
   rolling session window; it is not a calibrated payment fraud probability.
5. State that React live updates and durable event replay/retry are next work.
   Qualifying financial cases and their assessments are already persistent. The watcher displays the stream today.

Full commands are in the README and `scripts/README.md`.

## 3. Show specialist mule/scam scoring

1. Open `http://127.0.0.1:8001/demo` (its graph library requires CDN access).
2. Compare normal, mule-account, scam fan-out and burst scenarios.
3. Inspect rules/TGNN/mule/scam breakdown and reasons.
4. Explain that this score uses a separate 0–100 experimental fusion and
   in-memory history. BLOCK is a recommendation; no bank action occurs.
5. State that the TGNN was trained on synthetic canonical batches. There are
   no held-out accuracy, SHAP or production-readiness claims.

## 4. Optional existing cross-domain workflow

Use the React canonical demo to show infrastructure replay, correlation,
analyst-approved simulated containment and stored action audit. Replaying a
contained case does not reopen it; the reset button clears display state, not
persistent cases. Use a separate demo database for a fresh approval walkthrough.

## Close with the next work

Show `TODO.md`: unified scoring, financial-only cases, live React updates,
recoverable scoring/alerts, independent ML evaluation and compliance workflow.
Show the CI result and verification report as engineering evidence, rather
than representing passing synthetic tests as proof of real-world accuracy.
