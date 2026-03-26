from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class PersonioToken:
    access_token: str
    expires_at: datetime
    token_type: str = "Bearer"

    @property
    def is_expired(self) -> bool:
        return datetime.utcnow() + timedelta(seconds=30) >= self.expires_at


@dataclass
class EmployeeRecord:
    employee_id: int
    full_name: str
    weekly_hours: float | None


@dataclass
class AttendanceRecord:
    employee_id: int
    date: str
    start_time: str | None
    end_time: str | None
    hours: float
    project: str


@dataclass
class AbsenceRecord:
    employee_id: int
    start_date: str
    end_date: str
    absence_type: str
    half_day_start: bool
    half_day_end: bool


@dataclass
class PersonioApiError(Exception):
    status_code: int
    message: str

    def __str__(self) -> str:
        return f"PersonioApiError(status_code={self.status_code}, message={self.message})"
