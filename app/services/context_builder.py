import logging
from typing import List, Dict, Any
from app.services.article_parser import extract_article_code, get_hierarchy_level

logger = logging.getLogger(__name__)

def build_context_tree(rows: List[Dict[str, Any]], mapping: Dict[str, str] = None) -> List[Dict[str, Any]]:
    """
    Reconstructs the hierarchy from flat CSV rows using article codes.
    Each row receives a '_context' field containing its parent descriptions.
    """
    context_stack: Dict[int, str] = {}
    hierarchical_rows = []
    mapping = mapping or {}

    # Find which raw column names map to our logic-critical fields
    inv_map = {v: k for k, v in mapping.items()}
    article_col = inv_map.get("article_code", "article")
    desc_col = inv_map.get("description", "description")

    for row in rows:
        # Use the mapped column names to extract the key data
        raw_article = str(row.get(article_col, "") or row.get("article", "") or row.get("Code", ""))
        code = extract_article_code(raw_article)
        description = str(row.get(desc_col, "") or row.get("description", "") or row.get("Designation", ""))

        if code:
            level = get_hierarchy_level(code)
            context_stack[level] = description
            
            # Clean stack: remove levels deeper than current
            levels_to_remove = [l for l in context_stack if l > level]
            for l in levels_to_remove:
                del context_stack[l]

            # Reconstruct path
            full_context = [context_stack[l] for l in sorted(context_stack.keys()) if l <= level]
            
            row["_article_code"] = code
            row["_hierarchy_level"] = level
            row["_context"] = full_context
            
            logger.info(f"ARTICLE: {code} | CONTEXT: {full_context}")
        
        hierarchical_rows.append(row)
    
    return hierarchical_rows