from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langchain_core.tools import StructuredTool

from src.agents.state import AgentState
from src.agents.tools import (
    create_chart,
    create_dynamic_table,
    get_cashflow_summary,
    get_invoices,
    get_open_receivables,
    list_available_data,
)
from src.config.settings import Settings


SYSTEM_PROMPT = (
    "You are Reportio AI, a financial assistant for Bexio users. "
    "Answer in German or English based on the user language. "
    "Use tools for numeric answers and summarize assumptions clearly."
)


def _build_model(settings: Settings, model_name: str | None = None) -> ChatOpenAI:
    return ChatOpenAI(
        model=model_name or settings.openrouter_model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        temperature=0.1,
    )


def build_agent(settings: Settings, model_name: str | None = None):
    tools = [
        StructuredTool.from_function(get_cashflow_summary),
        StructuredTool.from_function(get_invoices),
        StructuredTool.from_function(get_open_receivables),
        StructuredTool.from_function(list_available_data),
        StructuredTool.from_function(create_dynamic_table),
        StructuredTool.from_function(create_chart),
    ]
    tool_node = ToolNode(tools)
    model = _build_model(settings, model_name).bind_tools(tools)

    def chat_node(state: AgentState) -> AgentState:
        messages = state["messages"]
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=SYSTEM_PROMPT), *messages]
        response = model.invoke(messages)
        return {
            **state,
            "messages": [*state["messages"], response],
            "tool_results": state.get("tool_results", []),
        }

    def should_continue(state: AgentState) -> str:
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
            return "tools"
        return "end"

    graph = StateGraph(AgentState)
    graph.add_node("chat", chat_node)
    graph.add_node("tools", tool_node)
    graph.add_edge(START, "chat")
    graph.add_conditional_edges("chat", should_continue, {"tools": "tools", "end": END})
    graph.add_edge("tools", "chat")
    return graph.compile(checkpointer=MemorySaver())


def run_agent_query(
    app, user_query: str, locale: str = "en", thread_id: str = "default-thread"
) -> dict[str, Any]:
    state: AgentState = {
        "messages": [HumanMessage(content=user_query)],
        "locale": locale,
        "filters": {},
        "tool_results": [],
    }
    result = app.invoke(state, config={"configurable": {"thread_id": thread_id}})
    final_msg = result["messages"][-1]
    return {"text": str(final_msg.content)}
