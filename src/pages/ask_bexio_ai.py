from __future__ import annotations

import uuid

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.agents.graph import build_agent, run_agent_query
from src.agents.tools import create_chart, create_dynamic_table
from src.config.settings import Settings
from src.integrations.ollama.client import list_local_ollama_models


LOCAL_OLLAMA_DEFAULT_MODEL = "qwen3:8b"


@st.cache_data(ttl=30)
def _fetch_local_models_cached(base_url: str) -> list[str]:
    return list_local_ollama_models(base_url)


def render_ai_page(settings: Settings) -> None:
    st.header("Ask Reportio AI")

    remote_models = [
        settings.openrouter_model,
        "anthropic/claude-3.5-sonnet",
        "anthropic/claude-3.7-sonnet",
        "openai/gpt-4o",
        "x-ai/grok-2-1212",
    ]

    local_models = _fetch_local_models_cached(settings.ollama_base_url)
    local_dropdown_models = [LOCAL_OLLAMA_DEFAULT_MODEL] + [
        m for m in local_models if m != LOCAL_OLLAMA_DEFAULT_MODEL
    ]

    model_options = [*local_dropdown_models, *remote_models]
    default_index = model_options.index(LOCAL_OLLAMA_DEFAULT_MODEL) if LOCAL_OLLAMA_DEFAULT_MODEL in model_options else 0

    model_choice = st.selectbox("Model", options=model_options, index=default_index)

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
                st.dataframe(pd.DataFrame(msg["table"]), width="stretch")
            if msg.get("chart") is not None:
                st.plotly_chart(go.Figure(msg["chart"]), width="stretch")

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
            st.dataframe(pd.DataFrame(assistant_msg["table"]), width="stretch")
        if assistant_msg.get("chart") is not None:
            st.plotly_chart(go.Figure(assistant_msg["chart"]), width="stretch")
