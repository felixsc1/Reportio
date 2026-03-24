from __future__ import annotations

from src.agents.tools import get_open_receivables, list_available_data


def test_open_receivables_and_catalog():
    receivables = get_open_receivables()
    catalog = list_available_data()
    assert receivables["count"] >= 0
    assert "finance" in catalog
