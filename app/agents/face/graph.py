from __future__ import annotations

from typing import Annotated, Literal

import json
import httpx
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition, InjectedState

from app.config import settings
from app.agents.face.prompts import SPECIALIST_SYSTEM_PROMPTS
from app.agents.face.state import FaceAgentState


# Bundle C: structured output returned by the specialist LLM call.
class SpecialistResult(BaseModel):
    prompt: str = Field(description="Final generation/edit prompt.")
    amount: int = Field(description="Number of outputs to generate. Must be >= 1.")
    model: str = Field(description="Generation model identifier. Must be non-empty.")


@tool("generate")
async def generate(
    route: Literal["t2i", "i2i", "m2i", "i2v"],
    intent: str,
    state: Annotated[FaceAgentState, InjectedState],
) -> str:
    """Bundle C implementation.

    Requirements:
    - Tool name is exactly "generate".
    - LLM-visible args are only {route, intent}.
    - Reads server-owned context via InjectedState.
    - Never raises.
    - Always includes route + video in return.
    """
    # Bundle C: always include route + video (locked contract).
    video = route == "i2v"

    webhook_url = settings.N8N_WEBHOOK_URL
    if not webhook_url:
        return json.dumps({"ok": False, "error_code": "missing_webhook_url", "route": route, "video": video})

    specialist_system_prompt = SPECIALIST_SYSTEM_PROMPTS.get(route)
    if not specialist_system_prompt:
        return json.dumps({"ok": False, "error_code": "invalid_route", "route": route, "video": video})

    # Server-owned context (must NOT be provided by the LLM tool args)
    project_id = state["project_id"]
    selected_ids = state["selected_ids"]
    requested_aspect = state.get("requested_aspect")

    # Specialist call: non-streaming, temperature=0, structured output.
    try:
        specialist_llm = ChatOpenAI(
            model=settings.MODEL_NAME,
            streaming=False,
            temperature=0,
        )
        structured = specialist_llm.with_structured_output(SpecialistResult)
        specialist_out: SpecialistResult = await structured.ainvoke(
            [
                SystemMessage(content=specialist_system_prompt),
                HumanMessage(content=intent),
            ]
        )
    except Exception:
        return json.dumps({"ok": False, "error_code": "specialist_parse_error", "route": route, "video": video})

    # Deterministic validation
    if not isinstance(specialist_out.amount, int) or specialist_out.amount < 1:
        return json.dumps({"ok": False, "error_code": "specialist_parse_error", "route": route, "video": video})
    if not isinstance(specialist_out.model, str) or not specialist_out.model.strip():
        return json.dumps({"ok": False, "error_code": "specialist_parse_error", "route": route, "video": video})
    if not isinstance(specialist_out.prompt, str) or not specialist_out.prompt.strip():
        return json.dumps({"ok": False, "error_code": "specialist_parse_error", "route": route, "video": video})

    payload = {
        "project_id": project_id,
        "selected_ids": selected_ids,
        "prompt": specialist_out.prompt,
        "amount": specialist_out.amount,
        "model": specialist_out.model,
        "requested_aspect": requested_aspect,
        "route": route,
        "video": video,
    }

    # Tight timeout; never raise.
    try:
        timeout = httpx.Timeout(10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(webhook_url, json=payload)
            if resp.status_code < 200 or resp.status_code >= 300:
                return json.dumps({"ok": False, "error_code": "webhook_http_error", "route": route, "video": video})
    except httpx.TimeoutException:
        return json.dumps({"ok": False, "error_code": "webhook_timeout", "route": route, "video": video})
    except Exception:
        return json.dumps({"ok": False, "error_code": "webhook_network_error", "route": route, "video": video})

    return json.dumps({
        "ok": True,
        "route": route,
        "video": video,
        "amount": specialist_out.amount,
        "model": specialist_out.model,
    })


def build_face_graph(llm: ChatOpenAI):
    """Bundle B: standard tool loop.

    agent (LLM+tools) -> ToolNode -> agent ... until no tool calls -> END
    """

    llm_with_tools = llm.bind_tools([generate])

    async def agent_node(state: FaceAgentState) -> dict:
        messages = state["messages"]
        response = await llm_with_tools.ainvoke(messages)
        return {"messages": [response]}

    graph = StateGraph(FaceAgentState)

    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode([generate]))

    graph.add_edge(START, "agent")

    # Bundle B: explicit mapping for version-stability.
    # tools_condition returns "tools" or "__end__".
    graph.add_conditional_edges(
        "agent",
        tools_condition,
        {
            "tools": "tools",
            "__end__": END,
        },
    )

    graph.add_edge("tools", "agent")

    return graph.compile()
