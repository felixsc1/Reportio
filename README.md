# Reportio (Bexio MVP)

Reportio is a local-first Streamlit financial dashboard with Bexio integration and a LangGraph-based AI assistant.

![Reportio logo](assets/reportio_logo.jpg)

## Features in this MVP

- Bexio OAuth2 authorization code flow wiring (with refresh token support).
- `BexioClient` wrappers for invoices, orders/quotes, journal entries, accounts, and generic search.
- Dashboard page with date filters, KPI cards, Plotly charts, invoice filters/search, and payments summary.
- Personio page with employee/date filters, attendance and absence tables, project hour breakdown, and mismatch cue.
- "Ask Reportio AI" page using LangGraph + OpenRouter model selection.
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
   - Optional: fill in `PERSONIO_*` values to use the Personio page.
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

## Personio integration (client credentials)

- Configure `PERSONIO_CLIENT_ID` and `PERSONIO_CLIENT_SECRET`.
- `PERSONIO_API_BASE_URL` defaults to `https://api.personio.de/v1`.
- The app authenticates server-side via `POST /auth` and uses the returned bearer token for API calls.
- Personio page supports `Current Month` and custom ranges, plus active employee filtering.
- Project breakdown uses attendance project-like fields when available and falls back to `Unassigned`.
- Mismatch warning compares attendance hours to an expected-hours estimate from `weekly_hours`; public holidays are not included in this estimate.

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
