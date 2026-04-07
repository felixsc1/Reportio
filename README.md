# Reportio (Bexio MVP)

Reportio is a local-first Streamlit financial dashboard with Bexio integration and a LangGraph-based AI assistant.

![Reportio logo](assets/reportio_logo.jpg)

## Features in this MVP

- Bexio integration using Personal Access Token (PAT) authentication.
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

## Bexio authentication (PAT)

- Configure `BEXIO_PAT` in `.env` (create it at [developer.bexio.com/pat](https://developer.bexio.com/pat)).
- The dashboard reads data directly using this bearer token.
- Profit & Loss uses `GET /3.0/accounting/journal`.
- Supplier bills/outgoing payments use Purchase API v4 (`/4.0/purchase/...`).
- Keep PAT secret, rotate periodically, and revoke it immediately if leaked.

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
