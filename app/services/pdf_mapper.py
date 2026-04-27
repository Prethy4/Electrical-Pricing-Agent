import logging
from typing import List, Dict, Any
from app.services.article_parser import extract_article_code, normalize_article_code

logger = logging.getLogger(__name__)

def extract_pdf_articles(structured_blocks: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Maps article codes found in PDF blocks to their specific data/tables.
    """
    pdf_map = {}
    last_seen_code = None
    buffer_text = []
    
    for block in structured_blocks:
        full_content = block.get("content", "")
        lines = full_content.splitlines()
        
        for line in lines:
            content = line.strip()
            if not content:
                continue
                
            code = extract_article_code(content)
            target_code = code or last_seen_code # Normalisé par extract_article_code
            
            if not target_code:
                buffer_text.append(content)
                continue

            if target_code not in pdf_map:
                pdf_map[target_code] = {
                    "context": [],
                    "data_fragments": [],
                    "is_table": block.get("type") == "table"
                }
            
            if code and buffer_text:
                # Associe le texte orphelin (titres de sections, lots) comme contexte
                pdf_map[target_code]["context"].extend(buffer_text)
                buffer_text = []

            pdf_map[target_code]["data_fragments"].append(content)
            
            if code:
                last_seen_code = code
                logger.info(f"PDF_MATCH: Article {code} indexé")
            else:
                logger.debug(f"PDF_APPEND: Contenu lié à l'article {last_seen_code}")

    return pdf_map