from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ProfitAndLoss:
    income: float
    expenses: float
    net_profit: float
    by_account: pd.DataFrame


def _classify_account(account_no: str | None) -> str:
    if not account_no:
        return "unknown"
    s = str(account_no).strip()
    if not s:
        return "unknown"
    # Swiss charts of accounts commonly use:
    # - 3xxx revenue (Ertrag)
    # - 4xxx..8xxx costs/expenses (Aufwand)
    if s.startswith("3"):
        return "income"
    if s[0] in {"4", "5", "6", "7", "8"}:
        return "expense"
    return "unknown"


def compute_profit_and_loss(
    *,
    journal_rows: list[dict],
    accounts_rows: list[dict] | None = None,
) -> ProfitAndLoss:
    journal_df = pd.DataFrame(journal_rows or [])
    if journal_df.empty:
        empty = pd.DataFrame(columns=["account_id", "account_no", "account_name", "category", "amount"])
        return ProfitAndLoss(0.0, 0.0, 0.0, empty)

    journal_df["amount"] = pd.to_numeric(journal_df.get("amount"), errors="coerce").fillna(0.0)
    journal_df["debit_account_id"] = pd.to_numeric(journal_df.get("debit_account_id"), errors="coerce")
    journal_df["credit_account_id"] = pd.to_numeric(journal_df.get("credit_account_id"), errors="coerce")

    debit = (
        journal_df.dropna(subset=["debit_account_id"])[["debit_account_id", "amount"]]
        .rename(columns={"debit_account_id": "account_id"})
        .assign(debit_amount=lambda d: d["amount"], credit_amount=0.0)
        .drop(columns=["amount"])
    )
    credit = (
        journal_df.dropna(subset=["credit_account_id"])[["credit_account_id", "amount"]]
        .rename(columns={"credit_account_id": "account_id"})
        .assign(debit_amount=0.0, credit_amount=lambda d: d["amount"])
        .drop(columns=["amount"])
    )
    amounts = pd.concat([debit, credit], ignore_index=True)
    grouped = amounts.groupby("account_id", as_index=False)[["debit_amount", "credit_amount"]].sum()

    # Optional: enrich with chart of accounts so we can show account_no + name.
    accounts_df = pd.DataFrame(accounts_rows or [])
    if not accounts_df.empty and "id" in accounts_df.columns:
        accounts_df = accounts_df.rename(columns={"id": "account_id"})
        accounts_df["account_id"] = pd.to_numeric(accounts_df["account_id"], errors="coerce")
        accounts_df["account_no"] = accounts_df.get("account_no").astype(str)
        accounts_df["account_name"] = accounts_df.get("name").astype(str)
        grouped = grouped.merge(
            accounts_df[["account_id", "account_no", "account_name"]],
            how="left",
            on="account_id",
        )
    else:
        grouped["account_no"] = None
        grouped["account_name"] = None

    grouped["category"] = grouped["account_no"].apply(_classify_account)

    # Convert to P&L signed amounts:
    # - income accounts: credit - debit
    # - expense accounts: debit - credit
    grouped["amount"] = 0.0
    income_mask = grouped["category"] == "income"
    expense_mask = grouped["category"] == "expense"
    grouped.loc[income_mask, "amount"] = grouped.loc[income_mask, "credit_amount"] - grouped.loc[income_mask, "debit_amount"]
    grouped.loc[expense_mask, "amount"] = grouped.loc[expense_mask, "debit_amount"] - grouped.loc[expense_mask, "credit_amount"]

    income_total = float(grouped.loc[income_mask, "amount"].sum())
    expense_total = float(grouped.loc[expense_mask, "amount"].sum())
    net = income_total - expense_total

    by_account = grouped[["account_id", "account_no", "account_name", "category", "amount"]].copy()
    by_account = by_account.sort_values(["category", "amount"], ascending=[True, False], kind="stable")

    return ProfitAndLoss(income_total, expense_total, net, by_account)

