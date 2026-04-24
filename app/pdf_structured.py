import logging
from typing import List, Dict

try:
    from unstructured.partition.pdf import partition_pdf
except (ImportError, Exception):
    partition_pdf = None

logger = logging.getLogger(__name__)

async def process_pdf_structured(file_path: str) -> List[Dict]:
    """
    Performs layout-aware parsing of PDF files to preserve tables and sections.
    """
    if partition_pdf is None:
        logger.warning("The 'unstructured' library is not available or its dependencies (like ONNX) are broken. Skipping structured parsing.")
        return []

    try:
        # hi_res strategy uses layout analysis to identify tables and text blocks
        elements = partition_pdf(
            filename=file_path,
            strategy="hi_res",
            infer_table_structure=True,
            chunking_strategy="by_title",
            max_characters=4000,
            new_after_n_chars=3800,
        )

        structured_data = []
        for el in elements:
            element_type = "table" if "Table" in str(type(el)) else "section"
            content = el.text
            
            structured_data.append({
                "content": content,
                "type": element_type,
                "metadata": {
                    "source": file_path,
                    "preview": content[:100] + "..." if content else ""
                }
            })
        
        return structured_data
    except Exception as e:
        logger.error(f"Error in layout-aware PDF parsing: {e}")
        return []