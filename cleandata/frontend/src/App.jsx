import { useState } from "react";
import StepRail from "./components/StepRail.jsx";
import Dropzone from "./components/Dropzone.jsx";
import ProfileList from "./components/ProfileList.jsx";
import DataTable from "./components/DataTable.jsx";
import ActionLog from "./components/ActionLog.jsx";

export default function App() {
  const [status, setStatus] = useState("idle"); // idle | loading | done | error
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  async function handleFile(file) {
    setStatus("loading");
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch("/api/process", { method: "POST", body: form });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Upload failed (${res.status})`);
      }
      const data = await res.json();
      setResult(data);
      setStatus("done");
    } catch (err) {
      setError(err.message || "Something went wrong.");
      setStatus("error");
    }
  }

  function reset() {
    setResult(null);
    setStatus("idle");
    setError(null);
  }

  const stepIndex = status === "done" ? 3 : status === "loading" ? 1 : 0;

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <h1>
            CleanData
            <span className="badge">runs locally</span>
          </h1>
          <p className="tagline">Upload a table, review every change, export the result.</p>
        </div>
        {status === "done" && (
          <button className="btn" onClick={reset}>
            Start over
          </button>
        )}
      </header>

      <StepRail currentIndex={stepIndex} />

      {error && <div className="error-banner">{error}</div>}

      {status !== "done" && (
        <Dropzone onFile={handleFile} disabled={status === "loading"} />
      )}

      {status === "loading" && (
        <p className="loading-line" style={{ marginTop: 16 }}>
          Profiling columns, applying rules, building the report…
        </p>
      )}

      {status === "done" && result && <Results result={result} />}
    </div>
  );
}

function Results({ result }) {
  const { session_id, filename, summary, actions, profile_before, diff, preview_after } = result;

  return (
    <>
      <div className="stat-row">
        <div className="stat">
          <span className="value">
            {summary.rows_before}
            <span className="arrow">→</span>
            {summary.rows_after}
          </span>
          <span className="label">rows</span>
        </div>
        <div className="stat">
          <span className="value">
            {summary.cols_before}
            <span className="arrow">→</span>
            {summary.cols_after}
          </span>
          <span className="label">columns</span>
        </div>
        <div className="stat">
          <span className="value">{summary.total_actions}</span>
          <span className="label">actions taken</span>
        </div>
      </div>

      <div className="panel">
        <div className="panel-header">
          <h2>Column profile — before cleaning</h2>
          <span className="meta">{filename}</span>
        </div>
        <div className="panel-body">
          <ProfileList columns={profile_before} />
        </div>
      </div>

      <div className="panel">
        <div className="panel-header">
          <h2>What changed</h2>
          <span className="meta">{diff.changed_columns.length} columns touched</span>
        </div>
        <div className="panel-body">
          <DataTable rows={preview_after} changedColumns={diff.changed_columns} />
        </div>
      </div>

      <div className="panel">
        <div className="panel-header">
          <h2>Action log</h2>
        </div>
        <div className="panel-body">
          <ActionLog actions={actions} />
        </div>
      </div>

      <div className="btn-row">
        <a className="btn btn-primary" href={`/api/download/${session_id}/cleaned.csv`}>
          Download cleaned CSV
        </a>
        <a className="btn" href={`/api/download/${session_id}/report.html`} target="_blank" rel="noreferrer">
          View full report
        </a>
        <a className="btn" href={`/api/download/${session_id}/report.json`}>
          Download report (JSON)
        </a>
      </div>
    </>
  );
}
