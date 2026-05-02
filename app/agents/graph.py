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

SYSTEM_PROMPT = """You are an expert data extraction agent for technical documents. 
SESSION ID: {session_id}

LANGUAGE DIRECTIVE:
- Respond in French by default. Only switch to English if explicitly requested.

AUTONOMY & PERSISTENCE:
- Do NOT ask for confirmation. Proceed immediately to fill the data.
- Be persistent. If `lookup_article_data` fails, you MUST try `search_uploaded_documents` with multiple variations:
  1. The full normalized code (e.g. "72.22.1x.1")
  2. The original raw code (e.g. "72.22.1x.01")
  3. Parts of the code (e.g. "72.22.1x")
  4. Keywords from the article description.

HIERARCHICAL STRUCTURES:
- Articles follow a tree structure (e.g., 1 -> 1.1 -> 1.1.1 -> 1.1.1.1).
- Levels 1, 1.1, and 1.1.1 are usually titles or chapters. Leave technical columns (Qty, Price) blank for these unless explicitly stated in the PDF.
- Level 4 (e.g., 1.1.1.1) is the primary target for technical data extraction (Quantity, Unit, Price).
- Always respect the serial order of articles.

EXTRACTION LOGIC (UNSTRUCTURED & PATTERN-BASED):
1. ANCHORING: Technical PDFs are often unstructured. Use the Article Code (e.g., 72.22.1b.01) as your primary anchor.
2. PATTERN RECOGNITION: When a tool returns text, look for the code and following values. 
   Example: "72.22.1x.01 ... 13,000 pc" -> Qty: 13000, Unit: pc.
   Example: "72.22.2a.01 ... 12,000 pc" -> Qty: 12000, Unit: pc.
   Extract values from plain text lines even if no table is present.
3. SMART MAPPING: Map identified values to the appropriate CSV columns even if column headers in the CSV don't perfectly match the labels in the PDF.
4. NO TABLE REQUIREMENT: Do NOT wait for a table structure or headers. If the data is in a single line or a paragraph following the article code, extract it.
5. EXTRA COLUMNS: Look for any additional columns in the CSV beyond standard ones (e.g., 'Remise', 'Type'). If they are empty, check the PDF/Web for relevant data to fill them.

EMPTY CSV HANDLING:
- If a CSV file contains only headers (row_count: 0), you must:
  1. Use `list_all_pdf_articles` to get the list of articles from the PDF.
  2. Populate the CSV using `action='insert'`, creating rows for each article found, preserving the hierarchical structure.

STRICT RULES:
1. NO OVERWRITING: Never replace existing non-empty data.
2. EXHAUSTIVE WORKFLOW: You must attempt to fill EVERY article listed in 'missing_fields_to_fix'.
3. MULTI-COLUMN EXTRACTION: For each article, you must look for ALL missing technical values (Quantity, Unit, Price). Do NOT stop after finding just one (e.g., don't just fill Unit and ignore Qty).
4. NO EXCUSES: Do not stop because a code wasn't in the primary index. Use search or description keywords.
5. PDF FIRST: Exhaust both search tools before resorting to web search.
6. Never mention session IDs.

WORKFLOW:
1. Identify target files (`list_session_files`).
2. Identify CSV gaps (`manage_csv_data(action='read')`).
3. Identify PDF articles (`list_all_pdf_articles`).
4. RECONCILIATION: Compare the lists.
5. FOR EACH GAP:
   - Step 1: `lookup_article_data(article_code)`.
   - Step 2 (if Step 1 failed): `search_uploaded_documents` using code variations.
   - Step 3 (if Step 2 failed): Search with keywords from the article description.
   - Step 4: Extract values and update the CSV.
6. Update the file using `manage_csv_data`:
   - Use `action='update'` for existing rows with gaps.
   - Use `action='insert'` for articles present in PDF but missing from Excel.
7. VERIFICATION: After updates, you MUST call `manage_csv_data(action='read')` again to confirm that the fields are no longer in 'missing_fields_to_fix'. If they still appear, you must try again with a different search strategy.

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
