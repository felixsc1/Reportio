from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.config.settings import Settings
from src.integrations.personio.models import (
    AbsenceRecord,
    AttendanceRecord,
    EmployeeRecord,
    PersonioApiError,
    PersonioToken,
)

logger = logging.getLogger(__name__)


class PersonioClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = httpx.Client(base_url=settings.personio_api_base_url.rstrip("/"), timeout=30.0)
        self._v2_client = httpx.Client(base_url="https://api.personio.de", timeout=30.0)
        self._token: PersonioToken | None = None
        self._weekly_hours_cache: dict[int, float | None] = {}

    def _require_credentials(self) -> None:
        if not self.settings.personio_client_id or not self.settings.personio_client_secret:
            raise PersonioApiError(
                status_code=401,
                message="Missing Personio credentials. Set PERSONIO_CLIENT_ID and PERSONIO_CLIENT_SECRET.",
            )

    def authenticate(self) -> str:
        self._require_credentials()
        if self._token and not self._token.is_expired:
            return self._token.access_token

        response = self._client.post(
            "/auth",
            json={
                "client_id": self.settings.personio_client_id,
                "client_secret": self.settings.personio_client_secret,
            },
        )
        if response.status_code >= 400:
            raise PersonioApiError(status_code=response.status_code, message=response.text[:500])

        payload = response.json()
        token_value = (
            payload.get("data", {}).get("token")
            if isinstance(payload, dict)
            else None
        )
        if not token_value:
            raise PersonioApiError(status_code=500, message="Auth token not found in Personio response.")

        self._token = PersonioToken(
            access_token=str(token_value),
            expires_at=datetime.utcnow() + timedelta(minutes=55),
        )
        return self._token.access_token

    def _headers(self) -> dict[str, str]:
        token = self.authenticate()
        return {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    @retry(
        reraise=True,
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
    )
    def _get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self._client.get(endpoint, headers=self._headers(), params=params)
        if response.status_code in (429, 500, 502, 503, 504):
            raise httpx.NetworkError(f"Transient Personio API error: {response.status_code}")
        if response.status_code >= 400:
            raise PersonioApiError(status_code=response.status_code, message=response.text[:500])
        data = response.json()
        if not isinstance(data, dict):
            raise PersonioApiError(status_code=500, message="Unexpected Personio response format.")
        return data

    def _get_v2(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self._v2_client.get(endpoint, headers=self._headers(), params=params)
        if response.status_code in (429, 500, 502, 503, 504):
            raise httpx.NetworkError(f"Transient Personio API error: {response.status_code}")
        if response.status_code >= 400:
            raise PersonioApiError(status_code=response.status_code, message=response.text[:500])
        data = response.json()
        if not isinstance(data, dict):
            raise PersonioApiError(status_code=500, message="Unexpected Personio v2 response format.")
        return data

    @staticmethod
    def _row_attributes(row: dict[str, Any]) -> dict[str, Any]:
        attrs = row.get("attributes")
        if isinstance(attrs, dict):
            return attrs
        return row

    @staticmethod
    def _as_float(value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _extract_attribute(employee: dict[str, Any], key: str) -> Any:
        attrs = employee.get("attributes", {})
        if not isinstance(attrs, dict):
            return None
        node = attrs.get(key)
        if isinstance(node, dict):
            return node.get("value")
        return None

    @staticmethod
    def _extract_project(attendance: dict[str, Any]) -> str:
        attributes = PersonioClient._row_attributes(attendance)
        candidates = [
            attributes.get("project"),
            attributes.get("project_name"),
            attributes.get("project_id"),
            attributes.get("comment"),
            attributes.get("note"),
        ]
        for value in candidates:
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, (int, float)):
                return str(value)
            if isinstance(value, dict):
                value_attrs = value.get("attributes")
                if isinstance(value_attrs, dict):
                    name = value_attrs.get("name")
                    if isinstance(name, str) and name.strip():
                        return name.strip()

        for key in ("project", "project_name", "dynamic_project", "dynamic_project_name"):
            val = attributes.get(key)
            if isinstance(val, dict):
                inner = val.get("value")
                if isinstance(inner, str) and inner.strip():
                    return inner.strip()
        return "Unassigned"

    @staticmethod
    def _attendance_duration_hours(attendance: dict[str, Any]) -> float:
        attributes = PersonioClient._row_attributes(attendance)
        hours = PersonioClient._as_float(attributes.get("hours"))
        if hours is not None:
            return round(hours, 2)

        start = attributes.get("start_time")
        end = attributes.get("end_time")
        if not isinstance(start, str) or not isinstance(end, str):
            return 0.0
        try:
            if "T" in start and "T" in end:
                start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
            else:
                start_dt = datetime.strptime(start, "%H:%M")
                end_dt = datetime.strptime(end, "%H:%M")
            seconds = (end_dt - start_dt).total_seconds()
            return round(max(seconds, 0) / 3600.0, 2)
        except ValueError:
            return 0.0

    def list_employees(self) -> list[EmployeeRecord]:
        payload = self._get("/company/employees")
        rows = payload.get("data", [])
        if not isinstance(rows, list):
            return []

        result: list[EmployeeRecord] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            status = self._extract_attribute(row, "status")
            if str(status).lower() != "active":
                continue
            first_name = str(self._extract_attribute(row, "first_name") or "").strip()
            last_name = str(self._extract_attribute(row, "last_name") or "").strip()
            employee_id = self._extract_attribute(row, "id")
            weekly_hours = self._as_float(self._extract_attribute(row, "weekly_hours"))
            if employee_id is None:
                continue
            full_name = (f"{first_name} {last_name}".strip() or f"Employee {employee_id}")
            result.append(
                EmployeeRecord(
                    employee_id=int(employee_id),
                    full_name=full_name,
                    weekly_hours=weekly_hours,
                )
            )
        return sorted(result, key=lambda x: x.full_name.lower())

    @staticmethod
    def _extract_weekly_hours_from_employments(payload: dict[str, Any]) -> float | None:
        employments = payload.get("_data")
        if not isinstance(employments, list):
            return None
        active_first = sorted(
            [row for row in employments if isinstance(row, dict)],
            key=lambda row: 0 if str(row.get("status", "")).upper() == "ACTIVE" else 1,
        )
        for row in active_first:
            hours = PersonioClient._as_float(row.get("full_time_weekly_working_hours"))
            if hours is not None and hours > 0:
                return hours
            hours = PersonioClient._as_float(row.get("weekly_working_hours"))
            if hours is not None and hours > 0:
                return hours
        return None

    def get_person_weekly_hours(self, employee_id: int) -> float | None:
        if employee_id in self._weekly_hours_cache:
            return self._weekly_hours_cache[employee_id]
        payload = self._get_v2(f"/v2/persons/{employee_id}/employments")
        hours = self._extract_weekly_hours_from_employments(payload)
        self._weekly_hours_cache[employee_id] = hours
        return hours

    def get_attendances(self, employee_id: int, start_date: str, end_date: str) -> list[AttendanceRecord]:
        params: dict[str, Any] = {
            "start_date": start_date,
            "end_date": end_date,
            "employees[]": employee_id,
        }
        payload = self._get("/company/attendances", params=params)
        rows = payload.get("data", [])
        if not isinstance(rows, list):
            return []

        result: list[AttendanceRecord] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            attributes = self._row_attributes(row)
            result.append(
                AttendanceRecord(
                    employee_id=int(attributes.get("employee", employee_id)),
                    date=str(attributes.get("date", "")),
                    start_time=str(attributes.get("start_time")) if attributes.get("start_time") is not None else None,
                    end_time=str(attributes.get("end_time")) if attributes.get("end_time") is not None else None,
                    hours=self._attendance_duration_hours(row),
                    project=self._extract_project(row),
                )
            )
        return result

    def get_absences(self, employee_id: int, start_date: str, end_date: str) -> list[AbsenceRecord]:
        params: dict[str, Any] = {
            "start_date": start_date,
            "end_date": end_date,
            "employees[]": employee_id,
        }
        payload = self._get("/company/time-offs", params=params)
        rows = payload.get("data", [])
        if not isinstance(rows, list):
            return []

        result: list[AbsenceRecord] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            attributes = self._row_attributes(row)
            absence_type = attributes.get("time_off_type", {})
            if isinstance(absence_type, dict):
                absence_type_name = str(absence_type.get("name", "Unknown"))
            else:
                absence_type_name = str(attributes.get("time_off_type_name", "Unknown"))
            result.append(
                AbsenceRecord(
                    employee_id=int(attributes.get("employee", employee_id)),
                    start_date=str(attributes.get("start_date", "")),
                    end_date=str(attributes.get("end_date", "")),
                    absence_type=absence_type_name,
                    half_day_start=bool(attributes.get("half_day_start", False)),
                    half_day_end=bool(attributes.get("half_day_end", False)),
                )
            )
        return result

    def close(self) -> None:
        self._client.close()
        self._v2_client.close()
