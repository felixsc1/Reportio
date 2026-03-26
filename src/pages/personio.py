from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from src.config.settings import Settings
from src.integrations.personio.client import PersonioClient
from src.integrations.personio.models import PersonioApiError


def _get_date_range(preset: str) -> tuple[date, date]:
    today = date.today()
    if preset == "Current Month":
        return date(today.year, today.month, 1), today
    return date(today.year, today.month, 1), today


def _expected_hours_in_range(weekly_hours: float | None, start_date: date, end_date: date) -> float | None:
    if weekly_hours is None or weekly_hours <= 0:
        return None
    total_days = (end_date - start_date).days + 1
    if total_days <= 0:
        return None
    business_days = sum(1 for i in range(total_days) if (start_date + timedelta(days=i)).weekday() < 5)
    daily_hours = weekly_hours / 5.0
    return round(business_days * daily_hours, 2)


def render_personio_page(settings: Settings) -> None:
    st.header("Personio Attendance and Absence")
    st.caption("Employee time overview with project breakdown.")

    presets = ["Current Month", "Custom"]
    selected_preset = st.sidebar.selectbox("Personio Date Range", presets, index=0)
    if selected_preset == "Custom":
        start_date = st.sidebar.date_input("Start Date (Personio)", value=date(date.today().year, date.today().month, 1))
        end_date = st.sidebar.date_input("End Date (Personio)", value=date.today())
    else:
        start_date, end_date = _get_date_range(selected_preset)

    client = PersonioClient(settings)
    try:
        employees = client.list_employees()
    except PersonioApiError as exc:
        st.error(f"Failed to load employees from Personio: {exc}")
        st.info("Check PERSONIO_CLIENT_ID/PERSONIO_CLIENT_SECRET and API permissions in your Personio account.")
        client.close()
        return
    except Exception as exc:
        st.error(f"Unexpected Personio error: {exc}")
        client.close()
        return

    if not employees:
        st.info("No active employees returned by Personio.")
        client.close()
        return

    employee_labels = [f"{emp.full_name} ({emp.employee_id})" for emp in employees]
    selected_label = st.selectbox("Employee", employee_labels, index=0)
    selected_employee = employees[employee_labels.index(selected_label)]
    weekly_hours = selected_employee.weekly_hours
    if weekly_hours is None:
        try:
            weekly_hours = client.get_person_weekly_hours(selected_employee.employee_id)
        except Exception:
            weekly_hours = None

    try:
        attendances = client.get_attendances(
            employee_id=selected_employee.employee_id,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
        )
        absences = client.get_absences(
            employee_id=selected_employee.employee_id,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
        )
    except PersonioApiError as exc:
        st.error(f"Failed to load Personio time data: {exc}")
        client.close()
        return
    finally:
        client.close()

    st.subheader("Employee Summary")
    c1, c2, c3 = st.columns(3)
    total_attendance_hours = round(sum(item.hours for item in attendances), 2)
    expected_hours = _expected_hours_in_range(weekly_hours, start_date, end_date)
    c1.metric("Attendance Hours", f"{total_attendance_hours:,.2f}h")
    c2.metric("Absence Entries", str(len(absences)))
    c3.metric(
        "Expected Hours (Estimate)",
        f"{expected_hours:,.2f}h" if expected_hours is not None else "n/a",
    )

    if expected_hours is not None and total_attendance_hours < expected_hours:
        missing = round(expected_hours - total_attendance_hours, 2)
        st.warning(f"Possible mismatch detected: attendance is about {missing:,.2f}h below expected hours.")
        st.caption("Note: this estimate does not account for public holidays and local calendar rules.")

    tab1, tab2, tab3 = st.tabs(["Attendances", "Absences", "Project Breakdown"])
    with tab1:
        st.markdown("### Attendances")
        if attendances:
            attendance_df = pd.DataFrame(
                [
                    {
                        "date": row.date,
                        "start_time": row.start_time,
                        "end_time": row.end_time,
                        "hours": row.hours,
                        "project": row.project,
                    }
                    for row in attendances
                ]
            )
            st.dataframe(
                attendance_df.sort_values(by=["date", "start_time"], ascending=True),
                width="stretch",
                hide_index=True,
            )
        else:
            st.info("No attendance records for this employee in the selected period.")

    with tab2:
        st.markdown("### Absences")
        if absences:
            absence_df = pd.DataFrame(
                [
                    {
                        "start_date": row.start_date,
                        "end_date": row.end_date,
                        "type": row.absence_type,
                        "half_day_start": row.half_day_start,
                        "half_day_end": row.half_day_end,
                    }
                    for row in absences
                ]
            )
            st.dataframe(
                absence_df.sort_values(by=["start_date", "end_date"], ascending=True),
                width="stretch",
                hide_index=True,
            )
        else:
            st.info("No absence records for this employee in the selected period.")

    with tab3:
        st.markdown("### Hours by Project")
        if attendances:
            project_df = pd.DataFrame(
                [{"project": row.project or "Unassigned", "hours": row.hours} for row in attendances]
            )
            grouped = project_df.groupby("project", as_index=False)["hours"].sum().sort_values("hours", ascending=False)
            grouped["hours"] = grouped["hours"].round(2)
            st.dataframe(grouped, width="stretch", hide_index=True)
            st.bar_chart(grouped.set_index("project")["hours"])
        else:
            st.info("No attendance records available for project breakdown.")
