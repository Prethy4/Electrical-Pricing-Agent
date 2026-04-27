import json
import logging
from typing import List, Dict, Any
from openai import AsyncOpenAI
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

client = AsyncOpenAI(api_key=settings.openai_api_key)

CANONICAL_FIELDS = ["article_code", "description", "unit", "quantity", "unit_price", "total_price"]

async def infer_csv_schema(headers: List[str], sample_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Uses LLM to map raw CSV headers to a canonical schema.
    Returns a mapping dict and a confidence score.
    """
    logger.info(f"CSV SCHEMA INFERENCE | RAW HEADERS: {headers}")

    prompt = f"""
    You are a data architect specializing in French technical quantity surveys. Your task is to map raw CSV headers to a canonical schema.
    
    Canonical Fields:
    - article_code (Ex: Article, Code, N°, Référence)
    - description (Ex: Dénomination, Désignation, Libellé, Texte)
    - unit (Ex: Unité, Unit, U)
    - quantity (Ex: Qté, Qte, Quantité, Mesurage)
    - unit_price (Ex: P.U., Prix Unitaire, Unit Price)
    - total_price (Ex: Somme, Total, Montant, Prix Total)

    Instructions:
    1. Map every raw header to the most likely canonical field.
    2. If a header does not fit any canonical field, map it to "unknown".
    3. Use the provided sample rows to resolve ambiguity (e.g., if a header is "Val", check if values look like prices).
    4. Return ONLY a valid JSON object.

    Headers: {headers}
    Sample Data: {json.dumps(sample_rows)}

    Return format:
    {{
        "mapping": {{ "raw_col_1": "canonical_field", ... }},
        "confidence": 0.0-1.0,
        "reasoning": "brief explanation"
    }}
    """

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",  # Faster model for mapping tasks
            messages=[{"role": "system", "content": "You are a specialized data mapping assistant."},
                      {"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0
        )
        
        result = json.loads(response.choices[0].message.content)
        
        # Validation: Ensure all headers are present in mapping
        mapping = result.get("mapping", {})
        for h in headers:
            if h not in mapping:
                mapping[h] = "unknown"
        
        logger.info(f"INFERRED SCHEMA: {mapping}")
        logger.info(f"CONFIDENCE: {result.get('confidence', 'N/A')}")
        
        return {
            "mapping": mapping,
            "confidence": result.get("confidence", 0)
        }
    except Exception as e:
        logger.error(f"Schema inference failed: {e}")
        # Fallback: All unknown
        return {
            "mapping": {h: "unknown" for h in headers},
            "confidence": 0
        }