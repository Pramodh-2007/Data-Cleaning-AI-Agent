"""
Data Cleaning AI Agent
======================

A rule-driven "agent" that inspects a raw CSV/DataFrame, decides which
cleaning actions to apply column-by-column, executes them, and produces
a human-readable report of every decision it made (so the cleaning is
auditable, not a black box).

Why call it an "agent"?
------------------------
It follows the classic perceive -> decide -> act -> report loop:
  1. PERCEIVE : profile each column (dtype, nulls, duplicates, outliers,
                 inconsistent text casing/whitespace, mixed types, etc.)
  2. DECIDE   : a rule engine picks an appropriate action per issue
                 (impute / drop / standardize / clip / dedupe)
  3. ACT      : the action is applied to the DataFrame
  4. REPORT   : every action + rationale is logged into a structured
                 cleaning report (JSON + text) so a human can audit it.

No external LLM call is required for this reference implementation
(it works fully offline / deterministically), but the same Agent class
can be pointed at an LLM (see `llm_hook`) to have a model decide edge
cases in natural language -- the hook is included below.

Usage
-----
    python -m data_cleaning_agent.agent input.csv cleaned_output.csv report.json
    # or, after `pip install -e .`:
    clean-data input.csv cleaned_output.csv report.json
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import numpy as np
import pandas as pd


# --------------------------------------------------------------------------
# 1. Data structures for tracking what the agent did
# --------------------------------------------------------------------------

@dataclass
class CleaningAction:
    column: str
    issue: str
    action: str
    details: str
    rows_affected: int = 0


@dataclass
class CleaningReport:
    actions: list[CleaningAction] = field(default_factory=list)
    rows_before: int = 0
    rows_after: int = 0
    cols_before: int = 0
    cols_after: int = 0

    def log(self, column: str, issue: str, action: str, details: str, rows_affected: int = 0):
        self.actions.append(CleaningAction(column, issue, action, details, rows_affected))

    def to_dict(self) -> dict:
        return {
            "summary": {
                "rows_before": self.rows_before,
                "rows_after": self.rows_after,
                "cols_before": self.cols_before,
                "cols_after": self.cols_after,
                "total_actions": len(self.actions),
            },
            "actions": [a.__dict__ for a in self.actions],
        }

    def to_text(self) -> str:
        lines = [
            "DATA CLEANING REPORT",
            "=" * 60,
            f"Rows:    {self.rows_before} -> {self.rows_after}",
            f"Columns: {self.cols_before} -> {self.cols_after}",
            f"Total actions taken: {len(self.actions)}",
            "-" * 60,
        ]
        for a in self.actions:
            lines.append(
                f"[{a.column}] {a.issue} -> {a.action} "
                f"({a.rows_affected} rows) :: {a.details}"
            )
        return "\n".join(lines)


# --------------------------------------------------------------------------
# 2. The Agent
# --------------------------------------------------------------------------

class DataCleaningAgent:
    """
    A configurable agent that perceives data quality issues in a DataFrame
    and decides/acts on cleaning steps, producing a full audit trail.

    Parameters
    ----------
    outlier_z_thresh : float
        Z-score beyond which a numeric value is flagged as an outlier.
    dup_subset : list[str] | None
        Columns to consider when detecting duplicate rows. None = all columns.
    llm_hook : Callable[[str], str] | None
        Optional callback the agent can use to ask an LLM to classify an
        ambiguous free-text value (e.g. normalizing "USA", "U.S.A", "United
        States" -> a canonical label). Not required to run the agent.
    """

    def __init__(
        self,
        outlier_z_thresh: float = 3.0,
        dup_subset: Optional[list[str]] = None,
        llm_hook: Optional[Callable[[str], str]] = None,
    ):
        self.outlier_z_thresh = outlier_z_thresh
        self.dup_subset = dup_subset
        self.llm_hook = llm_hook
        self.report = CleaningReport()

    # ---- PERCEIVE + DECIDE + ACT, orchestrated -----------------------

    def clean(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        self.report = CleaningReport()
        self.report.rows_before, self.report.cols_before = df.shape

        # Order matters: normalize representation first (names, whitespace,
        # dtypes, text casing) so that two rows which are "really" the same
        # record are recognized as duplicates. Deduplicate on that raw,
        # un-imputed data *before* filling in missing values -- otherwise an
        # imputed value (e.g. two rows both getting the same median) can look
        # like an accidental duplicate of an unrelated row and get dropped.
        df = self._standardize_column_names(df)
        df = self._strip_whitespace(df)
        df = self._fix_dtypes(df)
        df = self._normalize_text_columns(df)
        df = self._drop_duplicate_rows(df)
        df = self._handle_missing_values(df)
        df = self._handle_outliers(df)

        self.report.rows_after, self.report.cols_after = df.shape
        return df

    # ---- individual perception/decision/action steps -----------------

    def _standardize_column_names(self, df: pd.DataFrame) -> pd.DataFrame:
        original = list(df.columns)
        new_cols = (
            df.columns.str.strip()
            .str.lower()
            .str.replace(r"[^\w]+", "_", regex=True)
            .str.strip("_")
        )
        if list(new_cols) != original:
            df.columns = new_cols
            self.report.log(
                "ALL", "inconsistent column naming", "standardize_column_names",
                f"{original} -> {list(new_cols)}",
            )
        return df

    def _strip_whitespace(self, df: pd.DataFrame) -> pd.DataFrame:
        for col in df.select_dtypes(include=["object", "str"]).columns:
            before = df[col].copy()
            df[col] = df[col].apply(lambda x: x.strip() if isinstance(x, str) else x)
            changed = (before != df[col]) & before.notna()
            if changed.sum() > 0:
                self.report.log(
                    col, "leading/trailing whitespace", "strip",
                    "trimmed whitespace from text values", int(changed.sum()),
                )
            # Whitespace-only cells become "" after stripping -- treat as missing
            blank_mask = df[col] == ""
            n_blank = int(blank_mask.sum())
            if n_blank > 0:
                df.loc[blank_mask, col] = np.nan
                self.report.log(
                    col, "blank/whitespace-only cells", "convert_blank_to_null",
                    "empty strings after stripping treated as missing values",
                    n_blank,
                )
        return df

    def _fix_dtypes(self, df: pd.DataFrame) -> pd.DataFrame:
        for col in df.columns:
            if not (df[col].dtype == object or str(df[col].dtype) == "str"):
                continue

            # try numeric coercion (handles "$1,200", "1200 ", "3.5%")
            cleaned = (
                df[col]
                .astype(str)
                .str.replace(r"[$,%]", "", regex=True)
                .str.strip()
            )
            numeric = pd.to_numeric(cleaned, errors="coerce")
            non_null = df[col].notna()
            success_rate = numeric[non_null].notna().mean() if non_null.sum() else 0

            if success_rate >= 0.8:
                n_changed = int((df[col].notna() & numeric.isna()).sum())
                df[col] = numeric
                self.report.log(
                    col, "numeric stored as text", "cast_to_numeric",
                    f"parsed currency/percent symbols; {n_changed} values "
                    "could not be parsed and became NaN",
                )
                continue

            # try datetime coercion
            dt = pd.to_datetime(df[col], errors="coerce", format="mixed")
            non_null = df[col].notna()
            success_rate = dt[non_null].notna().mean() if non_null.sum() else 0
            if success_rate >= 0.8:
                df[col] = dt
                self.report.log(
                    col, "date stored as text", "cast_to_datetime",
                    "parsed inconsistent date formats into datetime64",
                )
        return df

    def _handle_missing_values(self, df: pd.DataFrame) -> pd.DataFrame:
        for col in df.columns:
            n_missing = df[col].isna().sum()
            if n_missing == 0:
                continue
            pct_missing = n_missing / len(df)

            if pct_missing > 0.6:
                df = df.drop(columns=[col])
                self.report.log(
                    col, f"{pct_missing:.0%} missing", "drop_column",
                    "too sparse to impute reliably", int(n_missing),
                )
                continue

            if pd.api.types.is_numeric_dtype(df[col]):
                fill_value = df[col].median()
                df[col] = df[col].fillna(fill_value)
                self.report.log(
                    col, f"{n_missing} missing numeric values", "impute_median",
                    f"filled with column median ({fill_value:.3g})", int(n_missing),
                )
            elif pd.api.types.is_datetime64_any_dtype(df[col]):
                df = df  # leave date gaps as-is; imputing dates is unsafe
                self.report.log(
                    col, f"{n_missing} missing dates", "leave_as_null",
                    "imputing dates would fabricate events; left as NaT",
                    int(n_missing),
                )
            else:
                # Mode-imputation only makes sense for genuinely categorical
                # columns (a handful of repeated values). For high-cardinality
                # free text (notes, comments, names) picking "the most common
                # value" and stamping it onto unrelated rows would fabricate
                # misleading content, so those are left as null instead.
                non_null = df[col].dropna()
                n_unique = non_null.nunique()
                # A column only "looks categorical" if (a) it has a capped
                # number of distinct values, and (b) at least one value
                # repeats -- i.e. it isn't just a column where every row
                # happens to be distinct (names, free-text notes, IDs).
                # Requiring repetition rather than a fixed ratio holds up
                # on both small and large samples.
                has_repeats = n_unique < len(non_null)
                looks_categorical = n_unique <= 20 and has_repeats
                if looks_categorical:
                    mode = df[col].mode(dropna=True)
                    fill_value = mode.iloc[0] if not mode.empty else "Unknown"
                    df[col] = df[col].fillna(fill_value)
                    self.report.log(
                        col, f"{n_missing} missing categorical values",
                        "impute_mode",
                        f"filled with most frequent value ('{fill_value}')",
                        int(n_missing),
                    )
                else:
                    self.report.log(
                        col, f"{n_missing} missing free-text values",
                        "leave_as_null",
                        "high-cardinality free text; imputing a 'most "
                        "common' value would fabricate misleading content",
                        int(n_missing),
                    )
        return df

    def _normalize_text_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        for col in df.select_dtypes(include=["object", "str"]).columns:
            if df[col].nunique(dropna=True) == 0:
                continue
            # Detect columns that look categorical (low cardinality) and
            # normalize casing so "usa", "USA", "Usa" collapse to one label.
            n_unique = df[col].nunique(dropna=True)
            if n_unique <= max(20, int(0.1 * len(df))):
                before_unique = df[col].dropna().unique().tolist()
                normalized = df[col].apply(
                    lambda x: x.title() if isinstance(x, str) else x
                )
                collapsed = normalized.dropna().unique().tolist()
                if len(collapsed) < len(before_unique):
                    df[col] = normalized
                    self.report.log(
                        col, "inconsistent capitalization", "normalize_case",
                        f"{len(before_unique)} raw variants -> {len(collapsed)} "
                        "canonical values via title-casing",
                    )
        return df

    def _handle_outliers(self, df: pd.DataFrame) -> pd.DataFrame:
        for col in df.select_dtypes(include=[np.number]).columns:
            series = df[col]
            std = series.std()
            if not std or np.isnan(std):
                continue
            z = (series - series.mean()) / std
            mask = z.abs() > self.outlier_z_thresh
            n_outliers = int(mask.sum())
            if n_outliers == 0:
                continue
            lower, upper = series.quantile(0.01), series.quantile(0.99)
            df.loc[mask, col] = series[mask].clip(lower, upper).round(2)
            self.report.log(
                col, f"{n_outliers} statistical outliers (|z| > {self.outlier_z_thresh})",
                "clip_to_1st_99th_percentile",
                f"clipped extreme values to [{lower:.3g}, {upper:.3g}]",
                n_outliers,
            )
        return df

    def _drop_duplicate_rows(self, df: pd.DataFrame) -> pd.DataFrame:
        subset = self.dup_subset
        if subset is None:
            # Auto-detect ID-like columns (unique per row, name suggests an
            # identifier) and exclude them -- two rows that are identical in
            # every *content* column are still duplicates even if a
            # surrogate ID column differs.
            id_like = [
                c for c in df.columns
                if re.search(r"(^|_)id($|_)", c) and df[c].is_unique
            ]
            subset = [c for c in df.columns if c not in id_like] or None
            if id_like:
                self.report.log(
                    "ALL", "id-like column(s) detected", "exclude_from_dup_check",
                    f"excluded {id_like} from duplicate comparison since a "
                    "surrogate id will always be unique",
                )

        dup_mask = df.duplicated(subset=subset, keep="first")
        n_dupes = int(dup_mask.sum())
        if n_dupes > 0:
            df = df[~dup_mask].reset_index(drop=True)
            self.report.log(
                "ALL", f"{n_dupes} duplicate rows", "drop_duplicates",
                f"kept first occurrence, subset={subset or 'all columns'}",
                n_dupes,
            )
        return df


# --------------------------------------------------------------------------
# 3. CLI entry point
# --------------------------------------------------------------------------

def main():
    if len(sys.argv) < 4:
        print("Usage: python data_cleaning_agent.py <input.csv> <output.csv> <report.json>")
        sys.exit(1)

    input_path, output_path, report_path = sys.argv[1:4]

    df = pd.read_csv(input_path)
    agent = DataCleaningAgent()
    cleaned = agent.clean(df)

    cleaned.to_csv(output_path, index=False)
    with open(report_path, "w") as f:
        json.dump(agent.report.to_dict(), f, indent=2, default=str)

    print(agent.report.to_text())
    print(f"\nCleaned data written to: {output_path}")
    print(f"Report written to:       {report_path}")


if __name__ == "__main__":
    main()
