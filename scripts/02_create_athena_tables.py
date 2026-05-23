import argparse
import time

import boto3


def run_query(client, query: str, database: str, output_s3: str):
    response = client.start_query_execution(
        QueryString=query,
        QueryExecutionContext={"Database": database},
        ResultConfiguration={"OutputLocation": output_s3},
    )
    qid = response["QueryExecutionId"]
    while True:
        status = client.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]
        state = status["State"]
        if state in ["SUCCEEDED", "FAILED", "CANCELLED"]:
            if state != "SUCCEEDED":
                reason = status.get("StateChangeReason", "No reason returned")
                raise RuntimeError(f"Athena query {state}: {reason}\nQuery:\n{query}")
            return qid
        time.sleep(2)


def main():
    parser = argparse.ArgumentParser(description="Create Glue/Athena external tables for the portfolio project.")
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--database", default="portfolio_db")
    parser.add_argument("--project-prefix", default="portfolio")
    parser.add_argument("--athena-output", required=True)
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()

    client = boto3.client("athena", region_name=args.region)
    bucket = args.bucket
    prefix = args.project_prefix.strip("/")
    database = args.database

    queries = [
        f"CREATE DATABASE IF NOT EXISTS {database}",
        f"DROP TABLE IF EXISTS {database}.transactions",
        f"""
        CREATE EXTERNAL TABLE {database}.transactions (
          date string,
          account string,
          asset string,
          amount_usd double,
          amount_shares double,
          buy_price double
        )
        ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.OpenCSVSerde'
        WITH SERDEPROPERTIES (
          'separatorChar' = ',',
          'quoteChar' = '\"',
          'escapeChar' = '\\\\'
        )
        STORED AS TEXTFILE
        LOCATION 's3://{bucket}/{prefix}/silver/transactions/'
        TBLPROPERTIES ('skip.header.line.count'='1')
        """,
        f"DROP TABLE IF EXISTS {database}.asset_history",
        f"""
        CREATE EXTERNAL TABLE {database}.asset_history (
          date string,
          market_value double,
          daily_acb double,
          daily_pl double,
          daily_irr double,
          account string,
          asset string,
          source_file string
        )
        ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.OpenCSVSerde'
        WITH SERDEPROPERTIES (
          'separatorChar' = ',',
          'quoteChar' = '\"',
          'escapeChar' = '\\\\'
        )
        STORED AS TEXTFILE
        LOCATION 's3://{bucket}/{prefix}/silver/asset_history/'
        TBLPROPERTIES ('skip.header.line.count'='1')
        """,
    ]

    for query in queries:
        clean = "\n".join(line.strip() for line in query.strip().splitlines() if line.strip())
        print(f"Running: {clean[:120]}...")
        qid = run_query(client, query, database, args.athena_output)
        print(f"SUCCEEDED: {qid}")

    print("Athena tables are ready.")


if __name__ == "__main__":
    main()
