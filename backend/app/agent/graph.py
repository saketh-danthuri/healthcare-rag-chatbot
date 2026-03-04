"""
graph.py - LangGraph Agent Definition
========================================
WHY LANGGRAPH:
  LangGraph gives us a stateful agent with:
  1. Multi-step reasoning (search -> analyze -> act -> respond)
  2. Tool calling (the LLM decides when to search, email, or query DB)
  3. Human-in-the-loop interrupts (pause before executing actions)
  4. Conversation memory (state persists across turns)

  Unlike a simple "prompt + retrieve + generate" chain, this agent can:
  - Search multiple times if the first search isn't specific enough
  - Decide to escalate based on what it finds in runbooks
  - Ask for approval before sending emails
  - Chain multiple tools in sequence

GRAPH STRUCTURE:
  START -> agent_node -> (tool call?) -> tool_node -> agent_node -> ... -> END

  The agent_node calls the LLM which either:
  a) Responds directly (END)
  b) Calls a tool (routes to tool_node, which executes and loops back)
"""

import logging
from pathlib import Path

import yaml
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from app.agent.tools import ALL_TOOLS, APPROVAL_REQUIRED_TOOLS
from app.config.settings import get_settings

logger = logging.getLogger(__name__)


def _load_system_prompt() -> str:
    """Load the system prompt from prompts.yaml."""
    prompts_path = Path(__file__).parent.parent / "config" / "prompts.yaml"
    with open(prompts_path) as f:
        prompts = yaml.safe_load(f)
    return prompts["prompts"]["system_prompt"]


def _create_llm() -> AzureChatOpenAI:
    """Create the Azure OpenAI LLM client with tool-calling support.

    WHY AzureChatOpenAI: This is LangChain's wrapper around the Azure OpenAI
    API. It handles authentication, retries, and streaming. The bind_tools()
    method converts our Python tool functions into the OpenAI function-calling
    format that GPT-4o-mini understands natively.
    """
    settings = get_settings()

    llm = AzureChatOpenAI(
        azure_deployment=settings.azure_openai_chat_deployment,
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        temperature=0.1,  # Low temperature for factual, consistent answers
        max_tokens=2048,
    )

    # Bind tools so the LLM knows what functions it can call
    return llm.bind_tools(ALL_TOOLS)


def _should_continue(state: dict) -> str:
    """Routing function: decide if the agent should continue or stop.

    After the LLM responds, check if it wants to call a tool:
    - If there are tool calls in the last message -> route to "tools" node
    - If no tool calls -> route to END (respond to user)

    This creates the agent loop: agent -> tools -> agent -> tools -> ... -> END
    """
    messages = state.get("messages", [])
    if not messages:
        return END

    last_message = messages[-1]

    # Check if the LLM wants to call tools
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        # Check if any tool requires approval
        for tool_call in last_message.tool_calls:
            if tool_call["name"] in APPROVAL_REQUIRED_TOOLS:
                # Route to approval node instead of direct execution
                return "check_approval"
        return "tools"

    return END


def _agent_node(state: dict) -> dict:
    """The main agent node - calls the LLM to decide what to do.

    This node:
    1. Prepends the system prompt to the conversation
    2. Calls GPT-4o-mini with the full message history
    3. The LLM either responds directly or requests tool calls
    4. Returns the updated state with the new message

    WHY system prompt here (not in graph setup): The system prompt is
    loaded fresh from prompts.yaml each time, so prompt changes take
    effect without restarting the server.
    """
    llm = _create_llm()
    system_prompt = _load_system_prompt()

    messages = state.get("messages", [])

    # Prepend system message if not already there
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=system_prompt)] + messages

    response = llm.invoke(messages)

    return {"messages": [response]}


def _check_approval_node(state: dict) -> dict:
    """Node that intercepts tool calls requiring human approval.

    WHY: Instead of executing send_email or query_database immediately,
    this node catches the tool call and adds a message asking for approval.
    The conversation pauses here until the user responds.

    In practice, the FastAPI endpoint detects the pending approval in the
    response and sends it to the frontend for user review.
    """
    messages = state.get("messages", [])
    last_message = messages[-1]

    if hasattr(last_message, "tool_calls"):
        for tool_call in last_message.tool_calls:
            if tool_call["name"] in APPROVAL_REQUIRED_TOOLS:
                # Mark this as requiring approval
                # The API layer will detect this and pause for user input
                return {
                    "pending_action": {
                        "tool_name": tool_call["name"],
                        "tool_call_id": tool_call["id"],
                        "arguments": tool_call["args"],
                        "status": "pending_approval",
                    }
                }

    # If no approval needed, pass through to tool execution
    return state


def build_agent_graph() -> StateGraph:
    """Build the LangGraph agent graph.

    GRAPH FLOW:
    1. User message arrives -> agent_node (LLM decides what to do)
    2. If LLM wants to call a tool:
       a. If tool needs approval -> check_approval -> PAUSE -> (user approves) -> tools -> agent
       b. If tool is safe -> tools -> agent (loop back)
    3. If LLM responds directly -> END

    Returns a compiled graph that can be invoked with state.
    """
    from langgraph.graph import MessagesState

    # Create the graph with message-based state
    graph = StateGraph(MessagesState)

    # Add nodes
    graph.add_node("agent", _agent_node)
    graph.add_node("tools", ToolNode(ALL_TOOLS))
    graph.add_node("check_approval", _check_approval_node)

    # Set the entry point
    graph.set_entry_point("agent")

    # Add conditional edges from agent node
    graph.add_conditional_edges(
        "agent",
        _should_continue,
        {
            "tools": "tools",  # Safe tools -> execute directly
            "check_approval": "check_approval",  # Dangerous tools -> approval
            END: END,  # No tools -> respond
        },
    )

    # After tool execution, loop back to agent
    graph.add_edge("tools", "agent")

    # After approval check, execute tools and loop back
    graph.add_edge("check_approval", "tools")

    return graph


# Module-level compiled graph (singleton)
_compiled_graph = None
_memory = None


def get_agent():
    """Get or create the compiled agent graph with memory checkpointing.

    WHY MemorySaver: Persists conversation state across multiple API calls.
    Each user session gets its own thread_id, so conversations don't mix.
    In production, you'd swap MemorySaver for a persistent store (Redis, Postgres).
    """
    global _compiled_graph, _memory

    if _compiled_graph is None:
        _memory = MemorySaver()
        graph = build_agent_graph()
        _compiled_graph = graph.compile(checkpointer=_memory)
        logger.info("Agent graph compiled successfully")

    return _compiled_graph


async def chat(
    message: str,
    session_id: str = "default",
) -> dict:
    """Send a message to the agent and get a response.

    This is the main function the API calls. It:
    1. Gets the compiled agent graph
    2. Sends the user message with the session's thread_id
    3. Returns the agent's response (text, citations, or pending action)

    Args:
        message: The user's message
        session_id: Unique session identifier for conversation memory

    Returns:
        Dict with response text, citations, and any pending actions
    """
    agent = get_agent()

    config = {"configurable": {"thread_id": session_id}}
    input_message = {"messages": [HumanMessage(content=message)]}

    # Invoke the agent graph
    result = agent.invoke(input_message, config=config)

    # Extract the last AI message
    messages = result.get("messages", [])
    ai_messages = [m for m in messages if isinstance(m, AIMessage)]

    response_text = ""
    pending_action = None
    tool_results = []

    if ai_messages:
        last_ai = ai_messages[-1]
        response_text = last_ai.content or ""

        # Check for pending approval actions
        if hasattr(last_ai, "tool_calls") and last_ai.tool_calls:
            for tc in last_ai.tool_calls:
                if tc["name"] in APPROVAL_REQUIRED_TOOLS:
                    pending_action = {
                        "tool_name": tc["name"],
                        "arguments": tc["args"],
                        "status": "pending_approval",
                    }

    # Check if any tool messages contain results
    from langchain_core.messages import ToolMessage

    for m in messages:
        if isinstance(m, ToolMessage):
            tool_results.append(
                {
                    "tool_name": m.name,
                    "content": m.content,
                }
            )

    return {
        "response": response_text,
        "pending_action": pending_action,
        "tool_results": tool_results,
        "session_id": session_id,
    }
