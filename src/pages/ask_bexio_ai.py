from __future__ import annotations

import uuid

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.agents.graph import build_agent, run_agent_query
from src.agents.tools import create_chart, create_dynamic_table
from src.config.settings import Settings


def render_ai_page(settings: Settings) -> None:
    st.header("Ask Bexio AI")
    model_choice = st.selectbox(
        "Model",
        options=[
            settings.openrouter_model,
            "anthropic/claude-3.5-sonnet",
            "anthropic/claude-3.7-sonnet",
            "openai/gpt-4o",
            "x-ai/grok-2-1212",
        ],
        index=0,
    )

    if "agent_app" not in st.session_state or st.session_state.get("agent_model") != model_choice:
        st.session_state["agent_app"] = build_agent(settings, model_choice)
        st.session_state["agent_model"] = model_choice
    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []
    if "chat_thread_id" not in st.session_state:
        st.session_state["chat_thread_id"] = str(uuid.uuid4())

    prompt = st.chat_input("Ask about invoices, receivables, or cashflow...")
    for msg in st.session_state["chat_history"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("table") is not None:
                st.dataframe(pd.DataFrame(msg["table"]), use_container_width=True)
            if msg.get("chart") is not None:
                st.plotly_chart(go.Figure(msg["chart"]), use_container_width=True)

    if not prompt:
        return

    st.session_state["chat_history"].append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    result = run_agent_query(st.session_state["agent_app"], prompt, thread_id=st.session_state["chat_thread_id"])
    assistant_msg = {"role": "assistant", "content": result["text"]}

    if any(token in prompt.lower() for token in ["table", "tabelle", "list", "status"]):
        assistant_msg["table"] = create_dynamic_table(prompt)
    if any(token in prompt.lower() for token in ["chart", "plot", "graph", "diagramm"]):
        assistant_msg["chart"] = create_chart(prompt).get("plotly_json")

    st.session_state["chat_history"].append(assistant_msg)
    with st.chat_message("assistant"):
        st.markdown(assistant_msg["content"])
        if assistant_msg.get("table") is not None:
            st.dataframe(pd.DataFrame(assistant_msg["table"]), use_container_width=True)
        if assistant_msg.get("chart") is not None:
            st.plotly_chart(go.Figure(assistant_msg["chart"]), use_container_width=True)
