import os

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
BUCKET_NAME = os.getenv("BUCKET_NAME","aws-portfolio-vis")
GLUE_DB_NAME = os.getenv("GLUE_DB_NAME", "silver_portfolio_db")

# Athena requiere un bucket de S3 para almacenar los resultados temporales de las queries
ATHENA_OUTPUT_BUCKET = os.getenv("ATHENA_OUTPUT_BUCKET", f"s3://{BUCKET_NAME}/athena-query-results/")

# IDs de Modelos de Amazon Bedrock
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")