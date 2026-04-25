import os
import json
import csv
import re
import pandas as pd
from pathlib import Path
import logging
import shutil
from openpyxl import load_workbook
from typing import List, Dict, Any, Optional, Tuple
from app.core.config import get_settings
from app.services.article_parser import extract_article_code

settings = get_settings()
logger = logging.getLogger(__name__)

# Keywords used to identify the primary article/code column
ARTICLE_KEYWORDS = ["article", "code", "réf", "n°", "art.", "item"]

def normalize_number(x: Any) -> Optional[float]:
    """Normalize numeric strings by handling French currency and decimal separators."""
    if x is None or x == "" or (isinstance(x, str) and x.lower() == "nan"):
        return None
    
    # Clean string: remove currency symbols and whitespace
    s = str(x).strip()
    s = re.sub(r'[€$£%]', '', s)
    s = re.sub(r'\s+', '', s)
    
    # Handle thousands and decimal separators
    if ',' in s and '.' in s:
        # Determine if French (1.200,50) or English (1,200.50)
        if s.rfind(',') > s.rfind('.'):
            s = s.replace('.', '').replace(',', '.')
        else:
            s = s.replace(',', '')
    elif ',' in s:
        # Common French decimal or English thousands
        s = s.replace(',', '.')
    elif s.count('.') > 1:
        # Multiple dots indicate thousands separators (e.g. 1.000.000)
        s = s.replace('.', '')
        
    try:
        val = float(s)
        if val.is_integer():
            return int(val)
        return val
    except (ValueError, TypeError):
        return None

def list_session_files(session_id: str) -> List[str]:
    """
    Lists all files available in the upload directory for a specific session.
    """
    session_dir = Path(settings.upload_dir) / session_id
    if not session_dir.exists() or not session_dir.is_dir():
        return []
    
    return [f.name for f in session_dir.iterdir() if f.is_file()]

def find_header_row(file_path: Path, encoding: str, sep: str) -> int:
    """Locates the index of the header row by looking for French technical keywords."""
    try:
        with open(file_path, 'r', encoding=encoding, errors='replace') as f:
            for i, line in enumerate(f):
                lower_line = line.lower()
                # Check for standard BOQ headers
                if "article" in lower_line and ("dénomination" in lower_line or "désignation" in lower_line or "unité" in lower_line):
                    return i
    except Exception:
        pass
    return 0

def manage_csv_data(session_id: str, filename: str, action: str = "read", updates: Optional[List[Dict[str, Any]]] = None) -> str:
    """
    Manages CSV data.
    Action 'read': returns structure and missing field info.
    Action 'update': applies found information to the file.
    """
    base_dir = Path(settings.upload_dir) / session_id
    is_excel = filename.lower().endswith('.xlsx')
    
    # Versioning Logic: Always prefer the most recently updated version as the source
    current_filename = filename
    if not filename.startswith("updated_"):
        potential_updated = base_dir / f"updated_{filename}"
        if potential_updated.exists():
            current_filename = f"updated_{filename}"
            logger.info(f"CSV_VERSIONING | Using latest version: {current_filename}")

    file_path = base_dir / current_filename
    
    if not file_path.exists():
        return f"Error: File '{filename}' not found."

    # Ensure the directory for updates exists
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        if is_excel:
            # Detect header row for Excel by scanning first 20 rows
            header_check = pd.read_excel(file_path, nrows=20, header=None, engine='openpyxl')
            header_idx = 0
            for i, row in header_check.iterrows():
                row_vals = [str(v).strip().lower() for v in row.values if v is not None]
                # Identify the row containing "Article" and technical headers
                if any(k in row_vals for k in ["article", "art.", "code", "réf"]) and \
                   any(k in " ".join(row_vals) for k in ["dénomination", "désignation", "unité", "qté", "quantité", "p.u", "somme"]):
                    header_idx = i
                    break
            
            df = pd.read_excel(file_path, dtype=str, engine='openpyxl', header=header_idx)
            encoding = 'utf-8' # Not used for writing excel but for consistency
        else:
            # Robust encoding and separator detection for CSV
            encoding = None
            sep = ','
            for enc in ['utf-8-sig', 'utf-8', 'cp1252', 'latin-1']:
                try:
                    with open(file_path, 'r', encoding=enc) as f:
                        sample = f.read(8192)
                        if not sample: continue
                        dialect = csv.Sniffer().sniff(sample)
                        sep = dialect.delimiter
                        encoding = enc
                        break
                except Exception:
                    continue
            
            if not encoding:
                encoding = 'utf-8'
                sep = ';' if ';' in open(file_path, 'r', encoding='utf-8', errors='replace').read(1024) else ','

            # Header detection: identify metadata rows to preserve design
            header_idx = find_header_row(file_path, encoding, sep)
            
            # Load CSV starting from the detected header row
            df = pd.read_csv(file_path, encoding=encoding, sep=sep, engine='python', dtype=str, header=header_idx)

        if action == "update" and updates:
            # Apply updates provided by the LLM
            new_filename = filename if filename.startswith("updated_") else f"updated_{filename}"
            new_file_path = file_path.parent / new_filename
            article_col = next((c for c in df.columns if any(k in str(c).lower() for k in ARTICLE_KEYWORDS)), None)
            
            logger.info(f"CSV_UPDATE_EXECUTION | File: {filename} | Updates: {len(updates)}")
            
            # Excel specific logic to preserve formatting
            if is_excel:
                # 1. Copy original file to the new path to preserve formatting/images/styles
                if file_path != new_file_path:
                    shutil.copy2(file_path, new_file_path)
                wb = load_workbook(new_file_path)
                ws = wb.active
                # Map column names to 1-based indices
                col_map = {col: i + 1 for i, col in enumerate(df.columns)}
                
            for upd in updates:
                try:
                    row_idx = int(upd.get("row"))
                except (ValueError, TypeError):
                    continue

                col_name = upd.get("column")
                raw_val = upd.get("value")
                
                norm_val = normalize_number(raw_val)
                
                if norm_val is not None:
                    val_to_assign = norm_val
                elif raw_val is not None and str(raw_val).strip().lower() not in ["noos", "none", "nan", "null", ""]:
                    val_to_assign = str(raw_val)
                else:
                    val_to_assign = None 
                
                if col_name not in df.columns:
                    logger.warning(f"SKIP_NEW_COL | {col_name} is not in original CSV. Skipping.")
                    continue

                if row_idx < len(df):
                    # Safety: Skip metadata rows or chapter titles
                    if article_col:
                        row_val = str(df.at[row_idx, article_col]).strip()
                        # Skip only high-level headers. Allow items even if they contain 'total' unless it's the absolute final row.
                        is_doc_metadata = any(k in row_val.lower() for k in ["chantier", "client", "projet", "devis n"])
                        is_final_total = "total général" in row_val.lower() or row_val.lower() == "total"

                        if not row_val or row_val.lower() in ["nan", "none"] or is_doc_metadata or is_final_total:
                            continue

                    if is_excel:
                        # Excel row = df_idx + header_idx + 1 (1-indexed) + 1 (data starts after header)
                        excel_row = row_idx + header_idx + 2
                        excel_col = col_map.get(col_name)
                        if excel_col:
                            ws.cell(row=excel_row, column=excel_col).value = val_to_assign
                            logger.info(f"EXCEL_CELL_FILL: {col_name} at Row {excel_row}")
                    else:
                        # Fallback for CSV
                        df.at[row_idx, col_name] = val_to_assign

            if is_excel:
                wb.save(new_file_path)
                return json.dumps({"status": "success", "message": f"Updated {len(updates)} fields in Excel {filename} (formatting preserved)"})
            else:
                # Standard CSV save logic
                with open(new_file_path, 'w', encoding=encoding, newline='') as f:
                    # If updating the same file, we need to read from the original
                    source_for_headers = file_path
                    if filename.startswith("updated_") and (base_dir / filename.replace("updated_", "")).exists():
                         source_for_headers = base_dir / filename.replace("updated_", "")
                    with open(source_for_headers, 'r', encoding=encoding, errors='replace') as old_f:
                        for _ in range(header_idx):
                            f.write(old_f.readline())
                    df.to_csv(f, index=False, encoding=encoding, sep=sep, quoting=csv.QUOTE_MINIMAL, na_rep="", float_format='%.10g')
                return json.dumps({"status": "success", "message": f"Updated {len(updates)} fields in CSV {filename}"})
            
        # Global Missing Field Detection
        # Identifies terminal articles (3+ segments) with empty technical columns
        missing_audit = []
        article_col = next((c for c in df.columns if any(k in str(c).lower() for k in ARTICLE_KEYWORDS)), None)
        # Expanded keywords and removed 'unnamed' restriction to catch columns in merged Excel headers
        tech_keywords = ["qt", "p.u", "somme", "prix", "unit", "montant", "total", "qte", "quantité", "ht", "tva"]
        tech_cols = [c for c in df.columns if any(k in str(c).lower() for k in tech_keywords)]
        
        def is_val_missing(val):
            s = str(val).strip().lower()
            # More comprehensive check for empty or zero values in financial documents
            return not s or s in ["nan", "none", "0", "0.0", "0,00", "0.00", "0,00 €", "0.00 €", "0,00€", "-", "/", "none"]

        if article_col:
            for idx, row in df.iterrows():
                art_val = str(row[article_col]).strip()
                # Detect if the row is a valid article (at least one numeric segment)
                code = extract_article_code(art_val)
                is_doc_metadata = any(k in art_val.lower() for k in ["chantier", "client", "projet", "devis n"])
                is_final_total = "total général" in art_val.lower() or art_val.lower() == "total"
                
                if code and not is_doc_metadata and not is_final_total:
                    missing_in_row = [c for c in tech_cols if is_val_missing(row[c])]
                    if missing_in_row:
                        missing_audit.append({"row": idx, "article": art_val, "missing_columns": missing_in_row})

        # Return all columns so LLM can see 'Unnamed' columns that might contain data
        valid_columns = list(df.columns)
        sample_data = df.head(50).to_dict(orient="records")

        summary = {
            "status": "success",
            "current_file": current_filename,
            "columns": valid_columns,
            "row_count": len(df),
            "missing_fields_to_fix": missing_audit, # Full list of all missing fields in the entire file
            "sample_data": sample_data,
            "instruction": (
                "1. Iterate through 'missing_fields_to_fix' completely. "
                "2. Use the 'row' index provided. "
                "3. Cross-reference with 'list_all_pdf_articles' to find PDF articles not in the CSV."
            )
        }
        return json.dumps(summary, ensure_ascii=False)
    except ImportError as ie:
        error_msg = f"Dependency error: 'openpyxl' is required for Excel files. Please install it."
        logger.error(f"TOOL_DEPS_ERROR | {filename}: {str(ie)}")
        return json.dumps({"status": "error", "message": error_msg})
    except Exception as e:
        logger.error(f"TOOL_ERROR | {filename}: {str(e)}")
        return json.dumps({"status": "error", "message": f"Technical error reading {filename}: {str(e)}. Ensure the file is not corrupted and uses standard CSV/Excel formatting."})
