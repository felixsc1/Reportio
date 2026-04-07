from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from src.config.settings import Settings, get_settings
from src.dashboard.charts import build_invoices_status_chart
from src.dashboard.kpis import compute_kpis
from src.dashboard.profit_and_loss import compute_profit_and_loss
from src.dashboard.tables import filter_invoices
from src.integrations.bexio.client import BexioClient


def _get_date_range(preset: str) -> tuple[date, date]:
    today = date.today()
    if preset == "This Month":
        return date(today.year, today.month, 1), today
    if preset == "QTD":
        q_start_month = ((today.month - 1) // 3) * 3 + 1
        return date(today.year, q_start_month, 1), today
    if preset == "YTD":
        return date(today.year, 1, 1), today
    return date(today.year, today.month, 1), today


def _dummy_transactions() -> pd.DataFrame:
    rows = [
        {"date": "2026-01-10", "type": "in", "amount": 12000, "signed_amount": 12000, "status": "paid"},
        {"date": "2026-01-13", "type": "out", "amount": 4300, "signed_amount": -4300, "status": "paid"},
        {"date": "2026-02-10", "type": "in", "amount": 9800, "signed_amount": 9800, "status": "paid"},
        {"date": "2026-02-15", "type": "out", "amount": 5100, "signed_amount": -5100, "status": "paid"},
        {"date": "2026-03-03", "type": "in", "amount": 3200, "signed_amount": 3200, "status": "open_receivable"},
        {"date": "2026-03-09", "type": "out", "amount": 2800, "signed_amount": -2800, "status": "open_payable"},
    ]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df


def _dummy_invoices() -> pd.DataFrame:
    rows = [
        {"document_nr": "INV-1001", "contact_name": "Acme AG", "status": "paid", "amount": 12000, "date": "2026-01-10"},
        {"document_nr": "INV-1002", "contact_name": "Northwind GmbH", "status": "open", "amount": 3200, "date": "2026-03-03"},
        {"document_nr": "INV-1003", "contact_name": "Contoso AG", "status": "paid", "amount": 9800, "date": "2026-02-10"},
    ]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df


def _has_bexio_pat(settings: Settings) -> bool:
    return bool(settings.bexio_pat.strip())


def _render_bexio_auth_panel(settings: Settings) -> None:
    st.subheader("Bexio Connection")
    if _has_bexio_pat(settings):
        st.success("Bexio PAT configured.")
    else:
        st.error("Missing `BEXIO_PAT`. Add it to `.env` and restart the app.")
    st.caption("Authentication mode: Personal Access Token (PAT).")


def _load_real_invoices(settings: Settings) -> pd.DataFrame | None:
    if not _has_bexio_pat(settings):
        return None
    client = BexioClient(settings)
    try:
        invoices = client.list_invoices()
    except Exception as exc:
        st.warning(f"Connected but failed to load invoices from Bexio: {exc}")
        st.info(
            "💡 **Troubleshooting tips:**\n"
            "• Ensure `BEXIO_PAT` is valid and not expired/revoked\n"
            "• Verify your user account has access to invoices in Bexio\n"
            "• Check the console for detailed API error logs (now improved)"
        )
        # Clear cache on error so next attempt doesn't reuse a failed response
        try:
            client.clear_cache()
        except Exception:
            pass
        return None
    if not invoices:
        return pd.DataFrame(columns=["document_nr", "contact_name", "status", "amount", "date"])

    df = pd.DataFrame(invoices)
    raw_columns = set(df.columns)

    # If Bexio returns different field names than we expect (e.g. no `amount`/`status`/`contact_name`),
    # we dump a small sample locally to quickly reverse engineer the schema.
    if not st.session_state.get("bexio_invoice_schema_dumped", False) and (
        ("amount" not in raw_columns) or ("status" not in raw_columns) or ("contact_name" not in raw_columns)
    ):
        try:
            repo_root = Path(__file__).resolve().parents[2]
            out_dir = repo_root / "bexio_debug"
            out_dir.mkdir(parents=True, exist_ok=True)

            sample = invoices[0] if invoices else {}
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            out_path = out_dir / f"invoices_schema_sample_{ts}.json"
            debug_payload = {
                "count": len(invoices),
                "sample_keys": sorted(list(sample.keys())),
                # Ensure it stays JSON-serializable (datetime strings etc).
                "sample": sample,
            }
            out_path.write_text(json.dumps(debug_payload, default=str, ensure_ascii=True, indent=2), encoding="utf-8")
            st.session_state["bexio_invoice_schema_dumped"] = True
            st.info(f"Debug: wrote Bexio invoice schema sample to `{out_path}`")
        except Exception:
            # Never block dashboard rendering due to debug dump failures.
            pass

    # Prefer the invoice validity date (changes per document), not `updated_at` (often clustered recently).
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    elif "is_valid_from" in df.columns:
        df["date"] = pd.to_datetime(df["is_valid_from"], errors="coerce")
    elif "is_valid_to" in df.columns:
        df["date"] = pd.to_datetime(df["is_valid_to"], errors="coerce")
    elif "updated_at" in df.columns:
        df["date"] = pd.to_datetime(df["updated_at"], errors="coerce")
    else:
        df["date"] = pd.Timestamp.utcnow()

    # Best-effort mapping from Bexio fields to our dashboard schema.
    if "document_nr" not in df.columns:
        for candidate in ["document_nr", "reference", "kb_invoice_id", "id"]:
            if candidate in df.columns:
                df["document_nr"] = df[candidate].astype(str)
                break
        else:
            df["document_nr"] = df.index.astype(str)

    if "contact_name" not in df.columns:
        if "contact_address" in df.columns:
            # Bexio typically prefixes the address block with the company/contact name.
            df["contact_name"] = (
                df["contact_address"]
                .fillna("")
                .astype(str)
                .str.split(r"\r?\n")
                .str[0]
                .replace("", "Unknown")
            )
        elif "contact_id" in df.columns:
            df["contact_name"] = "Contact " + df["contact_id"].astype(str)
        else:
            df["contact_name"] = "Unknown"

    if "amount" not in df.columns:
        # For cashflow / receivables KPIs, outstanding amount is typically driven by remaining payments.
        # We will later override paid invoices with received payments.
        for candidate in [
            "total_remaining_payments",
            "total_remaining_amount",
            "total_remaining_payment",
            "total",
            "total_net",
            "total_gross",
            "amount",
        ]:
            if candidate in df.columns:
                df["amount"] = pd.to_numeric(df[candidate], errors="coerce").fillna(0.0)
                break
        else:
            df["amount"] = 0.0

    if "status" not in df.columns:
        # Prefer deriving status from remaining/open amounts, which lets us classify paid/open/partially_paid.
        remaining = None
        for candidate in ["total_remaining_payments", "total_remaining_amount", "total_remaining_payment"]:
            if candidate in df.columns:
                remaining = pd.to_numeric(df[candidate], errors="coerce").fillna(0.0)
                break

        received = None
        for candidate in ["total_received_payments", "total_received_amount", "total_received_payment"]:
            if candidate in df.columns:
                received = pd.to_numeric(df[candidate], errors="coerce").fillna(0.0)
                break

        if remaining is not None:
            df["status"] = "open"
            df.loc[remaining <= 0, "status"] = "paid"
            if received is not None:
                partial_mask = (remaining > 0) & (received > 0)
                df.loc[partial_mask, "status"] = "partially_paid"

            # For paid invoices, the cash-in KPI should reflect received payments, not remaining.
            if received is not None:
                df.loc[df["status"] == "paid", "amount"] = pd.to_numeric(
                    received, errors="coerce"
                ).fillna(0.0)[df["status"] == "paid"]
        else:
            # Fallback: keep something usable for debugging.
            if "kb_item_status_id" in df.columns:
                df["status"] = df["kb_item_status_id"].astype(str)
            else:
                df["status"] = "unknown"

    return df[["document_nr", "contact_name", "status", "amount", "date"]]

def _load_profit_and_loss(
    settings: Settings,
    *,
    start_date: date,
    end_date: date,
) -> tuple[float, float, float, pd.DataFrame] | None:
    if not _has_bexio_pat(settings):
        return None

    client = BexioClient(settings)
    try:
        # Accounts can be cached more aggressively than journal rows (we use TTLCache inside the client).
        accounts = client.list_accounts_v2()
        journal = client.list_accounting_journal(
            from_date=start_date.isoformat(),
            to_date=end_date.isoformat(),
        )
    except Exception as exc:
        st.warning(f"Connected but failed to load Profit & Loss from Bexio: {exc}")
        st.info(
            "Troubleshooting tips:\n"
            "- Ensure your PAT is valid and has access to accounting data\n"
            "- Ensure the user has accounting permissions in Bexio\n"
            "- Regenerate PAT if it might be expired/revoked"
        )
        try:
            client.clear_cache()
        except Exception:
            pass
        return None

    pnl = compute_profit_and_loss(journal_rows=journal, accounts_rows=accounts)
    return pnl.income, pnl.expenses, pnl.net_profit, pnl.by_account


def _invoices_to_transactions(invoices_df: pd.DataFrame) -> pd.DataFrame:
    df = invoices_df.copy()
    status_l = df["status"].astype(str).str.lower()

    # Bexio status values vary by endpoint/version; map common terms.
    is_paid = status_l.isin({"paid", "bezahlt", "done"})
    is_open = status_l.isin({"open", "offen", "pending", "partially_paid"})

    tx_type = pd.Series("in", index=df.index)
    tx_status = pd.Series("paid", index=df.index)
    tx_status.loc[is_open] = "open_receivable"
    tx_status.loc[~(is_paid | is_open)] = "unknown"

    tx = pd.DataFrame(
        {
            "date": pd.to_datetime(df["date"], errors="coerce").fillna(pd.Timestamp.utcnow()),
            "type": tx_type,
            "amount": pd.to_numeric(df["amount"], errors="coerce").fillna(0.0),
            "status": tx_status,
        }
    )
    tx["signed_amount"] = tx["amount"]
    return tx


def _safe_float(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _extract_date(value: object) -> date | None:
    if value is None:
        return None
    try:
        parsed = pd.to_datetime(value, errors="coerce")
    except Exception:
        return None
    if pd.isna(parsed):
        return None
    return parsed.date()


def _is_invoice_paid(invoice: dict[str, object]) -> bool:
    total = _safe_float(invoice.get("total"))
    received = _safe_float(invoice.get("total_received_payments"))
    vouchers = _safe_float(invoice.get("total_credit_vouchers"))
    if total > 0 and (received + vouchers) >= total:
        return True
    return str(invoice.get("status", "")).strip().lower() in {"paid", "bezahlt", "done"}


def _is_bill_paid(bill: dict[str, object]) -> bool:
    total = _safe_float(bill.get("total"))
    paid = _safe_float(bill.get("total_paid"))
    if total > 0 and paid >= total:
        return True
    return str(bill.get("status", "")).strip().lower() in {"paid", "bezahlt", "done"}


def _pat_cache_key(settings: Settings) -> str:
    pat = settings.bexio_pat or ""
    return pat[-12:] if pat else "missing"


@st.cache_data(show_spinner=False)
def _fetch_cashflow_rows(
    start_date_iso: str,
    end_date_iso: str,
    pat_key: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    del pat_key  # only used for Streamlit cache invalidation
    settings = get_settings()
    table_columns = ["Payment Date", "Amount", "Document Nr.", "Contact Name", "Title/Description"]
    if not _has_bexio_pat(settings):
        return pd.DataFrame(columns=table_columns), pd.DataFrame(columns=table_columns)

    client = BexioClient(settings)
    start = date.fromisoformat(start_date_iso)
    end = date.fromisoformat(end_date_iso)

    inflow_rows: list[dict[str, object]] = []
    outflow_rows: list[dict[str, object]] = []

    invoices = client.list_invoices_v2(page_size=500)
    for invoice in invoices:
        if not _is_invoice_paid(invoice):
            continue
        invoice_id = invoice.get("id")
        if invoice_id is None:
            continue
        for payment in client.list_invoice_payments(invoice_id):
            payment_date = _extract_date(payment.get("date"))
            if payment_date is None or payment_date < start or payment_date > end:
                continue
            inflow_rows.append(
                {
                    "Payment Date": payment_date,
                    "Amount": _safe_float(payment.get("value")),
                    "Document Nr.": str(invoice.get("document_nr") or invoice_id),
                    "Contact Name": str(invoice.get("contact_name") or invoice.get("contact_id") or "Unknown"),
                    "Title/Description": str(invoice.get("title") or invoice.get("api_reference") or ""),
                }
            )

    bills = client.list_bills_v2(page_size=500)
    for bill in bills:
        if not _is_bill_paid(bill):
            continue
        bill_id = bill.get("id")
        if bill_id is None:
            continue
        for payment in client.list_bill_payments(bill_id):
            payment_date = _extract_date(payment.get("date"))
            if payment_date is None or payment_date < start or payment_date > end:
                continue
            outflow_rows.append(
                {
                    "Payment Date": payment_date,
                    "Amount": _safe_float(payment.get("value")),
                    "Document Nr.": str(bill.get("document_nr") or bill.get("vendor_bill_nr") or bill_id),
                    "Contact Name": str(bill.get("contact_name") or bill.get("supplier_name") or bill.get("contact_id") or "Unknown"),
                    "Title/Description": str(bill.get("title") or bill.get("api_reference") or ""),
                }
            )

    return pd.DataFrame(inflow_rows, columns=table_columns), pd.DataFrame(outflow_rows, columns=table_columns)


def render_cashflow_section(start_date: date, end_date: date) -> None:
    st.caption(
        "Cashflow is based on actual payment dates from Bexio payments via PAT authentication."
    )

    settings = get_settings()
    if not _has_bexio_pat(settings):
        st.info("Configure `BEXIO_PAT` in `.env` to load cashflow from invoice and bill payments.")
        return

    try:
        with st.spinner("Fetching payments from Bexio..."):
            inflows_df, outflows_df = _fetch_cashflow_rows(
                start_date.isoformat(),
                end_date.isoformat(),
                _pat_cache_key(settings),
            )
    except Exception as exc:
        st.error(f"Failed to fetch cashflow data from Bexio: {exc}")
        st.info(
            "Troubleshooting tips:\n"
            "- Ensure `BEXIO_PAT` is valid and not expired/revoked\n"
            "- Ensure your user has invoice/bill permissions in Bexio\n"
            "- Verify PAT access with `GET /4.0/purchase/bills`"
        )
        return

    inflows_total = float(inflows_df["Amount"].sum()) if not inflows_df.empty else 0.0
    outflows_total = float(outflows_df["Amount"].sum()) if not outflows_df.empty else 0.0
    net_total = inflows_total - outflows_total

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Inflows", f"{inflows_total:,.2f} CHF")
    c2.metric("Total Outflows", f"-{outflows_total:,.2f} CHF")
    c3.metric("Net Cashflow", f"{net_total:,.2f} CHF")

    chart_df = pd.DataFrame(
        [
            {"Type": "Inflows", "Amount": inflows_total},
            {"Type": "Outflows", "Amount": -outflows_total},
            {"Type": "Net", "Amount": net_total},
        ]
    )
    chart = px.bar(
        chart_df,
        x="Type",
        y="Amount",
        color="Type",
        text="Amount",
        title=f"Cashflow {start_date.isoformat()} - {end_date.isoformat()}",
        color_discrete_map={"Inflows": "#2E8B57", "Outflows": "#C0392B", "Net": "#2980B9"},
    )
    chart.update_traces(texttemplate="%{text:,.2f} CHF")
    chart.update_yaxes(tickformat=",.0f")
    chart.update_layout(showlegend=False, template="plotly_dark")
    st.plotly_chart(chart, width="stretch")

    in_tab, out_tab = st.tabs(["Inflows", "Outflows"])
    with in_tab:
        st.dataframe(inflows_df.sort_values("Payment Date", ascending=False), width="stretch", hide_index=True)
    with out_tab:
        st.dataframe(outflows_df.sort_values("Payment Date", ascending=False), width="stretch", hide_index=True)


def render_dashboard_page(settings: Settings) -> None:
    st.header("Bexio Dashboard")
    presets = ["This Month", "QTD", "YTD", "Custom"]
    selected_preset = st.sidebar.selectbox("Date Range", presets, index=0)
    currency = "CHF"

    if selected_preset == "Custom":
        start_date = st.sidebar.date_input("Start Date", value=date(date.today().year, 1, 1))
        end_date = st.sidebar.date_input("End Date", value=date.today())
    else:
        start_date, end_date = _get_date_range(selected_preset)

    _render_bexio_auth_panel(settings)

    invoices_df = _load_real_invoices(settings)
    using_real_data = invoices_df is not None
    if invoices_df is None:
        invoices_df = _dummy_invoices()
        transactions_df = _dummy_transactions()
    else:
        transactions_df = _invoices_to_transactions(invoices_df)

    # Apply the selected date range to the cashflow KPIs and trend chart as well.
    tx_mask = (transactions_df["date"].dt.date >= start_date) & (transactions_df["date"].dt.date <= end_date)
    transactions_df_for_kpis = transactions_df.loc[tx_mask]

    kpis = compute_kpis(transactions_df_for_kpis)

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Cash In", f"{kpis.cash_in:,.0f} {currency}")
    c2.metric("Cash Out", f"{kpis.cash_out:,.0f} {currency}")
    c3.metric("Net Cashflow", f"{kpis.net_cashflow:,.0f} {currency}")
    c4.metric("Open Receivables", f"{kpis.open_receivables:,.0f} {currency}")
    c5.metric("Open Payables", f"{kpis.open_payables:,.0f} {currency}")
    c6.metric("Cashflow Trend (MoM)", f"{kpis.cashflow_mom_pct:,.1f}%")

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Overview", "Cashflow Trend", "Invoices", "Payments", "Profit & Loss"])

    with tab1:
        st.plotly_chart(build_invoices_status_chart(invoices_df), width="stretch")
        st.caption("Data source: Bexio" if using_real_data else "Data source: Dummy seed data")

    with tab2:
        render_cashflow_section(start_date, end_date)

    with tab3:
        st.markdown("### Invoices")
        status_filter = st.selectbox("Status", ["", "open", "paid", "unknown"], index=0)
        min_amount = st.number_input("Min Amount", min_value=0.0, value=0.0, step=100.0)
        search_text = st.text_input("Search (contact or document no.)", value="")
        filtered = filter_invoices(invoices_df, status_filter or None, min_amount or None, search_text or None)
        mask = (filtered["date"].dt.date >= start_date) & (filtered["date"].dt.date <= end_date)
        st.dataframe(filtered.loc[mask], width="stretch", hide_index=True)

    with tab4:
        st.markdown("### Payments")
        paid = invoices_df[invoices_df["status"].str.lower() == "paid"]["amount"].sum()
        pending = invoices_df[invoices_df["status"].str.lower() == "open"]["amount"].sum()
        st.write(f"Received: {paid:,.0f} {currency}")
        st.write(f"Pending: {pending:,.0f} {currency}")

    with tab5:
        st.markdown("### Profit & Loss")
        pnl = _load_profit_and_loss(settings, start_date=start_date, end_date=end_date)
        if pnl is None:
            st.info("Connect to Bexio to load Profit & Loss (built from accounting journal entries).")
        else:
            income, expenses, net_profit, by_account = pnl
            c1, c2, c3 = st.columns(3)
            c1.metric("Income", f"{income:,.0f} {currency}")
            c2.metric("Expenses", f"{expenses:,.0f} {currency}")
            c3.metric("Net Profit", f"{net_profit:,.0f} {currency}")

            st.caption(
                "Source: `GET /3.0/accounting/journal` aggregated by account. "
                "Account classification is currently heuristic (3xxx=income, 4xxx–8xxx=expense)."
            )

            st.dataframe(by_account, width="stretch", hide_index=True)
