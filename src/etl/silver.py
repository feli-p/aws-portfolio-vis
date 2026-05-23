import argparse
import os
import glob
import re
from pathlib import Path

import awswrangler as wr
import boto3
import pandas as pd

from src.common.logging_utils import setup_logger

# To-do: Agregarlos como argumentos
AWS_REGION = "us-east-1"
BUCKET_NAME = "aws-portfolio-vis"
S3_PREFIX = "data/silver"
S3_BASE_PATH = f"s3://{BUCKET_NAME}/{S3_PREFIX}"
GLUE_DB_NAME = "silver_portfolio_db"

# To-Do: Agregar data-typespara las tablas.

FILES = ["sales_train.csv", "items_en.csv", "item_categories_en.csv", "shops_en.csv"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ETL silver layer: Agrega las tablas y almacena parquets con particiones en AWS."
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="data/",
        help="Directorio de entrada con CSVs raw (relativo a la raíz del repo).",
    )
    return parser.parse_args()


def process_transactions(
        session,
        logger,
        csv_path: str = "data/transactions.csv",
):
    """Lee el CSV de transacciones, lo limpia y lo sube particionado a S3."""
    if not os.path.exists(csv_path):
        logger.error("No se encontró: %s", csv_path)
        raise FileNotFoundError(csv_path)
    
    logger.info("Procesando: Transacciones...")
    df = pd.read_csv(csv_path)

    # Limpieza y estandarización de tipos de datos
    df['date'] = pd.to_datetime(df['date'], format="%d/%m/%Y")
    df['account'] = df['account'].astype(str).str.lower().str.replace(" ", "_")
    df['asset'] = df['asset'].astype(str).str.lower().str.replace(" ", "")
    
    # Ruta destino en S3
    s3_path = f"{S3_BASE_PATH}/transactions"
    
    # Guardar en S3 como Parquet, particionar y registrar en Glue Catalog
    logger.info(f"Subiendo transacciones a S3 y registrando en Glue...")
    wr.s3.to_parquet(
        df=df,
        path=s3_path,
        dataset=True,
        database=GLUE_DB_NAME,
        table="silver_portfolio_transactions",
        partition_cols=["account"],
        mode="overwrite",
        index=False,
        boto3_session=session,
    )
    logger.info("Tabla 'silver_portfolio_transactions' cargada exitosamente.")

def process_asset_histories(
    session,
    logger,
    histories_folder: str = "data/asset_histories",
):
    """Consolida todos los CSVs individuales de históricos en un solo DataFrame y lo sube."""
    csv_files = glob.glob(os.path.join(histories_folder, "*.csv"))

    if not csv_files:
        logger.error(f"No se encontraron los archivos en {histories_folder}")
        return
    
    logger.info("Procesando: Asset histories...")

    all_dfs = []

    # Leer y unificar todos los CSVs de históricos
    for file_path in csv_files:
        filename = os.path.basename(file_path) # Ejemplo: "inversiones_spy_history.csv"
        
        # Usamos una expresión regular para capturar el patrón: <cuenta>_<activo>_history.csv
        match = re.match(r"^([a-zA-Z0-9_]+)_([a-zA-Z0-9_]+)_history\.csv$", filename)
        
        if not match:
            logger.error(f"El archivo '{filename}' no cumple con el formato <account>_<asset>_history.csv. Omitido.")
            continue
            
        # Extraemos las variables del nombre del archivo
        account_from_file = match.group(1).lower()
        asset_from_file = match.group(2).lower()
        
        # Leer el contenido del CSV
        df_temp = pd.read_csv(file_path)
        
        if df_temp.empty:
            continue
        
        df_temp['date'] = pd.to_datetime(df_temp['date'])
        df_temp['account'] = account_from_file
        df_temp['asset'] = asset_from_file
        
        # Extraemos el año para usarlo como partición
        df_temp['year'] = df_temp['date'].dt.year

        all_dfs.append(df_temp)

    if not all_dfs:
        logger.error("No se procesó ningún archivo válido de histórico de activos.")
        return

    # Consolidamos todo en un súper DataFrame listo para analítica masiva
    df_consolidated = pd.concat(all_dfs, ignore_index=True)

    # Ruta destino en S3
    s3_path = f"{S3_BASE_PATH}/asset_history"
    
    # Guardar optimizado con particiones multinivel: account -> asset -> year
    logger.info(f"Subiendo {len(df_consolidated)} registros históricos a S3 y registrando en Glue...")
    wr.s3.to_parquet(
        df=df_consolidated,
        path=s3_path,
        dataset=True,
        database=GLUE_DB_NAME,
        table="silver_portfolio_asset_history",
        partition_cols=["account", "asset", "year"],
        mode="overwrite",
        index=False,
        boto3_session=session,
    )
    logger.info("Tabla 'silver_portfolio_asset_history' cargada exitosamente.")


def main():
    logger = setup_logger("ETL Silver")
    logger.info("Iniciando capa Silver...")
    args = parse_args()

    # En un futuro los archivos deberán obtenerse en la bronze layer en S3
    project_root = Path(__file__).resolve().parents[2]
    data_dir = project_root / args.data_dir

    try:
        session = boto3.Session(region_name=AWS_REGION)

        logger.info("Subiendo Parquets a S3 y registrando en Glue")
        wr.catalog.create_database(name=GLUE_DB_NAME, exist_ok=True)
        process_transactions(session, logger, data_dir / "transactions.csv")
        process_asset_histories(session, logger, data_dir / "asset_histories")
        logger.info("ETL finalizado. La capa Silver está lista en AWS.")
    except Exception as e:
        logger.error(f"Error ejecutando el pipeline: {e}")


if __name__ == "__main__":
    main()