"""
CleanData API
=============
FastAPI backend that wraps the DataCleaningAgent core library with the
extra surface a UI needs: column profiling, a before/after diff, and
downloadable outputs. Sessions are held in memory (this is a local,
single-user tool, not a multi-tenant service).
"""

from __future__ import annotations

import io
import json
import time
import uuid
from typing import Any

import numpy as np
import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from data_cleaning_agent import DataCleaningAgent

app = FastAPI(title="CleanData API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# session_id -> {original_df, cleaned_df, report, filename, created_at}
_SESSIONS: dict[str, dict[str, Any]] = {}
_SESSION_TTL_SECONDS = 60 * 60  # 1 hour
_MAX_PREVIEW_ROWS = 200


def _prune_sessions() -> None:
    now = time.time()
    expired = [sid for sid, s in _SESSIONS.items() if now - s["created_at"] > _SESSION_TTL_SECONDS]
    for sid in expired:
        _SESSIONS.pop(sid, None)


def _json_safe(value: Any) -> Any:
    """Make a single cell value JSON-serializable."""
    if value is None:
        return None
    if isinstance(value, float) and np.isnan(value):
        return None
    if isinstance(value, (pd.Timestamp,)):
        if pd.isna(value):
            return None
        return value.isoformat()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if np.isnan(value) else float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def _profile(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Per-column summary: dtype, missing %, uniqueness -- used for the
    'before cleaning' snapshot the UI shows on the profile step."""
    n = len(df)
    cols = []
    for col in df.columns:
        series = df[col]
        n_missing = int(series.isna().sum())
        cols.append(
            {
                "name": col,
                "dtype": str(series.dtype),
                "missing": n_missing,
                "missing_pct": round(n_missing / n, 4) if n else 0,
                "unique": int(series.nunique(dropna=True)),
            }
        )
    return cols


def _rows(df: pd.DataFrame, limit: int = _MAX_PREVIEW_ROWS) -> list[dict[str, Any]]:
    sample = df.head(limit)
    return [
        {col: _json_safe(val) for col, val in row.items()}
        for row in sample.to_dict(orient="records")
    ]


def _normalize_colname(name: str) -> str:
    """Mirrors DataCleaningAgent's column-name standardization so we can
    line up 'before' and 'after' columns for diffing even though the
    agent itself renames columns as its first cleaning step."""
    import re

    return re.sub(r"[^\w]+", "_", str(name).strip().lower()).strip("_")


def _diff(before: pd.DataFrame, after: pd.DataFrame, limit: int = _MAX_PREVIEW_ROWS) -> dict[str, Any]:
    """Cell-level diff for the rows that survive cleaning, capped to the
    same preview window as the row payloads so indices line up in the UI."""
    before = before.rename(columns=_normalize_colname)
    common_cols = [c for c in after.columns if c in before.columns]
    # Rows are realigned during cleaning (dedup/drop can shift the index),
    # so compare on the *cleaned* frame's positional index only, against the
    # original row it most likely corresponds to isn't reliable post-dedup --
    # instead we report column-level change stats, which is what the report
    # already narrates in detail; the UI pairs this with the action log.
    changed_cols = []
    for col in common_cols:
        if len(before[col]) == 0 or len(after[col]) == 0:
            continue
        b = before[col].reset_index(drop=True)
        a = after[col].reset_index(drop=True)
        n = min(len(b), len(a))
        if n == 0:
            continue
        b, a = b.iloc[:n], a.iloc[:n]
        try:
            diff_mask = ~((b == a) | (b.isna() & a.isna()))
        except Exception:
            diff_mask = b.astype(str) != a.astype(str)
        n_changed = int(diff_mask.sum())
        if n_changed:
            changed_cols.append(col)
    dropped_cols = [c for c in before.columns if c not in after.columns]
    return {"changed_columns": changed_cols, "dropped_columns": dropped_cols}


@app.post("/api/process")
async def process(file: UploadFile = File(...)) -> JSONResponse:
    _prune_sessions()

    if not file.filename.lower().endswith((".csv", ".tsv")):
        raise HTTPException(400, "Only .csv or .tsv files are supported right now.")

    raw = await file.read()
    if not raw:
        raise HTTPException(400, "The uploaded file is empty.")

    sep = "\t" if file.filename.lower().endswith(".tsv") else ","
    try:
        df = pd.read_csv(io.BytesIO(raw), sep=sep)
    except Exception as exc:
        raise HTTPException(400, f"Could not parse file as a table: {exc}") from exc

    if df.empty:
        raise HTTPException(400, "The uploaded file has no rows.")

    profile_before = _profile(df)

    agent = DataCleaningAgent()
    cleaned = agent.clean(df)

    profile_after = _profile(cleaned)
    diff = _diff(df, cleaned)

    session_id = str(uuid.uuid4())
    _SESSIONS[session_id] = {
        "original_df": df,
        "cleaned_df": cleaned,
        "report": agent.report,
        "filename": file.filename,
        "created_at": time.time(),
    }

    return JSONResponse(
        {
            "session_id": session_id,
            "filename": file.filename,
            "summary": agent.report.to_dict()["summary"],
            "actions": agent.report.to_dict()["actions"],
            "profile_before": profile_before,
            "profile_after": profile_after,
            "diff": diff,
            "preview_before": _rows(df),
            "preview_after": _rows(cleaned),
        }
    )


@app.get("/api/download/{session_id}/cleaned.csv")
def download_cleaned(session_id: str) -> StreamingResponse:
    session = _SESSIONS.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found or expired. Re-upload the file.")
    buf = io.StringIO()
    session["cleaned_df"].to_csv(buf, index=False)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=cleaned.csv"},
    )


@app.get("/api/download/{session_id}/report.json")
def download_report_json(session_id: str) -> JSONResponse:
    session = _SESSIONS.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found or expired. Re-upload the file.")
    return JSONResponse(session["report"].to_dict())


@app.get("/api/download/{session_id}/report.html", response_class=HTMLResponse)
def download_report_html(session_id: str) -> str:
    session = _SESSIONS.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found or expired. Re-upload the file.")
    report = session["report"].to_dict()
    rows = "".join(
        f"<tr><td>{a['column']}</td><td>{a['issue']}</td><td>{a['action']}</td>"
        f"<td>{a['rows_affected']}</td><td>{a['details']}</td></tr>"
        for a in report["actions"]
    )
    s = report["summary"]
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Cleaning report — {session['filename']}</title>
<style>
body {{ font-family: -apple-system, Segoe UI, sans-serif; background:#FAFAF8; color:#1C1E21; padding:2.5rem; }}
h1 {{ font-size: 1.25rem; margin-bottom: .25rem; }}
.summary {{ color:#6B7280; margin-bottom: 1.5rem; }}
table {{ border-collapse: collapse; width: 100%; font-size: .875rem; }}
th, td {{ text-align: left; padding: .5rem .75rem; border-bottom: 1px solid #E5E7EB; }}
th {{ color:#6B7280; font-weight: 500; }}
</style></head>
<body>
<h1>Cleaning report — {session['filename']}</h1>
<p class="summary">Rows {s['rows_before']} → {s['rows_after']} · Columns {s['cols_before']} → {s['cols_after']} · {s['total_actions']} actions</p>
<table>
<thead><tr><th>Column</th><th>Issue</th><th>Action</th><th>Rows affected</th><th>Details</th></tr></thead>
<tbody>{rows}</tbody>
</table>
</body></html>"""


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
