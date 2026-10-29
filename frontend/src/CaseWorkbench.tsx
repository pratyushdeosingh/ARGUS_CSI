import { useEffect, useRef, useState } from "react";
import { loadDraftReport, loadInvestigation, updateInvestigation } from "./api";
import type { Investigation } from "./types";

export function CaseWorkbench({ incidentId, onClose }: { incidentId: string; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { dialog.current?.showModal(); }, []);
  const [investigation, setInvestigation] = useState<Investigation | null>(null);
  const [actor, setActor] = useState("human-analyst");
  const [assignee, setAssignee] = useState("");
  const [status, setStatus] = useState<Investigation["status"]>("open");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    let active = true;
    setInvestigation(null);
    setError(null);
    void loadInvestigation(incidentId).then(value => {
      if (active) {
        setInvestigation(value); setAssignee(value.assigned_to ?? ""); setStatus(value.status); setNote("");
      }
    }).catch(reason => { if (active) setError(String(reason)); });
    return () => { active = false; };
  }, [incidentId, reload]);

  const save = async () => {
    if (!investigation) return;
    setBusy(true); setError(null);
    try {
      const updated = await updateInvestigation(incidentId, {
        actor, expected_revision: investigation.revision, assigned_to: assignee.trim() || null,
        status, ...(note.trim() ? { note: note.trim() } : {}),
      });
      setInvestigation(updated); setNote("");
    } catch (reason) { setError(String(reason)); }
    finally { setBusy(false); }
  };
  const download = async () => {
    setBusy(true); setError(null);
    try {
      const draft = await loadDraftReport(incidentId);
      const url = URL.createObjectURL(new Blob([JSON.stringify(draft, null, 2)], { type: "application/json" }));
      const anchor = document.createElement("a"); anchor.href = url; anchor.download = `${incidentId}-DRAFT.json`;
      anchor.click(); URL.revokeObjectURL(url);
    } catch (reason) { setError(String(reason)); }
    finally { setBusy(false); }
  };
  return <dialog ref={dialog} className="case-workbench" aria-label="Case investigation" onCancel={onClose}>
    <button onClick={onClose}>CLOSE INVESTIGATION</button>
    <h3>Investigate {incidentId}</h3>
    <p>Prototype identities are caller supplied. Report exports are drafts, never regulatory filings.</p>
    {error && <p role="alert">{error} Reload the case if another analyst changed it.</p>}
    <button disabled={busy} onClick={() => setReload(value => value + 1)}>RELOAD CASE</button>
    {investigation ? <>
      <small>Revision {investigation.revision}</small>
      <label>Analyst identity<input value={actor} maxLength={100} onChange={event => setActor(event.target.value)} /></label>
      <label>Assigned to<input value={assignee} maxLength={100} onChange={event => setAssignee(event.target.value)} /></label>
      <label>Investigation status<select value={status} onChange={event => setStatus(event.target.value as Investigation["status"])}>
        {["open", "investigating", "escalated", "closed"].map(value => <option key={value}>{value}</option>)}
      </select></label>
      <label>Investigation note<textarea value={note} maxLength={4000} onChange={event => setNote(event.target.value)} /></label>
      <button onClick={() => void save()} disabled={busy || !actor.trim()}>SAVE INVESTIGATION</button>
      <button onClick={() => void download()} disabled={busy}>DOWNLOAD DRAFT JSON</button>
      <ol>{investigation.history.map(event => <li key={event.id}>
        <strong>{event.actor}</strong> · revision {event.revision} · {event.timestamp}
        <pre>{JSON.stringify(event.changes, null, 2)}</pre>
      </li>)}</ol>
    </> : <p>{error ? "Case could not be loaded. Reload to try again." : "Loading investigation…"}</p>}
  </dialog>;
}
