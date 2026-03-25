# Reportio (Bexio MVP)

Reportio is a local-first Streamlit financial dashboard with Bexio integration and a LangGraph-based AI assistant.

## Features in this MVP

- Bexio OAuth2 authorization code flow wiring (with refresh token support).
- `BexioClient` wrappers for invoices, orders/quotes, journal entries, accounts, and generic search.
- Dashboard page with date filters, KPI cards, Plotly charts, invoice filters/search, and payments summary.
- "Ask Bexio AI" page using LangGraph + OpenRouter model selection.
- Controlled dynamic table/chart generation through a restricted sandbox.

## Tech stack

- Python 3.11+
- `streamlit`, `langgraph`, `langchain`, `langchain-openai`
- `httpx`, `authlib`, `plotly`, `pandas`, `numpy`
- `python-dotenv`, `tenacity`, `pytest`

## Local setup (venv in project)

1. Create and activate venv (if needed):
   - PowerShell: `.\venv\Scripts\Activate.ps1`
2. Install dependencies:
   - `python -m pip install -r requirements.txt`
3. Copy env template:
   - `copy .env.example .env`
4. Fill in `BEXIO_*` and `OPENROUTER_*` values.
5. Run app:
   - `python -m streamlit run app.py`

## OAuth callback flow

- App exposes a Bexio connect link on the dashboard.
- Use `BEXIO_AUTH_BASE_URL=https://auth.bexio.com/realms/bexio` (new IdP).
- `BEXIO_OAUTH_SCOPE` is optional (defaults to `kb_invoice_show kb_order_show offline_access`).
- Include only scopes enabled for your OAuth app in the Bexio developer portal. Required for invoices: `kb_invoice_show`. For orders: `kb_order_show`. `offline_access` enables refresh tokens.
- Profit & Loss is built from the accounting journal endpoint (`GET /3.0/accounting/journal`) and requires the `accounting` scope.
- After login/consent, Bexio redirects back to your configured `BEXIO_REDIRECT_URI`.
- The app exchanges `code` for tokens and stores token state in Streamlit session state for the current browser session.
- Access tokens auto-refresh when near expiry.

## Running tests

- `python -m pytest -q`

## Security and operations notes

- Never log `Authorization`, `access_token`, or `refresh_token`; logs are redacted.
- Use explicit HTTP timeouts and retry policy for transient API failures (429/5xx/network).
- Read tools are enabled in the agent; write actions are intentionally deferred for later HITL rollout.
- Caching is TTL-based (`REPORTIO_CACHE_TTL_SECONDS`) to reduce API pressure.

## Future extension points

- Add `PersonioClient` and `ExcelAdapter` under `src/integrations/`.
- Extend agent toolset and chart/table generation strategies.
- Replace session token persistence with encrypted durable storage when multi-user deployment is needed.
