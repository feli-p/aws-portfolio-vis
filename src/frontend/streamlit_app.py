import os
from datetime import datetime, timedelta
import streamlit as st
import pandas as pd
import plotly.express as px

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.backend.aws_athena import load_portfolio_metadata, query_asset_history
from src.backend.financial_math import generate_portfolio_report, generate_cumulative_return_chart
from src.common.logging_utils import setup_logger
from src.backend.bedrock_chat import ask_bedrock, format_portfolio_context

logger = setup_logger(__name__)

# Configuración de la página
st.set_page_config(
    page_title="Dashboard de Portafolio",
    page_icon="📊",
    layout="wide"
)

st.title("Dashboard para análisis de portafolio")
st.caption("Dashboard conectado a Athena")
st.subheader("Análisis dinámico de rendimiento y volatilidad")

# Cargar Metadata para Filtros (Caché de Streamlit para evitar llamadas redundantes a Athena)
@st.cache_data(ttl=600)  # Mantiene la caché por 10 minutos
def get_cached_metadata():
    logger.info("Cargando metadatos de cuentas y activos desde Athena...")
    return load_portfolio_metadata()

with st.spinner("Leyendo datos desde Athena..."):
    try:
        available_accounts, available_assets = get_cached_metadata()
    except Exception as e:
        st.error("Error al conectar con el catálogo de datos de AWS Glue.")
        logger.error(f"Fallo en carga de metadatos: {e}")
        st.code(str(e))
        st.stop()

# Barra Lateral (Filtros)
st.sidebar.header("Filtros del Portafolio")

# Filtro de Cuentas
selected_accounts = st.sidebar.multiselect(
    "Cuentas",
    options=available_accounts,
    default=available_accounts,
    help="Selecciona una o más cuentas para consolidar."
)

# Filtro de Activos
selected_assets = st.sidebar.multiselect(
    "Activos",
    options=available_assets,
    default=available_assets,
    help="Filtra por activos específicos dentro de las cuentas."
)

# Filtro de Fechas (Rango predeterminado: Últimos 12 meses)
default_start = datetime.now() - timedelta(days=365)
default_end = datetime.now()

date_range = st.sidebar.date_input(
    "Rango de tiempo",
    value=(default_start, default_end),
    max_value=default_end,
    help="Selecciona el rango de fechas de interés."
)

# Variable para controlar si tenemos datos listos para graficar
df_return_graph = None

# Procesamiento de la consulta al hacer clic en un botón
if st.sidebar.button("Ejecutar Análisis", type="primary"):
    # Validar que se haya seleccionado un rango de fechas completo (Inicio y Fin)
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_dt, end_dt = date_range
        
        # Conversión al formato esperado aws_athena ("%d/%m/%Y")
        start_str = start_dt.strftime("%d/%m/%Y")
        end_str = end_dt.strftime("%d/%m/%Y")
        
        st.info(f"Consultando Athena desde {start_str} hasta {end_str}...")
        logger.info(f"Consultando Athena desde {start_str} hasta {end_str}...")

        # Llamada a la capa de datos
        with st.spinner("Buscando en el Data Lakehouse de S3..."):
            df_athena = query_asset_history(
                start_date=start_str,
                end_date=end_str,
                accounts=selected_accounts,
                assets=selected_assets
            )
            
        if df_athena.empty:
            st.warning("No se encontraron registros para los filtros seleccionados.")
            logger.warning("No se encontraron registros para los filtros seleccionados.")
        else:
            # Generar Reporte de Métricas Financieras
            report = generate_portfolio_report(df_athena)
            
            # Guardamos el reporte y dataframe en el estado de la sesión de Streamlit
            st.session_state["last_report"] = report
            st.session_state["last_df_athena"] = df_athena
            df_return_graph = df_athena
    else:
        st.error("Por favor, selecciona un rango de fechas válido (Fecha de inicio y Fecha de fin).")

# Si no se presionó el botón en esta ejecución, pero existen datos guardados en la sesión, los usamos
if df_return_graph is None and "last_df_athena" in st.session_state:
    df_return_graph = st.session_state["last_df_athena"]
    report = st.session_state["last_report"]

if df_return_graph is not None:
    st.markdown("---")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="Valor Mercado del Portafolio", 
            value=f"${report['final_value']:,.2f}",
            delta=f"${df_return_graph['daily_pl'].sum():,.2f} P&L Total"
        )
    with col2:
        st.metric(
            label="Rendimiento acumulado", 
            value=f"{report['total_return_pct'] * 100:.2f}%"
        )
    with col3:
        st.metric(
            label="Volatilidad anualizada", 
            value=f"{report['annualized_volatility'] * 100:.2f}%",
            help="Calculada de los retornos diarios del portafolio consolidado."
        )
    with col4:
        st.metric(
            label="Sharpe Ratio", 
            value=f"{report['sharpe_ratio']:.2f}",
            help="Asume que no hay tasa libre de riesgo."
        )
        
    st.markdown("---")

    st.divider()

    tab1, tab2 = st.tabs(
        [
            "Rendimiento acumulado",
            "Chatbot",
        ]
    )
    
    with tab1:
        st.subheader("Evolución del rendimiento acumulado (%)")
        
        # Checkbox de Benchmark arriba del gráfico
        comparar_benchmark = st.checkbox(
            "Comparar con Benchmark (S&P 500)", 
            value=False,
            help="Compara contra el rendimiento acumulado del S&P 500 (^GSPC) vía yfinance."
        )
        benchmark_ticker = "SPX" if comparar_benchmark else None
        
        # Renderizar Gráfico de Plotly
        with st.spinner("Descargando datos del Benchmark..." if benchmark_ticker else "Generando gráfico..."):
            fig_cumulative = generate_cumulative_return_chart(df_return_graph, benchmark=benchmark_ticker)
            
        st.plotly_chart(fig_cumulative, use_container_width=True)
    with tab2:
        st.subheader("Chatbot sobre los datos")

        question = st.text_input(
            "Pregunta sobre el portafolio",
            placeholder="Ejemplo: ¿qué columna concentra mayor valor o cómo se comporta el rendimiento?",
        )

        context = format_portfolio_context(st.session_state["last_report"], st.session_state["last_df_athena"])

        if st.button("Preguntar"):
            if not question.strip():
                st.warning("Escribe una pregunta.")
            else:
                with st.spinner("Consultando Bedrock..."):
                    answer = ask_bedrock(question, context)
                st.markdown(answer)

        with st.expander("Contexto enviado al chatbot"):
            st.text(context)

else:
    # Mensaje inicial si la sesión está totalmente limpia
    #if not st.sidebar.button("Ejecutar Análisis", type="primary"): 
    #    st.info("Configura los filtros en la barra lateral y haz clic en 'Ejecutar Análisis' para comenzar.")
    st.info("Configura los filtros en la barra lateral y haz clic en 'Ejecutar Análisis' para comenzar.")