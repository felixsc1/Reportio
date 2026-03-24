from __future__ import annotations

import pandas as pd

from src.dashboard.kpis import compute_kpis


def test_compute_kpis_basic():
    df = pd.DataFrame(
        [
            {"date": "2026-01-01", "type": "in", "amount": 1000, "signed_amount": 1000, "status": "paid"},
            {"date": "2026-01-02", "type": "out", "amount": 200, "signed_amount": -200, "status": "paid"},
            {"date": "2026-01-03", "type": "in", "amount": 300, "signed_amount": 300, "status": "open_receivable"},
            {"date": "2026-01-04", "type": "out", "amount": 150, "signed_amount": -150, "status": "open_payable"},
        ]
    )
    df["date"] = pd.to_datetime(df["date"])
    result = compute_kpis(df)
    assert result.cash_in == 1300
    assert result.cash_out == 350
    assert result.net_cashflow == 950
