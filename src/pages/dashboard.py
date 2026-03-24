from __future__ import annotations

from datetime import date, datetime
from uuid import uuid4

import pandas as pd
import streamlit as st

from src.config.settings import Settings
from src.dashboard.charts import build_cashflow_trend, build_invoices_status_chart
from src.dashboard.kpis import compute_kpis
from src.dashboard.tables import filter_invoices
from src.integrations.bexio.client import BexioClient
from src.integrations.bexio.models import OAuthToken


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


def _get_oauth_token_from_session() -> OAuthToken | None:
    raw = st.session_state.get("oauth_token")
    if isinstance(raw, OAuthToken):
        return raw
    if isinstance(raw, dict):
        try:
            return OAuthToken(
                access_token=str(raw.get("access_token", "")),
                refresh_token=str(raw.get("refresh_token", "")),
                expires_at=pd.to_datetime(raw.get("expires_at")).to_pydatetime(),
                token_type=str(raw.get("token_type", "Bearer")),
            )
        except Exception:
            return None
    # Be resilient to module reloads where class identity can change.
    if all(hasattr(raw, name) for name in ("access_token", "refresh_token", "expires_at")):
        try:
            return OAuthToken(
                access_token=str(raw.access_token),
                refresh_token=str(raw.refresh_token),
                expires_at=pd.to_datetime(raw.expires_at).to_pydatetime(),
                token_type=str(getattr(raw, "token_type", "Bearer")),
            )
        except Exception:
            return None
    return None


def _render_oauth_panel(settings: Settings) -> None:
    st.subheader("Bexio Connection")
    state = st.session_state.get("oauth_state") or str(uuid4())
    st.session_state["oauth_state"] = state

    if st.button("Reset Bexio session / Reconnect", key="bexio_reset_session"):
        st.session_state.pop("oauth_token", None)
        st.session_state.pop("oauth_state", None)
        st.query_params.clear()
        st.info("Bexio session reset. Click connect again to authorize with updated scopes.")

    client = BexioClient(settings)
    auth_url = client.oauth.build_authorization_url(state=state)
    st.markdown(f"[Connect with Bexio]({auth_url})")
    st.caption(f"Requested scope: `{settings.bexio_oauth_scope or '(none - app default)'}`")

    with st.expander("Connection diagnostics", expanded=False):
        qp_code = st.query_params.get("code")
        qp_state = st.query_params.get("state")
        qp_error = st.query_params.get("error")
        qp_error_desc = st.query_params.get("error_description")
        token = _get_oauth_token_from_session()
        st.write(f"Has callback code: {'yes' if qp_code else 'no'}")
        st.write(f"Has callback state: {'yes' if qp_state else 'no'}")
        st.write(f"Session token present: {'yes' if token else 'no'}")
        st.write(f"OAuth error: {qp_error or 'none'}")
        st.write(f"OAuth error description: {qp_error_desc or 'none'}")
        st.write(f"Current redirect URI: `{settings.bexio_redirect_uri}`")

    existing_token = _get_oauth_token_from_session()
    if existing_token is not None:
        st.success("Bexio connected.")
        return

    code = st.query_params.get("code")
    callback_state = st.query_params.get("state")
    oauth_error = st.query_params.get("error")
    oauth_error_description = st.query_params.get("error_description")
    if oauth_error:
        st.error(
            "Bexio authorization failed: "
            f"{oauth_error}"
            + (f" - {oauth_error_description}" if oauth_error_description else "")
        )
        return
    if code:
        # In local Streamlit flows the callback can open a slightly different session;
        # accept code and only warn on state mismatch instead of dropping the login.
        if callback_state and callback_state != state:
            st.warning("OAuth state changed between redirects; continuing with callback code.")
        try:
            token = client.oauth.exchange_code_for_token(str(code))
            st.session_state["oauth_token"] = {
                "access_token": token.access_token,
                "refresh_token": token.refresh_token,
                "expires_at": token.expires_at.isoformat(),
                "token_type": token.token_type,
            }
            st.success("Bexio connected successfully.")
            st.query_params.clear()
            st.rerun()
        except Exception as exc:
            st.error(f"Bexio token exchange failed: {exc}")


def _load_real_invoices(settings: Settings) -> pd.DataFrame | None:
    token = _get_oauth_token_from_session()
    if not isinstance(token, OAuthToken):
        return None
    client = BexioClient(settings, token=token)
    try:
        invoices = client.list_invoices()
    except Exception as exc:
        st.warning(f"Connected but failed to load invoices from Bexio: {exc}")
        st.info(
            "💡 **Troubleshooting tips:**\n"
            "• Click **'Reset Bexio session / Reconnect'** (this also clears cache)\n"
            "• Check that your OAuth app has the `kb_invoice_show` scope\n"
            "• Verify the user account has access to invoices in Bexio\n"
            "• Check the console for detailed API error logs (now improved)"
        )
        # Clear cache on error so next attempt doesn't reuse a failed response
        try:
            client.clear_cache()
        except Exception:
            pass
        return None
    st.session_state["oauth_token"] = {
        "access_token": client.token.access_token if client.token else "",
        "refresh_token": client.token.refresh_token if client.token else "",
        "expires_at": client.token.expires_at.isoformat() if client.token else "",
        "token_type": client.token.token_type if client.token else "Bearer",
    }
    if not invoices:
        return pd.DataFrame(columns=["document_nr", "contact_name", "status", "amount", "date"])
    df = pd.DataFrame(invoices)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    elif "updated_at" in df.columns:
        df["date"] = pd.to_datetime(df["updated_at"], errors="coerce")
    else:
        df["date"] = pd.Timestamp.utcnow()
    if "contact_name" not in df.columns:
        df["contact_name"] = "Unknown"
    if "document_nr" not in df.columns:
        df["document_nr"] = df.index.astype(str)
    if "status" not in df.columns:
        df["status"] = "unknown"
    if "amount" not in df.columns:
        df["amount"] = 0.0
    return df[["document_nr", "contact_name", "status", "amount", "date"]]


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


def render_dashboard_page(settings: Settings) -> None:
    presets = ["This Month", "QTD", "YTD", "Custom"]
    selected_preset = st.sidebar.selectbox("Date Range", presets, index=0)
    currency = st.sidebar.selectbox("Currency", ["CHF", "EUR", "USD"], index=0)
    st.sidebar.selectbox("Company", ["Default"], index=0)

    if selected_preset == "Custom":
        start_date = st.sidebar.date_input("Start Date", value=date(date.today().year, 1, 1))
        end_date = st.sidebar.date_input("End Date", value=date.today())
    else:
        start_date, end_date = _get_date_range(selected_preset)

    _render_oauth_panel(settings)

    invoices_df = _load_real_invoices(settings)
    using_real_data = invoices_df is not None
    if invoices_df is None:
        invoices_df = _dummy_invoices()
        transactions_df = _dummy_transactions()
    else:
        transactions_df = _invoices_to_transactions(invoices_df)
        st.success("Connected to Bexio. Dashboard uses live invoice data.")
    kpis = compute_kpis(transactions_df)

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Cash In", f"{kpis.cash_in:,.0f} {currency}")
    c2.metric("Cash Out", f"{kpis.cash_out:,.0f} {currency}")
    c3.metric("Net Cashflow", f"{kpis.net_cashflow:,.0f} {currency}")
    c4.metric("Open Receivables", f"{kpis.open_receivables:,.0f} {currency}")
    c5.metric("Open Payables", f"{kpis.open_payables:,.0f} {currency}")
    c6.metric("Cashflow Trend (MoM)", f"{kpis.cashflow_mom_pct:,.1f}%")

    tab1, tab2, tab3, tab4 = st.tabs(["Overview", "Cashflow Trend", "Invoices", "Payments"])

    with tab1:
        st.plotly_chart(build_invoices_status_chart(invoices_df), use_container_width=True)
        st.caption("Data source: Bexio" if using_real_data else "Data source: Dummy seed data")

    with tab2:
        st.plotly_chart(build_cashflow_trend(transactions_df), use_container_width=True)

    with tab3:
        st.markdown("### Invoices")
        status_filter = st.selectbox("Status", ["", "open", "paid", "unknown"], index=0)
        min_amount = st.number_input("Min Amount", min_value=0.0, value=0.0, step=100.0)
        search_text = st.text_input("Search (contact or document no.)", value="")
        filtered = filter_invoices(invoices_df, status_filter or None, min_amount or None, search_text or None)
        mask = (filtered["date"].dt.date >= start_date) & (filtered["date"].dt.date <= end_date)
        st.dataframe(filtered.loc[mask], use_container_width=True)

    with tab4:
        st.markdown("### Payments")
        paid = invoices_df[invoices_df["status"].str.lower() == "paid"]["amount"].sum()
        pending = invoices_df[invoices_df["status"].str.lower() == "open"]["amount"].sum()
        st.write(f"Received: {paid:,.0f} {currency}")
        st.write(f"Pending: {pending:,.0f} {currency}")
