import logging
from difflib import SequenceMatcher
from typing import Dict

logger = logging.getLogger(__name__)

def match_product(csv_name: str, candidate_text: str) -> Dict[str, Any]:
    """
    Matches a product name from a CSV against text extracted from another source.
    """
    if not csv_name or not candidate_text:
        return {"match": False, "confidence": 0}

    # Clean and compare
    s1 = str(csv_name).lower().strip()
    s2 = str(candidate_text).lower().strip()
    
    ratio = SequenceMatcher(None, s1, s2).ratio()
    is_match = ratio > 0.75
    
    logger.info(f"ENTITY_MATCHING | CSV: '{s1}' | Target: '{s2[:30]}...' | Score: {ratio:.2f}")
    
    return {"match": is_match, "confidence": round(ratio, 2)}