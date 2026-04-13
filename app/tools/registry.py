"""
Tool registry.

To add a new tool:
1. Create a function decorated with @tool (or a BaseTool subclass) in this file
   or import it from a separate module in this package.
2. Add it to REGISTERED_TOOLS list at the bottom.

The agent graph will automatically pick up all registered tools.
"""

from langchain_core.tools import create_retriever_tool, tool

# ── Built-in tools ─────────────────────────────────────────────────────────────

@tool
def calculator(expression: str) -> str:
    """Evaluate a simple arithmetic expression. Input: a Python math expression string."""
    try:
        # Safe eval — only math operations
        allowed = {k: v for k, v in __import__("math").__dict__.items() if not k.startswith("_")}
        result = eval(expression, {"__builtins__": {}}, allowed)  # noqa: S307
        return str(result)
    except Exception as e:
        return f"Error evaluating expression: {e}"


@tool
def get_current_datetime(dummy: str = "") -> str:
    """Return the current date and time in ISO format."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ── Add your custom tools below ───────────────────────────────────────────────
# Example:
#
# @tool
# def search_web(query: str) -> str:
#     """Search the web for up-to-date information."""
#     ...
#
# from app.tools.my_custom_tool import my_tool


# ── Registry ──────────────────────────────────────────────────────────────────

REGISTERED_TOOLS = [
    calculator,
    get_current_datetime,
    # add more tools here
]


def get_tools(retriever=None):
    """
    Return the full list of tools for the agent.
    If a retriever is provided (i.e. files were uploaded),
    a document-search tool is prepended.
    """
    tools = list(REGISTERED_TOOLS)

    if retriever is not None:
        doc_tool = create_retriever_tool(
            retriever,
            name="search_uploaded_documents",
            description=(
                "Search through the documents (PDF/CSV files) uploaded by the user "
                "in this session. Use this tool first when the user asks about file contents, "
                "data in a spreadsheet, document details, or anything that might be in the files."
            ),
        )
        tools.insert(0, doc_tool)

    return tools
