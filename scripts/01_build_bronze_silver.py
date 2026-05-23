import argparse
import re
import zipfile
from pathlib import Path

import boto3
import pandas as pd


def parse_s3_uri(s3_uri: str):
    if not s3_uri.startswith("s3://"):
        raise ValueError(f"Invalid S3 URI: {s3_uri}")
    path = s3_uri.replace("s3://", "", 1)
    bucket, key = path.split("/", 1)
    return bucket, key.rstrip("/")


def upload_file_to_s3(local_path: Path, s3_uri: str):
    bucket, key_prefix = parse_s3_uri(s3_uri)
    key = f"{key_prefix}/{local_path.name}"
    boto3.client("s3").upload_file(str(local_path), bucket, key)
    return f"s3://{bucket}/{key}"


def upload_directory_to_s3(local_dir: Path, s3_uri: str):
    bucket, key_prefix = parse_s3_uri(s3_uri)
    s3 = boto3.client("s3")
    uploaded = []
    for path in local_dir.rglob("*"):
        if path.is_file():
            rel = path.relative_to(local_dir).as_posix()
            key = f"{key_prefix}/{rel}"
            s3.upload_file(str(path), bucket, key)
            uploaded.append(f"s3://{bucket}/{key}")
    return uploaded


def extract_zip(zip_path: Path, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(output_dir)


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [re.sub(r"[^a-zA-Z0-9_]+", "_", c.strip().lower()).strip("_") for c in df.columns]
    return df


def infer_account_asset_from_filename(filename: str):
    name = filename.replace("_history.csv", "")
    parts = name.split("_")
    if len(parts) < 2:
        return "unknown", name.upper()
    account_raw = parts[0].strip().lower()
    asset = parts[1].strip().upper()
    account_map = {"inversiones": "Inversiones", "retiro": "Retiro"}
    return account_map.get(account_raw, account_raw.title()), asset


def build_silver(extract_dir: Path, silver_dir: Path):
    data_dir = extract_dir / "data"
    if not data_dir.exists():
        raise FileNotFoundError(f"Expected folder not found: {data_dir}")

    transactions_dir = silver_dir / "transactions"
    history_dir = silver_dir / "asset_history"
    transactions_dir.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)

    transactions_path = data_dir / "transactions.csv"
    if not transactions_path.exists():
        raise FileNotFoundError(f"Expected file not found: {transactions_path}")

    transactions = normalize_columns(pd.read_csv(transactions_path, encoding="utf-8-sig"))
    if "date" in transactions.columns:
        transactions["date"] = pd.to_datetime(transactions["date"], dayfirst=True, errors="coerce").dt.strftime("%Y-%m-%d")
    for col in ["account", "asset"]:
        if col in transactions.columns:
            transactions[col] = transactions[col].astype(str).str.strip()
    if "asset" in transactions.columns:
        transactions["asset"] = transactions["asset"].str.upper()
    for col in ["amount_usd", "amount_shares", "buy_price"]:
        if col in transactions.columns:
            transactions[col] = pd.to_numeric(transactions[col], errors="coerce")
    transactions = transactions.dropna(subset=["date", "account", "asset"])
    transactions.to_csv(transactions_dir / "transactions.csv", index=False)

    histories_root = data_dir / "asset_histories"
    if not histories_root.exists():
        raise FileNotFoundError(f"Expected folder not found: {histories_root}")

    frames = []
    for file in sorted(histories_root.glob("*_history.csv")):
        account, asset = infer_account_asset_from_filename(file.name)
        df = normalize_columns(pd.read_csv(file))
        df["account"] = account
        df["asset"] = asset
        df["source_file"] = file.name
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        for col in ["market_value", "daily_acb", "daily_pl", "daily_irr"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["date", "account", "asset"])
        frames.append(df)

    if not frames:
        raise FileNotFoundError(f"No *_history.csv files found in {histories_root}")
    asset_history = pd.concat(frames, ignore_index=True)
    asset_history.to_csv(history_dir / "asset_history.csv", index=False)

    return {
        "transactions_rows": len(transactions),
        "asset_history_rows": len(asset_history),
        "transactions_file": str(transactions_dir / "transactions.csv"),
        "asset_history_file": str(history_dir / "asset_history.csv"),
    }


def main():
    parser = argparse.ArgumentParser(description="Build Bronze and Silver portfolio data layers in S3.")
    parser.add_argument("--zip-path", required=True, help="Local path to the original data ZIP.")
    parser.add_argument("--bronze-s3", required=True, help="S3 prefix for raw data, for example s3://bucket/portfolio/bronze/raw_zip")
    parser.add_argument("--silver-s3", required=True, help="S3 prefix for prepared tables, for example s3://bucket/portfolio/silver")
    parser.add_argument("--work-dir", default="work_portfolio_data", help="Local working directory.")
    args = parser.parse_args()

    zip_path = Path(args.zip_path)
    if not zip_path.exists():
        raise FileNotFoundError(f"ZIP not found: {zip_path}")

    work_dir = Path(args.work_dir)
    bronze_local = work_dir / "bronze_raw"
    extract_dir = work_dir / "extracted"
    silver_dir = work_dir / "silver"
    bronze_local.mkdir(parents=True, exist_ok=True)

    local_zip_copy = bronze_local / zip_path.name
    local_zip_copy.write_bytes(zip_path.read_bytes())

    print("Uploading original ZIP to Bronze...")
    print(upload_file_to_s3(local_zip_copy, args.bronze_s3))

    print("Extracting ZIP locally...")
    extract_zip(zip_path, extract_dir)

    print("Uploading extracted raw files to Bronze...")
    raw_uploaded = upload_directory_to_s3(extract_dir, f"{args.bronze_s3}/extracted")
    print(f"Raw files uploaded: {len(raw_uploaded)}")

    print("Building Silver tables...")
    result = build_silver(extract_dir, silver_dir)
    print(result)

    print("Uploading Silver tables...")
    silver_uploaded = upload_directory_to_s3(silver_dir, args.silver_s3)
    for uri in silver_uploaded:
        print(uri)

    print("Bronze/Silver build completed.")


if __name__ == "__main__":
    main()
