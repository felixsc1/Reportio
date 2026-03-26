from __future__ import annotations

from src.integrations.personio.client import PersonioClient


def test_attendance_duration_from_timestamps():
    attendance = {
        "start_time": "2026-03-01T08:00:00+00:00",
        "end_time": "2026-03-01T12:30:00+00:00",
    }
    assert PersonioClient._attendance_duration_hours(attendance) == 4.5


def test_extract_project_fallback_unassigned():
    attendance = {"note": "", "comment": None}
    assert PersonioClient._extract_project(attendance) == "Unassigned"

def test_extract_project_from_nested_attributes_project_name():
    attendance = {
        "attributes": {
            "project": {
                "type": "Project",
                "id": 1,
                "attributes": {"name": "Customer Work"},
            }
        }
    }
    assert PersonioClient._extract_project(attendance) == "Customer Work"


def test_list_employees_filters_active_and_builds_name():
    class StubClient(PersonioClient):
        def __init__(self):
            pass

        def _get(self, endpoint, params=None):
            _ = endpoint, params
            return {
                "data": [
                    {
                        "attributes": {
                            "id": {"value": 5},
                            "status": {"value": "active"},
                            "first_name": {"value": "Max"},
                            "last_name": {"value": "Mustermann"},
                            "weekly_hours": {"value": 40},
                        }
                    },
                    {
                        "attributes": {
                            "id": {"value": 6},
                            "status": {"value": "inactive"},
                            "first_name": {"value": "Old"},
                            "last_name": {"value": "User"},
                        }
                    },
                ]
            }

    client = StubClient()
    employees = client.list_employees()
    assert len(employees) == 1
    assert employees[0].employee_id == 5
    assert employees[0].full_name == "Max Mustermann"
    assert employees[0].weekly_hours == 40.0


def test_extract_weekly_hours_from_employments_prefers_full_time():
    payload = {
        "_data": [
            {"status": "INACTIVE", "full_time_weekly_working_hours": 38.0},
            {"status": "ACTIVE", "full_time_weekly_working_hours": 40.0, "weekly_working_hours": 39.0},
        ]
    }
    assert PersonioClient._extract_weekly_hours_from_employments(payload) == 40.0
