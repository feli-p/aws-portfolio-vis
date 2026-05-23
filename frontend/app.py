from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import plotly.express as px
import streamlit as st

from backend.bedrock_chat import ask_bedrock
from backend.data_loader import (
    get_categorical_columns,
    get_datetime_columns,
    get_numeric_columns,
    infer_date_column,
    infer_group_column,
    infer_return_column,
    infer_value_column,
    load_asset_history,
    load_transactions,
    summarize_for_chat,
)


st.set_page_config(
    page_title="Portfolio Analytics Dashboard",
    page_icon="📊",
    layout="wide",
)

st.title("Portfolio Analytics Dashboard")
st.caption("Dashboard conectado a Athena")

with st.spinner("Leyendo datos desde Athena..."):
    try:
        transactions = load_transactions()
        asset_history = load_asset_history()
    except Exception as exc:
        st.error("No se pudieron leer los datos desde Athena.")
        st.code(str(exc))
        st.stop()

st.sidebar.header("Filtros dinámicos")

categorical_filters = get_categorical_columns(transactions, max_unique=40)

filtered_transactions = transactions.copy()

for col in categorical_filters[:8]:
    options = sorted(filtered_transactions[col].dropna().astype(str).unique().tolist())

    selected = st.sidebar.multiselect(
        label=col,
        options=options,
        default=options,
    )

    if selected:
        filtered_transactions = filtered_transactions[
            filtered_transactions[col].astype(str).isin(selected)
        ]

value_col = infer_value_column(filtered_transactions)
group_col = infer_group_column(filtered_transactions)

history = asset_history.copy()
date_col = infer_date_column(history)
return_col = infer_return_column(history)
history_value_col = infer_value_column(history)
history_group_col = infer_group_column(history)

if date_col and date_col in history.columns:
    history[date_col] = pd.to_datetime(history[date_col], errors="coerce")
    history = history.dropna(subset=[date_col])

    if not history.empty:
        min_date = history[date_col].min().date()
        max_date = history[date_col].max().date()

        date_range = st.sidebar.date_input(
            "Periodo histórico",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
        )

        if isinstance(date_range, tuple) and len(date_range) == 2:
            start_date, end_date = date_range
            history = history[
                (history[date_col].dt.date >= start_date)
                & (history[date_col].dt.date <= end_date)
            ]

st.subheader("Resumen de datos reales")

c1, c2, c3, c4 = st.columns(4)

c1.metric("Registros transactions", f"{len(filtered_transactions):,}")
c2.metric("Columnas transactions", f"{len(filtered_transactions.columns):,}")
c3.metric("Registros history", f"{len(history):,}")
c4.metric("Columnas history", f"{len(history.columns):,}")

if value_col:
    c5, c6, c7, c8 = st.columns(4)
    c5.metric(f"Total {value_col}", f"{filtered_transactions[value_col].sum():,.2f}")
    c6.metric(f"Promedio {value_col}", f"{filtered_transactions[value_col].mean():,.2f}")
    c7.metric(f"Máximo {value_col}", f"{filtered_transactions[value_col].max():,.2f}")
    c8.metric(f"Mínimo {value_col}", f"{filtered_transactions[value_col].min():,.2f}")

st.divider()

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    [
        "Transactions",
        "Asset History",
        "Performance",
        "Exploración",
        "Chatbot",
    ]
)

with tab1:
    st.subheader("Transactions desde Athena")

    st.write("Columnas reales detectadas:")
    st.code(", ".join(filtered_transactions.columns.tolist()))

    st.dataframe(
        filtered_transactions,
        width="stretch",
        hide_index=True,
    )

    if group_col and value_col:
        st.subheader(f"Distribución de {value_col} por {group_col}")

        grouped = (
            filtered_transactions.groupby(group_col, dropna=False)[value_col]
            .sum()
            .reset_index()
            .sort_values(value_col, ascending=False)
            .head(20)
        )

        fig = px.bar(
            grouped,
            x=group_col,
            y=value_col,
            text_auto=True,
            title=f"{value_col} por {group_col}",
        )
        fig.update_layout(xaxis_title=group_col, yaxis_title=value_col)
        st.plotly_chart(fig, width="stretch")

with tab2:
    st.subheader("Asset History desde Athena")

    st.write("Columnas reales detectadas:")
    st.code(", ".join(history.columns.tolist()))

    st.dataframe(
        history,
        width="stretch",
        hide_index=True,
    )

with tab3:
    st.subheader("Performance histórico")

    if not date_col:
        st.warning("No se detectó columna de fecha en asset_history.")
    elif not return_col and not history_value_col:
        st.warning("No se detectó columna de rendimiento ni columna numérica para graficar historia.")
    else:
        if return_col:
            st.write(f"Usando columna de rendimiento detectada: `{return_col}`")

            perf = history.copy()
            perf[return_col] = pd.to_numeric(perf[return_col], errors="coerce")
            perf = perf.dropna(subset=[date_col, return_col])

            if history_group_col and history_group_col != date_col:
                monthly = (
                    perf.groupby([date_col, history_group_col], dropna=False)[return_col]
                    .mean()
                    .reset_index()
                    .sort_values(date_col)
                )

                fig_return = px.line(
                    monthly,
                    x=date_col,
                    y=return_col,
                    color=history_group_col,
                    markers=True,
                    title=f"{return_col} por {history_group_col}",
                )
            else:
                monthly = (
                    perf.groupby(date_col, dropna=False)[return_col]
                    .mean()
                    .reset_index()
                    .sort_values(date_col)
                )

                fig_return = px.line(
                    monthly,
                    x=date_col,
                    y=return_col,
                    markers=True,
                    title=f"{return_col} histórico",
                )

            fig_return.update_layout(xaxis_title=date_col, yaxis_title=return_col)
            st.plotly_chart(fig_return, width="stretch")

        if history_value_col:
            st.write(f"Usando columna de valor detectada: `{history_value_col}`")

            hist_value = history.copy()
            hist_value[history_value_col] = pd.to_numeric(hist_value[history_value_col], errors="coerce")
            hist_value = hist_value.dropna(subset=[date_col, history_value_col])

            value_ts = (
                hist_value.groupby(date_col, dropna=False)[history_value_col]
                .sum()
                .reset_index()
                .sort_values(date_col)
            )

            fig_value = px.area(
                value_ts,
                x=date_col,
                y=history_value_col,
                title=f"Evolución histórica de {history_value_col}",
            )
            fig_value.update_layout(xaxis_title=date_col, yaxis_title=history_value_col)
            st.plotly_chart(fig_value, width="stretch")

with tab4:
    st.subheader("Exploración automática")

    numeric_cols = get_numeric_columns(filtered_transactions)
    categorical_cols = get_categorical_columns(filtered_transactions, max_unique=80)

    left, right = st.columns(2)

    with left:
        selected_numeric = st.selectbox(
            "Variable numérica",
            options=numeric_cols,
            index=0 if numeric_cols else None,
        )

    with right:
        selected_group = st.selectbox(
            "Variable categórica",
            options=categorical_cols,
            index=0 if categorical_cols else None,
        )

    if numeric_cols and categorical_cols and selected_numeric and selected_group:
        auto_group = (
            filtered_transactions.groupby(selected_group, dropna=False)[selected_numeric]
            .sum()
            .reset_index()
            .sort_values(selected_numeric, ascending=False)
            .head(20)
        )

        fig_auto = px.bar(
            auto_group,
            x=selected_group,
            y=selected_numeric,
            text_auto=True,
            title=f"{selected_numeric} por {selected_group}",
        )
        st.plotly_chart(fig_auto, width="stretch")
    else:
        st.info("No hay suficientes columnas numéricas/categóricas para exploración automática.")

with tab5:
    st.subheader("Chatbot sobre datos reales")

    context = summarize_for_chat(filtered_transactions, history)

    question = st.text_input(
        "Pregunta sobre el portafolio",
        placeholder="Ejemplo: ¿qué columna concentra mayor valor o cómo se comporta el rendimiento?",
    )

    if st.button("Preguntar"):
        if not question.strip():
            st.warning("Escribe una pregunta.")
        else:
            with st.spinner("Consultando Bedrock..."):
                answer = ask_bedrock(question, context)
            st.markdown(answer)

    with st.expander("Contexto enviado al chatbot"):
        st.text(context)
