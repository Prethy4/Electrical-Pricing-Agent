from typing import Annotated, List, Dict, Any, TypedDict
from operator import add

class GraphState(TypedDict):
    """
    Represents the state of our LangGraph workflow.
    """
    session_id: str
    csv_file_path: str
    pdf_file_paths: List[str]
    # List of missing fields found in the CSV: [{'row': 0, 'column': 'VAT', 'status': 'missing'}]
    missing_fields: List[Dict[str, Any]]
    # Accumulated knowledge from PDF and Web searches
    knowledge_base_context: str
    # Final data to be written back to CSV
    updated_rows: List[Dict[str, Any]]
    # Control flag for user clarification
    requires_clarification: bool
    clarification_message: str
    # History of messages for the LLM
    messages: Annotated[List[Any], add]