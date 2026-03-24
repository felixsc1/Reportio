from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class CashflowKpis:
    cash_in: float
    cash_out: float
    net_cashflow: float
    open_receivables: float
    open_payables: float
    cashflow_mom_pct: float


def compute_kpis(df: pd.DataFrame) -> CashflowKpis:
    if df.empty:
        return CashflowKpis(0, 0, 0, 0, 0, 0)

    cash_in = float(df.loc[df["type"] == "in", "amount"].sum())
    cash_out = float(df.loc[df["type"] == "out", "amount"].sum())
    open_receivables = float(df.loc[df["status"] == "open_receivable", "amount"].sum())
    open_payables = float(df.loc[df["status"] == "open_payable", "amount"].sum())
    net = cash_in - cash_out

    monthly = df.groupby(df["date"].dt.to_period("M"))["signed_amount"].sum()
    if len(monthly) > 1 and monthly.iloc[-2] != 0:
        mom = ((monthly.iloc[-1] - monthly.iloc[-2]) / abs(monthly.iloc[-2])) * 100
    else:
        mom = 0.0

    return CashflowKpis(cash_in, cash_out, net, open_receivables, open_payables, mom)
