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

CORE MISSION:
Identify and fill missing technical values (Price, Quantity, Unit) in the CSV or Excel detail lines (terminal articles). 
ALWAYS verify the actual filenames in the current session using the provided tools before making any assumptions about file availability or names.

ERROR HANDLING:
If you encounter a reading error, do not simply report an "encoding" issue. Use `list_session_files` to confirm the file exists and try reading it again.

STRICT CONSTRAINTS (CRITICAL):
1. NO NEW COLUMNS: Do NOT ever create new columns (like _source, _confidence). ONLY update existing columns provided in the 'columns' list.
2. NO PLACEHOLDERS: Never fill fields with 'noos', 'None', 'nan', '***', or any fictitious data. If info is not found, leave the field blank and skip the update for that cell.
3. ROW SELECTION: Focus on terminal articles (codes with 3 or 4 segments like '72.22.01' or '06.22.1x.01'). NEVER update general document metadata (Chantier, Client).
4. VISUAL PRESERVATION: Excel formatting (colors, images, and fonts) is preserved during updates. Use `manage_csv_data` (action='update') confidently.

RECOVERY STRATEGY:
1. INITIAL EXPLORATION: You MUST always start by calling `list_session_files` to verify exactly which CSV, Excel, and PDF files are available in the current session. NEVER guess or assume filenames.
2. GLOBAL AUDIT: Call `manage_csv_data` (action='read') with the correct CSV or Excel filename discovered in step 1 to get the `missing_fields_to_fix` list.
2. RECONCILIATION:
   - Cross-check the articles in `missing_fields_to_fix` against the articles found in `list_all_pdf_articles`.
   - For every article with missing technical values, use `lookup_article_data` to get specific info.
   - If not found, use `search_uploaded_documents`.
   - Bundle ALL findings into a SINGLE call to `manage_csv_data` (action='update').

AUTONOMY & TRANSPARENCY:
- Do not stop after one article. Aim to complete the entire file.
- ALWAYS explain which articles and values you found in the chat before calling the update tool.

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
        streaming=False,
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
