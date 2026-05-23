import pandas as pd
import numpy as np
import plotly.graph_objects as go

from src.common.logging_utils import setup_logger

logger = setup_logger(__name__)


def consolidate_portfolio_history(df: pd.DataFrame) -> pd.DataFrame:
    """
    Agrupa un historial mezclado de assets por fecha para calcular las métricas agregadas de todo el portafolio.
    """
    if df.empty:
        return pd.DataFrame(columns=["market_value", "daily_pl", "daily_irr"])
        
    # Asegurar orden cronológico
    df = df.sort_values("date")
    
    # Agrupamos por fecha para consolidar el valor de mercado y el P&L diario
    consolidated = df.groupby("date").agg(
        market_value=("market_value", "sum"),
        daily_pl=("daily_pl", "sum")
    ).copy()
    
    # Calcular el retorno diario implícito del portafolio consolidado:
    # Retorno_t = P&L_t / (Valor_t - P&L_t)
    daily_acb = consolidated["market_value"] - consolidated["daily_pl"]
    consolidated["daily_return"] = np.where(
        daily_acb > 0, # No debería ocurrir bajo nuestra construcción de datos
        consolidated["daily_pl"] / daily_acb,
        0.0
    )
    
    return consolidated


def calculate_annualized_volatility(daily_returns: pd.Series, periods_per_year: int = 252) -> float:
    """Calcula la volatilidad anualizada a partir de los retornos diarios."""
    if daily_returns.empty or len(daily_returns) < 2:
        logger.error("Muy pocos datos para calcular volatilidad.")
        return 0.0
    return float(daily_returns.std() * np.sqrt(periods_per_year))


def calculate_max_drawdown(market_value_series: pd.Series) -> float:
    """Calcula la máxima caída histórica del portafolio."""
    if market_value_series.empty:
        logger.error("Muy pocos datos para calcular máxima caída.")
        return 0.0
    # Calcular los máximos acumulados móviles
    rolling_max = market_value_series.cummax()
    # Calcular caídas porcentuales respecto al máximo anterior
    drawdowns = (market_value_series - rolling_max) / rolling_max
    return float(drawdowns.min())


def generate_portfolio_report(df_athena: pd.DataFrame, risk_free_rate: float = 0.0) -> dict:
    """
    Toma el DataFrame crudo de Athena, lo consolida y genera el resumen
    ejecutivo de métricas que usará tanto la UI (tarjetas) como el LLM de Bedrock.
    """
    if df_athena.empty:
        return {
            "initial_value": 0.0,
            "final_value": 0.0,
            "total_return_pct": 0.0,
            "annualized_volatility": 0.0,
            "max_drawdown": 0.0,
            "sharpe_ratio": 0.0
        }
        
    df_portfolio = consolidate_portfolio_history(df_athena)
    
    initial_val = float(df_portfolio["market_value"].iloc[0])
    final_val = float(df_portfolio["market_value"].iloc[-1])
    
    # Rendimiento total simple en el periodo seleccionado
    total_return = float((1 + df_portfolio["daily_return"]).prod() - 1.0)

    # Ganancia/Pérdida no realizada total en el periodo
    unrealized_pnl = float(df_portfolio["daily_pl"].sum())
    
    # Volatilidad anualizada
    vol = calculate_annualized_volatility(df_portfolio["daily_return"])
    
    # Sharpe Ratio
    rf_daily = (1 + risk_free_rate) ** (1 / 252) - 1
    excess_daily_returns = df_portfolio["daily_return"] - rf_daily
    annualized_excess_return = excess_daily_returns.mean() * 252
    
    vol = calculate_annualized_volatility(df_portfolio["daily_return"])
    sharpe = annualized_excess_return / vol if vol > 0 else 0.0
    
    # Max Drawdown
    max_dd = calculate_max_drawdown(df_portfolio["market_value"])
    
    return {
        "initial_value": initial_val,
        "final_value": final_val,
        "total_return_pct": total_return,
        "unrealized_pnl": unrealized_pnl,
        "annualized_volatility": vol,
        "max_drawdown": max_dd,
        "sharpe_ratio": sharpe
    }


def generate_cumulative_return_chart(df_athena: pd.DataFrame) -> go.Figure:
    """
    Consolida el historial, calcula el rendimiento acumulado en porcentaje y genera una figura de Plotly interactiva.
    """
    fig = go.Figure()
    
    if df_athena.empty:
        logger.error("Retorno acumulado: No hay datos disponibles para graficar.")
        fig.update_layout(title="No hay datos disponibles para graficar")
        return fig
        
    df_portfolio = consolidate_portfolio_history(df_athena)
    
    # Calcular rendimiento acumulado en porcentaje
    df_portfolio["cumulative_return_pct"] = ((1 + df_portfolio["daily_return"]).cumprod() - 1.0) * 100
    
    # Crear la línea de evolución
    fig.add_trace(go.Scatter(
        x=df_portfolio.index,
        y=df_portfolio["cumulative_return_pct"],
        mode="lines",
        name="Rendimiento Acumulado",
        line=dict(color="#0068c9", width=2),
        hovertemplate="Fecha: %{x}<br>Rendimiento: %{y:.2f}%<extra></extra>"
    ))
    
    # Configurar diseño (layout) óptimo para la UI
    fig.update_layout(
        title="Evolución del Rendimiento Acumulado",
        xaxis_title="Fecha",
        yaxis_title="Rendimiento (%)",
        margin=dict(l=40, r=40, t=40, b=40),
        hovermode="x unified",
        template="plotly_white"
    )
    
    return fig