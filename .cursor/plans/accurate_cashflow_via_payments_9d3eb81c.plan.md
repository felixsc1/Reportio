---
name: Accurate Cashflow via Payments
overview: Replace the current invoice-status-based cashflow trend with a payment-date-based cashflow summary that mirrors manual Bexio dashboard logic for the selected date range. Extend the existing Bexio client with invoice/bill payment retrieval, wire a new `render_cashflow_section(start_date, end_date)` into the dashboard, and add scope/config guidance for `kb_bill_show`.
todos: []
isProject: false
---

# Accurate Cashflow Summary Plan

## Goal

Implement a new cashflow section that calculates inflows/outflows from **actual payment dates** (invoice and bill payments), using the existing date selector in the Streamlit dashboard, and replace the current inaccurate trend logic.

## What will be changed

- **Bexio client extensions** in [C:/GitRepos/Reportio/src/integrations/bexio/client.py](C:/GitRepos/Reportio/src/integrations/bexio/client.py)
  - Add reusable read methods for:
    - listing invoices (full fetch)
    - listing bills (full fetch)
    - fetching payments for one invoice
    - fetching payments for one bill
  - Reuse existing `_request`, `_cached_get`, `_paginated_get`, and existing error/retry behavior.
  - Keep methods endpoint-focused so the dashboard layer handles period filtering and aggregation.
- **Dashboard cashflow rendering** in [C:/GitRepos/Reportio/src/pages/dashboard.py](C:/GitRepos/Reportio/src/pages/dashboard.py)
  - Add `render_cashflow_section(start_date, end_date)` (plus small internal helpers) that:
    - shows a scope note (must include `kb_bill_show`, then reconnect)
    - loads data with spinner
    - computes inflows from invoice payments in selected range
    - computes outflows from bill payments in selected range
    - renders top metrics (Inflows, Outflows, Net)
    - renders cashflow bar chart (`Inflows`, `Outflows`, `Net`) with CHF formatting
    - renders detailed `st.dataframe` tables in tabs `Inflows` / `Outflows`
  - Replace the old `Cashflow Trend` tab content (currently based on transformed invoice status amounts) with the new section.
- **Scope defaults and guidance**
  - Update default OAuth scope string to include bill read scope in:
    - [C:/GitRepos/Reportio/src/config/settings.py](C:/GitRepos/Reportio/src/config/settings.py)
    - [C:/GitRepos/Reportio/.env.example](C:/GitRepos/Reportio/.env.example)
  - Keep clear UI guidance to re-authenticate after changing scopes.

## Implementation details

- **Date handling**
  - Continue using existing `start_date`/`end_date` (`datetime.date`) from sidebar.
  - Parse Bexio payment dates to Python dates and include rows where `start_date <= payment_date <= end_date`.
- **Business logic mapping**
  - Inflows: sum `payment.value` from invoice payments within range.
  - Outflows: sum `payment.value` from bill payments within range (displayed as negative in chart/metric).
  - Net: `inflows - outflows`.
  - Paid-document pre-check optimization:
    - Invoice: treat as paid when `total_received_payments + total_credit_vouchers >= total` (with safe numeric coercion); fallback to paid status text if needed.
    - Bill: treat as paid when `total_paid >= total` (fallback to paid status text if needed).
- **Performance and cache**
  - Use `@st.cache_data` around dashboard-level fetch/aggregation helpers keyed by date range and token-safe inputs.
  - Continue leveraging client-level TTL cache for endpoint requests.
  - Keep pagination loops robust (`limit`/`offset`, fetch until short/empty page).
- **Error handling UX**
  - Catch `BexioApiError`/network exceptions and show actionable `st.error`/`st.info` messages (missing scope, reconnect, permissions).
  - Avoid breaking the whole dashboard when cashflow calls fail; show partial UI with explanation.

## Existing logic to replace

The current “cashflow trend” is invoice-status-derived and monthly-aggregated from transformed invoice rows, not from real payment dates:

```368:390:src/pages/dashboard.py
# Apply the selected date range to the cashflow KPIs and trend chart as well.
tx_mask = (transactions_df["date"].dt.date >= start_date) & (transactions_df["date"].dt.date <= end_date)
transactions_df_for_kpis = transactions_df.loc[tx_mask]

kpis = compute_kpis(transactions_df_for_kpis)
...
with tab2:
    st.plotly_chart(build_cashflow_trend(transactions_df_for_kpis), width="stretch")
```

This block will be functionally superseded for cashflow accuracy by payment-date-based calculations.

## Validation checklist

- Connect Bexio with updated scopes (`kb_bill_show` included), then run dashboard.
- Confirm metrics match manual Bexio dashboard totals for same date range.
- Confirm chart signs/colors and CHF formatting.
- Confirm inflow/outflow detail tables list only payments inside selected period.
- Confirm graceful error message when bill scope is missing.
- Run lint check on touched files and resolve introduced issues.
