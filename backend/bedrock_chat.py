from __future__ import annotations

import json
import os

import boto3


def ask_bedrock(question: str, context: str = "") -> str:
    question = (question or "").strip()

    if not question:
        return "Escribe una pregunta sobre el portafolio."

    region = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1"))
    model_id = os.getenv(
        "BEDROCK_MODEL_ID",
        "anthropic.claude-3-haiku-20240307-v1:0",
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
        return (
            "No pude consultar Bedrock en este momento. "
            "El dashboard sigue funcionando con los datos del portafolio. "
            f"Detalle técnico: {type(exc).__name__}: {exc}"
        )
