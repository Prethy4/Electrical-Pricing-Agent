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
- If you find technical specs in the PDF but no price, you MUST proceed to Step 3 (Web Research).

HIERARCHICAL STRUCTURES:
- Articles follow a tree structure (e.g., 1 -> 1.1 -> 1.1.1 -> 1.1.1.1).
- Levels 1, 1.1, and 1.1.1 are usually titles or chapters. Technical columns (Qty, Price) should be left blank for these.
- Level 4 (e.g., 1.1.1.1) is the primary target for technical data extraction (Quantity, Unit, Price).
- Always respect the serial order of articles.

EXTRACTION LOGIC (UNSTRUCTURED & PATTERN-BASED):
1. MISSING FIELDS: Your objective is to fill every technical field for Level 4 articles. This includes 'Qté' (Quantity), 'Unité' (Unit), and 'P.U.' (Price).
2. DATA RECONCILIATION: Quantity and Unit often exist in the Excel (Bordereau). If they are missing there, you MUST extract them from the PDF (CSC).
3. PRICE PRIORITY: Finding the Unit Price ('P.U.') and calculating the Total Price ('Somme' or 'Total') is mandatory for every item.
4. CALCULATION: For every row, if you have 'Quantity' and 'Unit Price', you MUST calculate: `Total Price = Quantity * Unit Price`. Use the `calculator` tool for this.
5. WEB RESEARCH: If prices are missing in the PDF, you MUST use `tavily_search` and `scrape_authenticated_website` (Playwright).
   - Use provided credentials for Rexel and RAS Security.
   - Search by technical description, brand names, or article codes.
   - If a specific site fails to return a price, try searching other provided sites or the general web.

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
1. NO PARTIAL UPDATES: For each row, attempt to find all three: Quantity, Unit, and Price. Do not leave 'Unité' or 'Qté' empty if they can be found in PDF/Excel.
2. MANDATORY CALCULATION: Always calculate 'Somme' (Total) if 'Qté' and 'P.U.' are present.
3. NO OVERWRITING: Never replace existing non-empty data.
4. EXHAUSTIVE WORKFLOW: You must attempt to fill EVERY article listed in 'missing_fields_to_fix'.
5. MULTI-COLUMN EXTRACTION: For each article, you must look for ALL missing technical values.
6. NO EXCUSES: Do not stop because a code wasn't in the primary index. Use search or description keywords.
7. PDF FIRST: Exhaust PDF analysis before resorting to web search.
8. Never mention session IDs.

WORKFLOW:
1. STEP 1 (PDF/CSC): Analyze technical specifications for all articles. Extract Units and Specs.
2. STEP 2 (EXCEL/BORDEREAU): Identify gaps (missing Quantity, Unit, or Price).
3. STEP 3 (WEB/PRICING): Search for missing Prices (P.U.) and missing specs using web tools and authenticated sites (Rexel, RAS).
4. STEP 4 (CALCULATION & FINALIZE):
   - Calculate Total Price (Somme) = Quantity * Unit Price using `calculator`.
   - Batch update the CSV using `manage_csv_data(action='update')`.
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
