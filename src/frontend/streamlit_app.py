# src/main.py
from datetime import datetime, timedelta
import streamlit as st

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.backend.aws_athena import load_portfolio_metadata, query_asset_history
from src.backend.financial_math import generate_portfolio_report, generate_cumulative_return_chart
from src.common.logging_utils import setup_logger

logger = setup_logger(__name__)

import streamlit as st

# Configuración básica de la página
st.set_page_config(
    page_title="Prueba de Portafolio",
    page_icon="📊",
    layout="centered"
)

logger.info("Hola desde Streamlit!")

# Título y texto de prueba
st.title("¡Hola desde Docker!")
st.write("prueba")

# Un componente interactivo simple para validar que los WebSockets responden bien
if st.button("Haz clic aquí"):
    st.success("¡Funcionó!")