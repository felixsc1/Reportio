from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def build_cashflow_trend(df: pd.DataFrame) -> go.Figure:
    monthly = (
        df.assign(month=df["date"].dt.to_period("M").astype(str))
        .groupby("month", as_index=False)["signed_amount"]
        .sum()
    )
    fig = px.bar(monthly, x="month", y="signed_amount", title="Monthly Net Cashflow")
    fig.update_layout(template="plotly_dark")
    return fig


def build_invoices_status_chart(invoices_df: pd.DataFrame) -> go.Figure:
    status = invoices_df.groupby("status", as_index=False).size()
    fig = px.pie(status, values="size", names="status", title="Invoice Status Split")
    fig.update_layout(template="plotly_dark")
    return fig
