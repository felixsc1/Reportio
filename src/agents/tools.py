from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from src.agents.sandbox import execute_restricted


def get_cashflow_summary(start_date: str, end_date: str, group_by: str = "month") -> dict[str, Any]:
    data = [
        {"date": "2026-01-10", "signed_amount": 12000},
        {"date": "2026-01-13", "signed_amount": -4300},
        {"date": "2026-02-10", "signed_amount": 9800},
        {"date": "2026-02-15", "signed_amount": -5100},
    ]
    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["date"])
    mask = (df["date"] >= pd.Timestamp(start_date)) & (df["date"] <= pd.Timestamp(end_date))
    period = "M" if group_by == "month" else "D"
    grouped = df.loc[mask].groupby(df["date"].dt.to_period(period))["signed_amount"].sum()
    return {"group_by": group_by, "rows": grouped.reset_index().astype(str).to_dict(orient="records")}


def get_invoices(filter_dict: dict[str, Any]) -> list[dict[str, Any]]:
    invoices = [
        {"document_nr": "INV-1001", "contact_name": "Acme AG", "status": "paid", "amount": 12000},
        {"document_nr": "INV-1002", "contact_name": "Northwind GmbH", "status": "open", "amount": 3200},
        {"document_nr": "INV-1003", "contact_name": "Contoso AG", "status": "paid", "amount": 9800},
    ]
    status = str(filter_dict.get("status", "")).lower()
    if status:
        invoices = [i for i in invoices if i["status"].lower() == status]
    return invoices


def get_open_receivables() -> dict[str, Any]:
    rows = get_invoices({"status": "open"})
    total = sum(float(row["amount"]) for row in rows)
    return {"total_open_receivables": total, "count": len(rows), "rows": rows}


def list_available_data() -> dict[str, list[str]]:
    return {
        "finance": ["cashflow_summary", "invoices", "open_receivables"],
        "analytics": ["dynamic_table", "dynamic_chart"],
    }


def create_dynamic_table(query: str) -> list[dict[str, Any]]:
    base_df = pd.DataFrame(get_invoices({}))
    code = (
        "result = invoices.groupby('status', as_index=False)['amount'].sum()"
        if "status" in query.lower()
        else "result = invoices.sort_values('amount', ascending=False)"
    )
    result = execute_restricted(code, {"invoices": base_df})
    if isinstance(result, pd.DataFrame):
        return result.to_dict(orient="records")
    return [{"message": "No table result"}]


def create_chart(query: str) -> dict[str, Any]:
    base_df = pd.DataFrame(get_invoices({}))
    code = (
        "result = px.bar(invoices, x='document_nr', y='amount', color='status', title='Invoice Amounts')"
        if "invoice" in query.lower()
        else "result = px.pie(invoices, values='amount', names='status', title='Status Split')"
    )
    result = execute_restricted(code, {"invoices": base_df})
    if result is None:
        return {"error": "No chart produced"}
    return {"plotly_json": result.to_plotly_json()}
