from __future__ import annotations

import json
import os

import boto3

from src.common.logging_utils import setup_logger

logger = setup_logger(__name__)

def format_portfolio_context(report_metrics: dict, df_athena: any = None) -> str:
    """
    Serializar las métricas financieras y los datos de Athena en un formato Markdown para el prompt.
    """
    context_lines = [
        "### MÉTRICAS CLAVE DEL PORTAFOLIO CONSOLIDADO",
        f"- Valor Final Total: ${report_metrics.get('final_value', 0):,.2f}",
        f"- Rendimiento Total del Periodo: {report_metrics.get('total_return_pct', 0) * 100:.2f}%",
        f"- Volatilidad Anualizada: {report_metrics.get('annualized_volatility', 0) * 100:.2f}%",
        f"- Sharpe Ratio: {report_metrics.get('sharpe_ratio', 0):.2f}",
        ""
    ]
    
    if df_athena is not None:
        context_lines.append("### HISTORIAL RECIENTE POR ACTIVO / CUENTA (MUESTRA)")
        # Tomamos los últimos registros para no saturar la ventana de contexto
        sample_df = df_athena.tail(10)
        context_lines.append(sample_df.to_markdown(index=False))
        
    return "\n".join(context_lines)

def ask_bedrock(question: str, context) -> str:
    """
    Envía una pregunta junto con el contexto del portafolio a Amazon Bedrock.
    """
    question = (question or "").strip()

    if not question:
        return "Escribe una pregunta sobre el portafolio."
    
    region = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1"))
    model_id = os.getenv(
        "BEDROCK_MODEL_ID",
        #"anthropic.claude-3-haiku-20240307-v1:0",
        "us.anthropic.claude-sonnet-4-6",
    )

    prompt = f"""
You are a portfolio analytics assistant.

Use only the portfolio context below. If the answer is not available in the context, say that the information is not available in the current portfolio data.

Portfolio context:
{context}

User question:
{question}

Answer in Spanish, clearly and briefly.
"""

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 700,
        "temperature": 0.2,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
    }

    try:
        logger.info(f"Iniciando llamada a Bedrock ({model_id}) en la región {region}...")
        client = boto3.client("bedrock-runtime", region_name=region)

        response = client.invoke_model(
            modelId=model_id,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )

        result = json.loads(response["body"].read())
        return result["content"][0]["text"]

    except Exception as exc:
        logger.error(f"Error inesperado al procesar chat con Bedrock: {exc}", exc_info=True)
        return (
            "No pude consultar Bedrock en este momento. "
            "El dashboard sigue funcionando con los datos del portafolio. "
            f"Detalle técnico: {type(exc).__name__}: {exc}"
        )