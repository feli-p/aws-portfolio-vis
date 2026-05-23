from __future__ import annotations

import io
import os
import time
from urllib.parse import urlparse

import boto3
import numpy as np
import pandas as pd


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _read_csv_from_s3_uri(s3_uri: str) -> pd.DataFrame:
    parsed = urlparse(s3_uri)
    bucket = parsed.netloc
    key = parsed.path.lstrip("/")

    if not bucket or not key:
        raise RuntimeError(f"Invalid S3 URI: {s3_uri}")

    s3 = boto3.client("s3")
    obj = s3.get_object(Bucket=bucket, Key=key)
    return pd.read_csv(io.BytesIO(obj["Body"].read()))


def run_athena_query(query: str) -> pd.DataFrame:
    region = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1"))

    database = _require_env("ATHENA_DATABASE")
    output_s3 = _require_env("ATHENA_OUTPUT_S3")

    athena = boto3.client("athena", region_name=region)

    response = athena.start_query_execution(
        QueryString=query,
        QueryExecutionContext={"Database": database},
        ResultConfiguration={"OutputLocation": output_s3},
    )

    query_id = response["QueryExecutionId"]

    while True:
        execution = athena.get_query_execution(QueryExecutionId=query_id)
        status = execution["QueryExecution"]["Status"]["State"]

        if status in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            break

        time.sleep(1.5)

    if status != "SUCCEEDED":
        reason = execution["QueryExecution"]["Status"].get("StateChangeReason", "No reason returned")
        raise RuntimeError(f"Athena query failed: {status}. Reason: {reason}")

    result_location = execution["QueryExecution"]["ResultConfiguration"]["OutputLocation"]
    return _read_csv_from_s3_uri(result_location)


def load_transactions(limit: int | None = None) -> pd.DataFrame:
    database = _require_env("ATHENA_DATABASE")
    table = _require_env("ATHENA_TRANSACTIONS_TABLE")

    if limit is None:
        query = f'SELECT * FROM "{database}"."{table}"'
    else:
        query = f'SELECT * FROM "{database}"."{table}" LIMIT {int(limit)}'

    df = run_athena_query(query)
    return clean_dataframe(df)


def load_asset_history(limit: int | None = None) -> pd.DataFrame:
    database = _require_env("ATHENA_DATABASE")
    table = _require_env("ATHENA_HISTORY_TABLE")

    if limit is None:
        query = f'SELECT * FROM "{database}"."{table}"'
    else:
        query = f'SELECT * FROM "{database}"."{table}" LIMIT {int(limit)}'

    df = run_athena_query(query)
    return clean_dataframe(df)


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df.columns = (
        df.columns.astype(str)
        .str.strip()
        .str.lower()
        .str.replace(" ", "_", regex=False)
        .str.replace("-", "_", regex=False)
    )

    for col in df.columns:
        if df[col].dtype == "object":
            converted_date = pd.to_datetime(df[col], errors="coerce")
            if converted_date.notna().mean() >= 0.8:
                df[col] = converted_date

    for col in df.columns:
        if df[col].dtype == "object":
            numeric = pd.to_numeric(df[col], errors="coerce")
            if numeric.notna().mean() >= 0.8:
                df[col] = numeric

    return df


def get_numeric_columns(df: pd.DataFrame) -> list[str]:
    return df.select_dtypes(include=["number"]).columns.tolist()


def get_datetime_columns(df: pd.DataFrame) -> list[str]:
    return df.select_dtypes(include=["datetime64[ns]", "datetimetz"]).columns.tolist()


def get_categorical_columns(df: pd.DataFrame, max_unique: int = 50) -> list[str]:
    categorical = []

    for col in df.columns:
        if col in get_numeric_columns(df) or col in get_datetime_columns(df):
            continue

        unique_count = df[col].nunique(dropna=True)

        if 1 < unique_count <= max_unique:
            categorical.append(col)

    return categorical


def pick_first_existing(df: pd.DataFrame, candidates: list[str]) -> str | None:
    cols = set(df.columns)
    for candidate in candidates:
        if candidate in cols:
            return candidate
    return None


def infer_value_column(df: pd.DataFrame) -> str | None:
    candidates = [
        "market_value",
        "amount",
        "monto",
        "saldo",
        "balance",
        "value",
        "valor",
        "exposure",
        "aum",
        "notional",
        "price",
        "total",
    ]

    found = pick_first_existing(df, candidates)
    if found:
        return found

    numeric_cols = get_numeric_columns(df)
    if not numeric_cols:
        return None

    return numeric_cols[0]


def infer_return_column(df: pd.DataFrame) -> str | None:
    candidates = [
        "return",
        "returns",
        "rendimiento",
        "monthly_return",
        "monthly_return_pct",
        "return_pct",
        "performance",
        "pnl_pct",
    ]

    found = pick_first_existing(df, candidates)
    if found:
        return found

    for col in get_numeric_columns(df):
        if "return" in col or "rend" in col or "performance" in col:
            return col

    return None


def infer_date_column(df: pd.DataFrame) -> str | None:
    candidates = [
        "date",
        "fecha",
        "month",
        "period",
        "periodo",
        "transaction_date",
        "as_of_date",
        "valuation_date",
    ]

    found = pick_first_existing(df, candidates)
    if found:
        return found

    datetime_cols = get_datetime_columns(df)
    if datetime_cols:
        return datetime_cols[0]

    return None


def infer_group_column(df: pd.DataFrame) -> str | None:
    candidates = [
        "asset_class",
        "asset",
        "instrument",
        "producto",
        "product",
        "security",
        "ticker",
        "client_segment",
        "segment",
        "portfolio",
        "account",
        "type",
        "category",
        "categoria",
    ]

    found = pick_first_existing(df, candidates)
    if found:
        return found

    categorical_cols = get_categorical_columns(df)
    if categorical_cols:
        return categorical_cols[0]

    return None


def summarize_for_chat(transactions: pd.DataFrame, history: pd.DataFrame) -> str:
    text = []

    text.append("Transactions table:")
    text.append(f"- Rows: {len(transactions):,}")
    text.append(f"- Columns: {', '.join(transactions.columns.tolist())}")

    value_col = infer_value_column(transactions)
    group_col = infer_group_column(transactions)

    if value_col:
        text.append(f"- Main numeric value column: {value_col}")
        text.append(f"- Total {value_col}: {transactions[value_col].sum():,.2f}")

    if group_col and value_col:
        grouped = (
            transactions.groupby(group_col, dropna=False)[value_col]
            .sum()
            .sort_values(ascending=False)
            .head(10)
        )
        text.append(f"\nTop allocation by {group_col}:")
        text.append(grouped.to_string())

    text.append("\nAsset history table:")
    text.append(f"- Rows: {len(history):,}")
    text.append(f"- Columns: {', '.join(history.columns.tolist())}")

    date_col = infer_date_column(history)
    return_col = infer_return_column(history)

    if date_col:
        text.append(f"- Date column: {date_col}")
        text.append(f"- Min date: {history[date_col].min()}")
        text.append(f"- Max date: {history[date_col].max()}")

    if return_col:
        text.append(f"- Return column: {return_col}")
        text.append(f"- Average return: {history[return_col].mean():.4f}")

    return "\n".join(text)
