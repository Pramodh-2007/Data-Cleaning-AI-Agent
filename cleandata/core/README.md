# Data Cleaning AI Agent

A rule-driven agent that inspects a raw CSV/DataFrame, decides which cleaning
action to apply to each data-quality issue it finds, applies it, and produces
a full audit trail explaining every change — so the cleaning is auditable,
not a black box.

Runs fully offline (no API key, no LLM call required). An optional
`llm_hook` is included if you want to plug in a model later for ambiguous
free-text decisions.

## Why call it an "agent"?

It follows the classic **perceive → decide → act → report** loop:

1. **Perceive** — profiles every column: dtype, missing values, duplicate
   rows, outliers, inconsistent casing/whitespace, values stored as the
   wrong type.
2. **Decide** — a rule engine picks an action per issue (impute vs. drop,
   cast vs. leave alone, clip vs. keep an outlier), based on how severe and
   how safe-to-fix the issue is.
3. **Act** — the chosen action is applied to a working copy of the data.
4. **Report** — every action, its rationale, and the number of rows it
   touched is logged (both as plain text and as JSON).

## What it actually cleans

| Issue | Action |
|---|---|
| Inconsistent column names | Lowercased, trimmed, underscored |
| Leading/trailing whitespace | Stripped from every text field |
| Blank / whitespace-only cells | Converted to proper null values |
| Numbers stored as text (`"$1,200"`) | Cast to numeric |
| Dates stored as text, mixed formats | Cast to `datetime64` |
| Missing numeric values | Filled with the column median |
| Missing **categorical** values (low-cardinality, values repeat) | Filled with the most frequent value |
| Missing **free-text** values (names, notes — high-cardinality, no repeats) | Left as null, *not* fabricated |
| Missing dates | Left as null (imputing a date would fabricate an event) |
| Columns >60% empty | Dropped — too sparse to impute reliably |
| Inconsistent capitalization (`"usa"` / `"USA"` / `"Usa"`) | Normalized via title-casing |
| Statistical outliers (`\|z-score\| > 3`) | Clipped to the 1st–99th percentile, not deleted |
| Duplicate rows | Dropped (surrogate ID columns are auto-detected and excluded from the comparison, so two otherwise-identical rows aren't kept apart just because they have different IDs) |

A deliberate design choice: the agent **never fabricates content**. It
imputes numeric/categorical gaps where there's a statistically defensible
fill value, but leaves dates and high-cardinality free text alone rather
than inventing a plausible-looking value.

## Install

```bash
git clone https://github.com/<your-username>/data-cleaning-agent.git
cd data-cleaning-agent
pip install -e .
```

This installs `pandas`/`numpy` and gives you a `clean-data` command.

## Usage

```bash
clean-data path/to/input.csv path/to/output.csv path/to/report.json
```

or without installing:

```bash
pip install -r requirements.txt
python -m data_cleaning_agent.agent input.csv output.csv report.json
```

Or use it as a library:

```python
import pandas as pd
from data_cleaning_agent import DataCleaningAgent

df = pd.read_csv("input.csv")
agent = DataCleaningAgent()
cleaned = agent.clean(df)

cleaned.to_csv("output.csv", index=False)
print(agent.report.to_text())      # human-readable audit log
agent.report.to_dict()             # same thing, as JSON-able dict
```

## Example

See [`examples/`](examples/) for a deliberately messy sample input, the
cleaned output, and the full audit log produced by running:

```bash
python -m data_cleaning_agent.agent examples/sample_input.csv examples/cleaned_output.csv examples/report.json
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Known limitations

- **Z-score outlier detection can "mask" itself on small samples** — a
  single extreme value inflates the mean/std it's being judged against, so
  it can slip under the `|z| > 3` threshold on datasets with only a
  handful of rows. This is a well-known property of z-score methods, not a
  bug; it becomes reliable once you have a reasonable sample size (dozens
  of rows or more).
- Duplicate detection excludes columns that look like surrogate IDs
  (column name matches `*_id`/`id` and every value is unique). On a very
  small dataset with few non-ID columns, this can be aggressive — two
  genuinely different records that happen to match on every remaining
  column will be treated as duplicates.
- The categorical-vs-free-text heuristic (used to decide whether to
  mode-impute a missing text value) is based on cardinality and repetition
  within the *current* dataset, not a semantic understanding of the
  column — a genuinely categorical column with too few repeated values in
  a small sample may be treated as free text and left null instead of
  imputed.

## License

MIT — see [LICENSE](LICENSE).
