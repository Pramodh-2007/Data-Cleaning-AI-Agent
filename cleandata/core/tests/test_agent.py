import numpy as np
import pandas as pd
import pytest

from data_cleaning_agent.agent import DataCleaningAgent


@pytest.fixture
def messy_df():
    return pd.DataFrame({
        " Customer ID ": [1, 2, 3, 4],
        " Full Name": [" Alice Smith ", "bob jones", " Alice Smith ", "Carlos Diaz"],
        " Country ": ["usa", "USA", "usa", "Mexico "],
        " Purchase Amount": ["$1200", "950", "$1200", "1100.50"],
    })


def test_standardizes_column_names(messy_df):
    agent = DataCleaningAgent()
    cleaned = agent.clean(messy_df)
    assert list(cleaned.columns) == [
        "customer_id", "full_name", "country", "purchase_amount",
    ]


def test_strips_whitespace(messy_df):
    agent = DataCleaningAgent()
    cleaned = agent.clean(messy_df)
    assert cleaned["full_name"].iloc[0] == "Alice Smith"


def test_casts_currency_strings_to_numeric(messy_df):
    agent = DataCleaningAgent()
    cleaned = agent.clean(messy_df)
    assert pd.api.types.is_numeric_dtype(cleaned["purchase_amount"])
    assert cleaned["purchase_amount"].iloc[0] == 1200.0


def test_normalizes_inconsistent_capitalization(messy_df):
    agent = DataCleaningAgent()
    cleaned = agent.clean(messy_df)
    # "usa" / "USA" should collapse into a single canonical label
    assert cleaned["country"].nunique() == 2  # Usa, Mexico
    assert set(cleaned["country"].unique()) == {"Usa", "Mexico"}


def test_drops_true_duplicate_rows_ignoring_id_column(messy_df):
    agent = DataCleaningAgent()
    cleaned = agent.clean(messy_df)
    # rows 1 and 3 are identical except for the surrogate id column
    assert len(cleaned) == 3


def test_imputes_missing_numeric_with_median():
    df = pd.DataFrame({
        "id": [1, 2, 3, 4],
        "amount": [10.0, 20.0, np.nan, 30.0],
    })
    agent = DataCleaningAgent()
    cleaned = agent.clean(df)
    assert cleaned["amount"].isna().sum() == 0
    assert cleaned.loc[2, "amount"] == 20.0  # median of [10, 20, 30]


def test_imputes_missing_categorical_with_mode():
    # note: a distinguishing column is required so rows aren't
    # indistinguishable (and therefore true duplicates) once the id is
    # excluded from comparison
    df = pd.DataFrame({
        "id": [1, 2, 3, 4],
        "category": ["A", "A", None, "B"],
        "amount": [10, 20, 30, 40],
    })
    agent = DataCleaningAgent()
    cleaned = agent.clean(df)
    assert cleaned["category"].isna().sum() == 0
    assert len(cleaned) == 4
    assert cleaned.loc[2, "category"] == "A"


def test_drops_sparse_column():
    df = pd.DataFrame({
        "id": range(10),
        "mostly_empty": [None] * 8 + ["x", "y"],
        "distinguishing_value": range(100, 110),
    })
    agent = DataCleaningAgent()
    cleaned = agent.clean(df)
    assert "mostly_empty" not in cleaned.columns
    assert len(cleaned) == 10


def test_clips_statistical_outliers():
    # z-score outlier detection needs enough points that a single extreme
    # value doesn't dominate the mean/std it's being judged against (the
    # classic "masking" limitation of z-scores) -- 30 points here, one
    # obvious outlier.
    rng = np.random.default_rng(0)
    normal_values = rng.normal(loc=10, scale=1, size=29).round(1)
    values = list(normal_values) + [5000.0]
    df = pd.DataFrame({
        "id": range(30),
        "value": values,
        "distinguishing_value": range(100, 130),
    })
    agent = DataCleaningAgent()
    cleaned = agent.clean(df)
    assert len(cleaned) == 30
    assert cleaned["value"].max() < 5000


def test_report_logs_every_action(messy_df):
    agent = DataCleaningAgent()
    agent.clean(messy_df)
    assert len(agent.report.actions) > 0
    d = agent.report.to_dict()
    assert "summary" in d and "actions" in d
    assert d["summary"]["rows_before"] == 4


def test_empty_dataframe_does_not_crash():
    df = pd.DataFrame({"a": [], "b": []})
    agent = DataCleaningAgent()
    cleaned = agent.clean(df)
    assert len(cleaned) == 0
