from __future__ import annotations

import pandas as pd


def filter_invoices(
    invoices_df: pd.DataFrame,
    status: str | None = None,
    min_amount: float | None = None,
    search_text: str | None = None,
) -> pd.DataFrame:
    df = invoices_df.copy()
    if status:
        df = df[df["status"].str.lower() == status.lower()]
    if min_amount is not None:
        df = df[df["amount"] >= min_amount]
    if search_text:
        search_text = search_text.lower()
        df = df[
            df["contact_name"].str.lower().str.contains(search_text, na=False)
            | df["document_nr"].astype(str).str.lower().str.contains(search_text, na=False)
        ]
    return df
