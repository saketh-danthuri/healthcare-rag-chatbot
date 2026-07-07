"""
graph.py - LangGraph Agent Definition
========================================
WHY LANGGRAPH:
  LangGraph gives us a stateful agent with:
  1. Multi-step reasoning (search -> analyze -> act -> respond)
  2. Tool calling (the LLM decides when to search, email, or query DB)
  3. Human-in-the-loop interrupts (pause before executing sensitive actions)
  4. Durable conversation memory (state persists across turns AND restarts)

GRAPH STRUCTURE:
  START -> agent -> (route)
    - safe tool (search_runbooks)      -> search -> agent
    - approval tool (email/db/publish) -> [INTERRUPT] -> execute_action -> agent
    - no tool                          -> END

MEMORY MODEL (this is the important part):
  The graph is compiled with a PERSISTENT Postgres checkpointer (set up in
  main.py's lifespan and handed to init_agent). Every turn is keyed by
  thread_id == conversation_id, so a conversation can be resumed after an
  arbitrary gap, survives server restarts, and is shared across replicas.
  MemorySaver (in-memory) is only used as a degraded fallback if Postgres is
  unreachable at startup.

HUMAN-IN-THE-LOOP:
  Approval-required tools route to the `execute_action` node, which the graph
  is told to pause BEFORE (interrupt_before=["execute_action"]). The actual
  side effect (sending the email, running the query, publishing the page) runs
  INSIDE that node only after the user approves and the graph is resumed -- so
  it is durable, exactly-once, and the agent sees the real result.
"""

import json
import logging
from pathlib import Path
from typing import Annotated, TypedDict

import yaml
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from app.agent.tools import (
    ALL_TOOLS,
    APPROVAL_REQUIRED_TOOLS,
    search_runbooks,
    validate_readonly_sql,
)

logger = logging.getLogger(__name__)

# Map the LLM-facing approval tool name -> the executor action_type used by
# tool_executors.ACTION_EXECUTORS (and by the frontend's TOOL_TO_ACTION_TYPE).
TOOL_TO_ACTION_TYPE = {
    "send_escalation_email": "send_email",
    "query_database": "query_database",
    "publish_to_confluence": "publish_confluence",
}

# Safe tools the LLM may call without approval, indexed by name for direct
# execution if one ever rides along in the same message as an approval call.
_SAFE_TOOLS_BY_NAME = {"search_runbooks": search_runbooks}


class AgentState(TypedDict):
    """Durable agent state, persisted per thread by the checkpointer.

    messages: conversation history (auto-merged via the add_messages reducer).
    user_id:  owner of the thread; recorded in the checkpoint and carried for
              long-term memory injection (Phase 2).
    """

    messages: Annotated[list, add_messages]
    user_id: str


def _load_system_prompt() -> str:
    """Load the system prompt from prompts.yaml."""
    prompts_path = Path(__file__).parent.parent / "config" / "prompts.yaml"
    with open(prompts_path) as f:
        prompts = yaml.safe_load(f)
    return prompts["prompts"]["system_prompt"]


def _create_llm() -> ChatOpenAI:
    """Create the local (Ollama) LLM client with tool-calling support.

    The LLM is bound with ALL tools (including approval-required ones) so it
    knows their schemas and can propose them; whether a proposed call executes
    is governed by the graph's routing + interrupt, not by the binding.
    """
    from app.llm import get_chat_model

    llm = get_chat_model(temperature=0.1, max_tokens=2048)
    return llm.bind_tools(ALL_TOOLS)


def _route_after_agent(state: AgentState) -> str:
    """Decide where to go after the LLM responds.

    - approval-required tool call -> "execute_action" (paused before by interrupt)
    - safe tool call              -> "search"
    - no tool call                -> END
    """
    messages = state.get("messages", [])
    if not messages:
        return END

    last_message = messages[-1]
    tool_calls = getattr(last_message, "tool_calls", None)
    if not tool_calls:
        return END

    for tool_call in tool_calls:
        if tool_call["name"] in APPROVAL_REQUIRED_TOOLS:
            return "execute_action"
    return "search"


async def _agent_node(state: AgentState) -> dict:
    """The main agent node - calls the LLM to decide what to do.

    The system prompt is loaded fresh from prompts.yaml each turn, so prompt
    changes take effect without restarting the server.
    """
    llm = _create_llm()
    system_prompt = _load_system_prompt()

    messages = state.get("messages", [])
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=system_prompt)] + messages

    response = await llm.ainvoke(messages)
    return {"messages": [response]}


async def _execute_action_node(state: AgentState) -> dict:
    """Execute the approved tool call(s) and return their results.

    The graph is configured to PAUSE before this node (interrupt_before), so it
    only runs once the user has approved and the graph is resumed. It produces a
    ToolMessage for EVERY tool call on the last AI message so the conversation
    stays well-formed (every tool call must be answered).
    """
    from app.agent.tool_executors import execute_approved_action

    messages = state.get("messages", [])
    last_message = messages[-1]
    tool_calls = getattr(last_message, "tool_calls", None) or []

    out: list[ToolMessage] = []
    for tool_call in tool_calls:
        name = tool_call["name"]
        args = tool_call.get("args", {})
        tool_call_id = tool_call["id"]

        if name in APPROVAL_REQUIRED_TOOLS:
            # Re-validate read-only SQL here too: this node runs the query
            # directly via the executor, bypassing the tool body's check.
            if name == "query_database":
                sql_error = validate_readonly_sql(args.get("sql_query", ""))
                if sql_error:
                    out.append(
                        ToolMessage(
                            content=json.dumps({"success": False, "error": sql_error}),
                            tool_call_id=tool_call_id,
                            name=name,
                        )
                    )
                    continue

            action_type = TOOL_TO_ACTION_TYPE.get(name, name)
            result = await execute_approved_action(action_type, args)
            out.append(
                ToolMessage(
                    content=json.dumps(result, default=str),
                    tool_call_id=tool_call_id,
                    name=name,
                )
            )
        else:
            # A safe tool that rode along in the same message; execute directly.
            safe_tool = _SAFE_TOOLS_BY_NAME.get(name)
            content = safe_tool.invoke(args) if safe_tool else f"Unknown tool: {name}"
            out.append(
                ToolMessage(content=str(content), tool_call_id=tool_call_id, name=name)
            )

    return {"messages": out}


def build_agent_graph() -> StateGraph:
    """Build (but do not compile) the LangGraph agent graph."""
    graph = StateGraph(AgentState)

    graph.add_node("agent", _agent_node)
    graph.add_node("search", ToolNode([search_runbooks]))
    graph.add_node("execute_action", _execute_action_node)

    graph.set_entry_point("agent")
    graph.add_conditional_edges(
        "agent",
        _route_after_agent,
        {
            "search": "search",
            "execute_action": "execute_action",
            END: END,
        },
    )
    graph.add_edge("search", "agent")
    graph.add_edge("execute_action", "agent")

    return graph


# Module-level compiled graph (singleton). Set by init_agent() during the app
# lifespan; never created lazily with an in-memory store on the request path.
_compiled_graph = None


def init_agent(checkpointer) -> object:
    """Compile the agent graph with the given checkpointer. Call once at startup.

    interrupt_before=["execute_action"] makes the graph pause before any
    side-effecting action so a human can approve it.
    """
    global _compiled_graph
    graph = build_agent_graph()
    _compiled_graph = graph.compile(
        checkpointer=checkpointer,
        interrupt_before=["execute_action"],
    )
    logger.info("Agent graph compiled (checkpointer=%s)", type(checkpointer).__name__)
    return _compiled_graph


def init_agent_in_memory() -> object:
    """Degraded fallback: compile with an in-memory checkpointer.

    Used only if the Postgres checkpointer cannot be initialized at startup, so
    the app still runs (ephemeral, single-process) instead of failing outright.
    """
    logger.warning(
        "Falling back to in-memory MemorySaver; conversations will NOT persist "
        "across restarts and will NOT be shared across replicas."
    )
    return init_agent(MemorySaver())


def get_agent():
    """Return the compiled agent graph, or raise if init_agent was not called."""
    if _compiled_graph is None:
        raise RuntimeError(
            "Agent graph is not initialized. init_agent() must run in the app "
            "lifespan before handling requests."
        )
    return _compiled_graph


def _extract_pending_action(snapshot) -> dict | None:
    """If the graph is paused before execute_action, describe the pending call."""
    if not snapshot.next or "execute_action" not in snapshot.next:
        return None

    messages = snapshot.values.get("messages", [])
    if not messages:
        return None
    last = messages[-1]
    for tool_call in getattr(last, "tool_calls", None) or []:
        if tool_call["name"] in APPROVAL_REQUIRED_TOOLS:
            return {
                "tool_name": tool_call["name"],
                "tool_call_id": tool_call["id"],
                "arguments": tool_call.get("args", {}),
                "status": "pending_approval",
            }
    return None


def _last_assistant_text(messages: list) -> str:
    """Return the content of the most recent AI text message."""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            return msg.content or ""
    return ""


def _extract_last_action_result(messages: list) -> dict | None:
    """Parse the most recent approval-tool ToolMessage result (post-resume)."""
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage) and msg.name in APPROVAL_REQUIRED_TOOLS:
            try:
                return json.loads(msg.content)
            except (json.JSONDecodeError, TypeError):
                return {"raw": msg.content}
    return None


def _build_chat_result(snapshot, conversation_id: str) -> dict:
    """Shape a graph state snapshot into the dict the API layer expects."""
    messages = snapshot.values.get("messages", [])
    return {
        "response": _last_assistant_text(messages),
        "citations": [],  # citations plumbing reserved; tools return text today
        "pending_action": _extract_pending_action(snapshot),
        "conversation_id": conversation_id,
    }


async def chat(
    message: str,
    conversation_id: str = "default",
    user_id: str = "anonymous",
) -> dict:
    """Send a message to the agent and get a response.

    Args:
        message: The user's (already guardrail-processed) message.
        conversation_id: Thread key for durable conversation memory.
        user_id: Owner of the conversation (for the checkpoint + future memory).

    Returns:
        Dict with response text, citations, pending_action, and conversation_id.
        If pending_action is set, the graph is paused awaiting approval; call
        resume_action() to continue.
    """
    agent = get_agent()
    config = {"configurable": {"thread_id": conversation_id}}
    input_state = {"messages": [HumanMessage(content=message)], "user_id": user_id}

    await agent.ainvoke(input_state, config=config)
    snapshot = await agent.aget_state(config)
    return _build_chat_result(snapshot, conversation_id)


async def stream_chat(
    message: str,
    conversation_id: str = "default",
    user_id: str = "anonymous",
):
    """Stream the agent's FINAL assistant answer token-by-token.

    An async generator yielding raw content deltas (strings). Only the final
    assistant answer is streamed: the `search_runbooks` decision turn emits
    empty `content` (its output is tool_call chunks), so filtering on non-empty
    `content` naturally skips it and streams only the post-search answer.

    Drives the graph exactly like chat() (same thread_id) and stops at the
    interrupt_before=["execute_action"] pause identically. After this generator
    is exhausted, call get_turn_snapshot() to read pending_action / a fallback
    answer from the durable state.
    """
    agent = get_agent()
    config = {"configurable": {"thread_id": conversation_id}}
    input_state = {"messages": [HumanMessage(content=message)], "user_id": user_id}

    async for event in agent.astream_events(input_state, config=config, version="v2"):
        if event.get("event") != "on_chat_model_stream":
            continue
        # Only the agent node calls the chat model; be robust anyway.
        if event.get("metadata", {}).get("langgraph_node") not in (None, "agent"):
            continue
        chunk = event.get("data", {}).get("chunk")
        content = getattr(chunk, "content", None)
        if content:
            yield content


async def get_turn_snapshot(conversation_id: str):
    """Return the durable state snapshot after a (possibly streamed) turn."""
    agent = get_agent()
    config = {"configurable": {"thread_id": conversation_id}}
    return await agent.aget_state(config)


def snapshot_pending_action(snapshot) -> dict | None:
    """Public wrapper: pending action from a state snapshot (or None)."""
    return _extract_pending_action(snapshot)


def snapshot_last_answer(snapshot) -> str:
    """Public wrapper: the final assistant text from a state snapshot."""
    return _last_assistant_text(snapshot.values.get("messages", []))


async def resume_action(
    conversation_id: str,
    approved: bool,
    decided_by: str = "anonymous",
) -> dict:
    """Resume a conversation paused before a side-effecting action.

    On approve: resume the graph so execute_action runs the side effect exactly
    once and the agent summarizes the result.
    On reject: inject synthetic ToolMessages (so the tool calls are answered)
    without executing anything, then resume so the agent acknowledges.

    Returns a chat-result dict plus an "execution_result" key (the executor's
    raw output, or None on rejection / nothing-to-resume).
    """
    agent = get_agent()
    config = {"configurable": {"thread_id": conversation_id}}
    snapshot = await agent.aget_state(config)

    # Idempotency guard: only act if actually paused before execute_action.
    if not snapshot.next or "execute_action" not in snapshot.next:
        result = _build_chat_result(snapshot, conversation_id)
        result["execution_result"] = None
        result["status"] = "no_pending_action"
        return result

    if approved:
        await agent.ainvoke(None, config=config)
    else:
        last = snapshot.values.get("messages", [])[-1]
        rejection_msgs = [
            ToolMessage(
                content="The user rejected this action. It was NOT executed.",
                tool_call_id=tool_call["id"],
                name=tool_call["name"],
            )
            for tool_call in (getattr(last, "tool_calls", None) or [])
        ]
        await agent.aupdate_state(
            config, {"messages": rejection_msgs}, as_node="execute_action"
        )
        await agent.ainvoke(None, config=config)

    new_snapshot = await agent.aget_state(config)
    result = _build_chat_result(new_snapshot, conversation_id)
    result["execution_result"] = (
        _extract_last_action_result(new_snapshot.values.get("messages", []))
        if approved
        else None
    )
    result["status"] = "approved" if approved else "rejected"
    return result
