"""
LangGraph ReAct agent for CSV filling and PDF/Web research.

Graph topology:
  START → agent_node → (tool_node | END)
                ↑______________|
"""

import json
from typing import Annotated, Sequence, TypedDict, List, Optional
from langchain_core.messages import BaseMessage, AIMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from app.core.config import get_settings
from app.tools.registry import get_tools

settings = get_settings()

SYSTEM_PROMPT = """You are a high-performance, autonomous data extraction engine.
SESSION ID: {session_id}

LANGUAGE DIRECTIVE:
- Respond in French by default. Only switch to English if explicitly requested.

STRICT CONSTRAINTS (CRITICAL):
1. NO OVERWRITING: NEVER replace existing non-empty data.
2. ZERO TOLERANCE FOR OMISSIONS: You must process EVERY article. If 'missing_fields_to_fix' contains 50 items, you must address all 50. Do not stop until the count of missing fields is 0.
3. ARTICLE IDENTIFICATION: Articles have 1 to 4 segments (e.g., 0, 1.1, 1.1.1, 1.1.1.1). PRIORITIZE level 4 articles, as they contain the primary technical data tables.
4. DATA POSITIONING: If an article is in the PDF but missing from the Excel/CSV, use `manage_csv_data` (action='insert') to add it in the exact serial place relative to existing article numbers.
5. CONFIDENCE: Only add values if you are at least 75 percent confident.

RECONCILIATION WORKFLOW:
1. Call `list_session_files` to identify the targets.
2. Call `manage_csv_data(action='read')` to identify gaps (`missing_fields_to_fix`).
3. Call `list_all_pdf_articles` to see what should be in the file.
4. For each gap or missing article: Use `lookup_article_data` (PDF search) OR `tavily_search` (Web search).
5. Update the file using `manage_csv_data`:
   - Use `action='update'` for existing rows with gaps.
   - Use `action='insert'` for articles present in PDF but missing from Excel.
6. If a lookup fails, explain WHY (e.g., "Article 1.2 not found in PDF article list").

UPDATE FORMAT:
When calling `manage_csv_data` (action='update'), use:
`{{"row": <int_index>, "column": "<exact_column_name>", "value": "<found_value>"}}`

EXTRACTION PATTERNS:
Technical PDFs usually follow: [CODE] -> [DESCRIPTION] -> [TYPE] -> [QUANTITY] -> [UNIT].

FINAL RESPONSE:
Summarize the lines and columns updated in French.
"""

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]

def build_agent_graph(retriever=None, session_id: str = "unknown"):
    """
    Build and compile the agent graph.
    """
    tools = get_tools(retriever=retriever)
    tool_node = ToolNode(tools)

    llm = ChatOpenAI(
        model=settings.openai_model,
        openai_api_key=settings.openai_api_key,
        temperature=0.0,
        streaming=True,
    ).bind_tools(tools)

    def agent_node(state: AgentState) -> AgentState:
        from langchain_core.messages import SystemMessage
        messages = [SystemMessage(content=SYSTEM_PROMPT.format(session_id=session_id))] + list(state["messages"])
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

async def run_agent(
    user_message: str,
    history: List[BaseMessage],
    retriever=None,
    session_id: Optional[str] = None,
) -> tuple[str, Optional[list]]:
    from langchain_core.messages import HumanMessage
    graph = build_agent_graph(retriever=retriever, session_id=str(session_id) if session_id else "unknown")
    input_messages = list(history) + [HumanMessage(content=user_message)]
    result = await graph.ainvoke({"messages": input_messages})
    final_message = result["messages"][-1]
    ai_text = final_message.content if hasattr(final_message, "content") else str(final_message)
    tool_calls = getattr(final_message, "tool_calls", None) or None
    return ai_text, tool_calls
