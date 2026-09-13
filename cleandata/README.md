# CleanData

Upload a messy CSV, get back a cleaned file plus a full audit trail of every
change that was made to it — column by column, with a plain-English reason
for each decision.

```
core/       the cleaning engine (Python library + CLI, usable standalone)
backend/    FastAPI service that wraps the engine for the web app
frontend/   the web UI (Vite + React)
```

## Run it

**1. Backend** — run these from the project root (not from inside `backend/`):

```bash
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows (PowerShell):
.venv\Scripts\Activate.ps1

pip install -e core
pip install -r backend/requirements.txt
uvicorn app.main:app --app-dir backend --reload --port 8000
```

`core` is installed as its own step deliberately — a relative editable
path (`-e ../core`) inside `requirements.txt` resolves against your
*current directory*, not the file's location, so running pip from a
different folder than intended silently breaks it. Installing `core`
explicitly sidesteps that.

**2. Frontend** (separate terminal)

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`, drop in a CSV, and review the result.

## Using just the engine

The cleaning engine has no dependency on the web app and works standalone:

```bash
cd core
pip install -e .
clean-data path/to/input.csv path/to/output.csv path/to/report.json
```

See [`core/README.md`](core/README.md) for the full rule set, design
rationale, and known limitations of the cleaning logic.

## What's cleaned

Column naming, whitespace, blank cells, numbers/dates stored as text,
missing values (imputed or left null depending on what's statistically
defensible), inconsistent capitalization, statistical outliers, and
duplicate rows. See `core/README.md` for the full table and the reasoning
behind each rule.

## Status / roadmap

This is an actively developed tool. Near-term additions: Excel/JSON input,
a configurable rule set (thresholds, per-column overrides), selective
accept/reject of individual actions, and an undo history.

## License

MIT — see [LICENSE](core/LICENSE).
