import re
from typing import Optional

def extract_article_code(text: str) -> Optional[str]:
    """
    Extracts article codes like 72.22.1b.01 from text.
    Pattern: digits separated by dots, potentially containing a single letter.
    """
    # Matches patterns like 72.22.1, 72.22.1b, 72.22.1b.01 and allows internal spaces (72.22.01. 01)
    pattern = r'(\d+(?:\s*\.\s*\d+)*(?:\s*[a-zA-Z])?(?:\s*\.\s*\d+)*)'
    match = re.search(pattern, text)
    return match.group(1) if match else None

def get_hierarchy_level(code: str) -> int:
    """
    Determines the depth of the article code in the hierarchy.
    Example: 
    72.22.1 -> level 2
    72.22.1b -> level 3
    72.22.1b.01 -> level 4
    """
    dot_count = code.count('.')
    alpha_count = len([c for c in code if c.isalpha()])
    return dot_count + alpha_count