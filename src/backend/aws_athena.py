# app/logic/aws_athena.py
import awswrangler as wr
import pandas as pd
import boto3
from datetime import datetime
from src.config import AWS_REGION, GLUE_DB_NAME, ATHENA_OUTPUT_BUCKET

def get_boto3_session():
    """Genera una sesión de boto3."""
    return boto3.Session(region_name=AWS_REGION)

def load_portfolio_metadata() -> tuple[list[str], list[str]]:
    """
    Obtiene las cuentas y activos únicos disponibles en el Data Lake para poblar los filtros de Streamlit.
    """
    session = get_boto3_session()
    
    query = f"""
        SELECT DISTINCT account, asset 
        FROM "{GLUE_DB_NAME}"."silver_portfolio_transactions"
    """
    
    df = wr.athena.read_sql_query(
        sql=query,
        database=GLUE_DB_NAME,
        s3_output=ATHENA_OUTPUT_BUCKET,
        boto3_session=session
    )
    
    accounts = df["account"].unique().tolist()
    assets = df["asset"].unique().tolist()
    return accounts, assets

def query_asset_history(
    start_date: str,
    end_date: str,
    accounts: list[str] = None,
    assets: list[str] = None
) -> pd.DataFrame:
    """
    Consulta el historial aplicando filtros de fechas, cuentas y activos.
    Devuelve un DataFrame ordenado cronológicamente.
    """
    session = get_boto3_session()

    # Convertimos de formato de fechas México a SQL
    SQL_DATE_FORMAT = "%Y-%m-%d"

    parsed_start = datetime.strptime(start_date, "%d/%m/%Y")
    parsed_end = datetime.strptime(end_date, "%d/%m/%Y")

    start_date = parsed_start.strftime(SQL_DATE_FORMAT)
    end_date = parsed_end.strftime(SQL_DATE_FORMAT)
    
    # Construcción dinámica de la query
    where_clauses = [f"date BETWEEN CAST('{start_date}' AS DATE) AND CAST('{end_date}' AS DATE)"]
    
    if accounts:
        accounts_str = ", ".join([f"'{acc}'" for acc in accounts])
        where_clauses.append(f"account IN ({accounts_str})")
        
    if assets:
        assets_str = ", ".join([f"'{asset}'" for asset in assets])
        where_clauses.append(f"asset IN ({assets_str})")
        
    where_stmt = " AND ".join(where_clauses)
    
    query = f"""
        SELECT 
            CAST(date AS DATE) as date,
            account,
            asset,
            market_value,
            daily_acb,
            daily_pl,
            daily_irr
        FROM "{GLUE_DB_NAME}"."silver_portfolio_asset_history"
        WHERE {where_stmt}
        ORDER BY date ASC
    """
    
    df = wr.athena.read_sql_query(
        sql=query,
        database=GLUE_DB_NAME,
        s3_output=ATHENA_OUTPUT_BUCKET,
        boto3_session=session
    )
    
    df["date"] = pd.to_datetime(df["date"])
    return df