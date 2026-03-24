from __future__ import annotations

import streamlit as st

from src.config.settings import get_settings
from src.pages.ask_bexio_ai import render_ai_page
from src.pages.dashboard import render_dashboard_page
from src.utils.logging import configure_logging


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    st.set_page_config(page_title="Reportio", page_icon=":bar_chart:", layout="wide")

    st.title("Reportio")
    st.caption("Bexio-powered financial dashboard with AI assistant")

    page = st.sidebar.radio("Navigation", ["Dashboard", "Ask Bexio AI"], index=0)
    if page == "Dashboard":
        render_dashboard_page(settings)
    else:
        render_ai_page(settings)


if __name__ == "__main__":
    main()
