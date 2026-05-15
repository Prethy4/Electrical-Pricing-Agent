"""
Tool registry.

To add a new tool:
1. Create a function decorated with @tool (or a BaseTool subclass) in this file
   or import it from a separate module in this package.
2. Add it to REGISTERED_TOOLS list at the bottom.

The agent graph will automatically pick up all registered tools.
"""

from langchain_core.tools import create_retriever_tool, tool
from app.tools.web_scraper import scrape_knowledge_base, tavily_search
from app.tools.csv_tool import manage_csv_data, list_session_files
from app.tools.example_tool import summarize_numbers
from app.services.article_parser import normalize_article_code
from app.tools.playwright_tool import scrape_authenticated_website
from app.services.file_service import get_article_data, _article_stores
from uuid import UUID

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

@tool
def lookup_article_data(session_id: str, article_code: str) -> str:
    """
    Perform a deterministic lookup of a specific article code in the uploaded PDFs.
    Returns text and table data associated specifically with that code.
    """
    # On normalise le code reçu (de l'Excel ou de l'IA) pour correspondre à l'index PDF
    normalized_code = normalize_article_code(article_code)
    data = get_article_data(UUID(session_id), normalized_code)
    if not data:
        return f"Code article '{article_code}' (normalisé: {normalized_code}) non trouvé dans l'index déterministe."
    
    output = [f"--- DONNÉES POUR L'ARTICLE {article_code} ---"]
    if data.get("context"):
        output.append(f"CONTEXTE : {' '.join(data['context'])}")
    output.append("CONTENU :")
    output.extend(data.get("data_fragments", []))
    return "\n".join(output)

@tool
def list_all_pdf_articles(session_id: str) -> str:
    """
    Returns a list of all unique article codes discovered across all uploaded PDFs.
    Use this to see what articles exist in the documentation that might be missing from the CSV.
    """
    store = _article_stores.get(session_id, {})
    if not store:
        return "No articles found in the PDF index."
    return "Articles discovered in PDFs: " + ", ".join(sorted(store.keys()))

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
    scrape_knowledge_base,
    tavily_search,
    manage_csv_data,
    list_session_files,
    summarize_numbers,
    lookup_article_data,
    list_all_pdf_articles,
    scrape_authenticated_website
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
