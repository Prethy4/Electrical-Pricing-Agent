"""
LangGraph ReAct agent.

Graph topology:
  START → agent_node → (tool_node | END)
                ↑______________|

- agent_node  : calls the LLM with tools bound; if the model requests tool calls →
                we route to tool_node, otherwise we route to END.
- tool_node   : executes the requested tools and returns results to agent_node.

The graph is stateless per invocation; memory is loaded from PostgreSQL before
calling the graph and saved back afterwards.
"""

from typing import Annotated, Sequence, TypedDict, List, Optional

from langchain_core.messages import BaseMessage, AIMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from app.core.config import get_settings
from app.tools.registry import get_tools

settings = get_settings()

SYSTEM_PROMPT = """You are a helpful, knowledgeable assistant.
When users upload files (PDFs or CSVs), use the `search_uploaded_documents` tool to
retrieve relevant content before answering questions about those files.
Be concise but thorough. Cite sources when pulling from uploaded documents.
Today's date/time can be fetched with `get_current_datetime` if needed."""


# ── Agent State ───────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]


# ── Graph builder ─────────────────────────────────────────────────────────────

def build_agent_graph(retriever=None):
    """
    Build and compile the agent graph.
    Called once per request (lightweight; graph compilation is fast).
    Pass `retriever` when the session has uploaded files.
    """
    tools = get_tools(retriever=retriever)
    tool_node = ToolNode(tools)

    llm = ChatOpenAI(
        model=settings.openai_model,
        openai_api_key=settings.openai_api_key,
        temperature=0.2,
        streaming=False,
    ).bind_tools(tools)

    def agent_node(state: AgentState) -> AgentState:
        from langchain_core.messages import SystemMessage
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + list(state["messages"])
        response = llm.invoke(messages)
        return {"messages": [response]}

    def should_continue(state: AgentState):
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "tools"
        return END

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)

    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    return graph.compile()


# ── Run helper ────────────────────────────────────────────────────────────────

async def run_agent(
    user_message: str,
    history: List[BaseMessage],
    retriever=None,
) -> tuple[str, Optional[list]]:
    """
    Run the agent graph for one user turn.

    Returns:
        (ai_text_response, tool_calls_list_or_None)
    """
    from langchain_core.messages import HumanMessage

    graph = build_agent_graph(retriever=retriever)

    input_messages = list(history) + [HumanMessage(content=user_message)]
    result = await graph.ainvoke({"messages": input_messages})

    final_message = result["messages"][-1]
    ai_text = final_message.content if hasattr(final_message, "content") else str(final_message)
    tool_calls = getattr(final_message, "tool_calls", None) or None

    return ai_text, tool_calls
