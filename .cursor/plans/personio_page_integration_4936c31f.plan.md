---
name: Personio Page Integration
overview: Add a new Streamlit Personio page using non-interactive v1 authentication (client credentials), with employee/date filters, attendance + absence views, project hour breakdown, and an optional expected-vs-actual mismatch indicator.
todos:
  - id: wire-personio-page
    content: Add Personio page to app navigation and page module skeleton
    status: completed
  - id: build-personio-client
    content: Implement Personio client auth + employees/attendances/absences methods with normalization
    status: completed
  - id: extend-config
    content: Add Personio settings/env variables and update .env.example
    status: completed
  - id: implement-ui-filters
    content: Implement time + employee filters and render attendance/absence data
    status: completed
  - id: project-breakdown
    content: Add project-hours aggregation with Unassigned fallback
    status: completed
  - id: mismatch-cue
    content: Add basic expected-vs-actual attendance warning with holiday limitation note
    status: completed
  - id: tests-and-docs
    content: Add/adjust tests and README documentation
    status: completed
isProject: false
---

# Personio Page Integration Plan

## Goal

Implement a new Personio integration page in the existing Streamlit app that mirrors the Bexio page patterns, but uses simple credential-based token acquisition (`client_id` + `client_secret`) and displays employee attendance/absence insights for a selected period.

## Scope

- Add a new `Personio` page to sidebar navigation.
- Add Personio integration client and token handling (v1 `/auth` flow).
- Add filters: preset date period (`Current Month` + custom range) and employee selector.
- Show attendance and absence details for selected employee/timeframe.
- Add attendance project-hours breakdown with fallback bucket `Unassigned`.
- Add low-priority mismatch cue (actual attendance hours vs expected work hours), without holiday-specific corrections.

## File-by-File Changes

- Update navigation in [C:/GitRepos/Reportio/app.py](C:/GitRepos/Reportio/app.py)
  - Add new page option (e.g. `Personio`) to sidebar radio.
  - Import and call `render_personio_page(settings)`.
- Add new page module [C:/GitRepos/Reportio/src/pages/personio.py](C:/GitRepos/Reportio/src/pages/personio.py)
  - Reuse dashboard-style date preset helper pattern (`This Month` + `Custom`).
  - Add employee picker sourced from Personio active employees.
  - Render sections/tabs:
    - Employee summary (name/id, expected hours where available)
    - Attendance table (date/start/end/duration/project)
    - Absence table (period/type/half-day fields)
    - Project breakdown (hours by project, with `Unassigned` fallback)
    - Mismatch cue (`actual_hours < expected_hours_in_period`) as warning badge/text.
  - Handle API errors with `st.warning` and actionable hints.
- Add integration package [C:/GitRepos/Reportio/src/integrations/personio/client.py](C:/GitRepos/Reportio/src/integrations/personio/client.py)
  - Implement `PersonioClient` with `httpx` and retry behavior similar to Bexio.
  - Methods:
    - `authenticate()` -> fetch and cache bearer token from `/v1/auth`.
    - `list_employees()` -> retrieve employees, filter active, return normalized id/name/weekly_hours.
    - `get_attendances(employee_id, start_date, end_date)`.
    - `get_absences(employee_id, start_date, end_date)`.
  - Include response normalization helpers:
    - Convert attendance periods to decimal hours.
    - Extract project value from likely fields, fallback to `Unassigned`.
  - Add defensive handling for schema drift (missing fields, different key names).
- Add Personio models/errors [C:/GitRepos/Reportio/src/integrations/personio/models.py](C:/GitRepos/Reportio/src/integrations/personio/models.py)
  - Define lightweight typed structures (or dataclasses) for token payload and normalized rows.
  - Define `PersonioApiError` for consistent error handling.
- Add package init files
  - [C:/GitRepos/Reportio/src/integrations/personio/**init**.py](C:/GitRepos/Reportio/src/integrations/personio/__init__.py)
  - Optionally export `PersonioClient` for cleaner imports.
- Extend settings in [C:/GitRepos/Reportio/src/config/settings.py](C:/GitRepos/Reportio/src/config/settings.py)
  - Add fields:
    - `personio_client_id`
    - `personio_client_secret`
    - `personio_api_base_url` (default `https://api.personio.de/v1` or base domain + path handling)
  - Load from env/Streamlit secrets via existing `_read_value` pattern.
- Update env template [C:/GitRepos/Reportio/.env.example](C:/GitRepos/Reportio/.env.example)
  - Add `PERSONIO_CLIENT_ID`, `PERSONIO_CLIENT_SECRET`, `PERSONIO_API_BASE_URL`.
  - Keep comments explicit that this is non-interactive v1 auth.
- Update docs [C:/GitRepos/Reportio/README.md](C:/GitRepos/Reportio/README.md)
  - Add Personio setup section and new page description.
  - Document assumptions for mismatch cue (holidays not considered in v1).

## Data and UI Logic Details

- Date filter:
  - Presets: `Current Month`, `Custom` (start/end pickers).
- Employee filter:
  - Dropdown of active employees (`Full Name` + id).
- Attendance breakdown:
  - Group by extracted project label.
  - Sum decimal hours; show table + simple bar chart (optional, if consistent with existing Plotly usage).
- Mismatch cue:
  - Estimate expected period hours from employee weekly hours and weekdays in range.
  - Show warning only when estimate is meaningful and attendance data exists.
  - Add explanatory caption that public holidays are not included.

## Testing

- Add tests for settings loading in [C:/GitRepos/Reportio/tests/test_settings.py](C:/GitRepos/Reportio/tests/test_settings.py)
  - Assert Personio defaults/fields load correctly.
- Add new tests (unit-level) for normalization helpers, e.g. [C:/GitRepos/Reportio/tests/test_personio_client.py](C:/GitRepos/Reportio/tests/test_personio_client.py)
  - Attendance duration calculation.
  - Project extraction fallback to `Unassigned`.
  - Active employee filtering.
  - Mismatch calculation helper (if factored out).

## Acceptance Criteria

- New `Personio` page is visible and functional in navigation.
- User can select period and employee and see attendance/absence entries.
- Attendance data is grouped by project with `Unassigned` fallback.
- A basic mismatch warning appears when attendance appears below expected hours.
- Configuration is documented and app starts without regressions to Bexio features.
