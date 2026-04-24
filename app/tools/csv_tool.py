import os
import json
import csv
import re
import pandas as pd
from pathlib import Path
import logging
from typing import List, Dict, Any, Optional, Tuple
from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

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
        return float(s)
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
    
    try:
        # Robust encoding and separator detection
        # Try common encodings for French/European CSVs: UTF-8 with BOM, UTF-8, and Windows-1252
        encoding = None
        sep = ','
        
        for enc in ['utf-8-sig', 'utf-8', 'cp1252', 'latin-1']:
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    sample = f.read(8192)
                    if not sample:
                        continue
                    dialect = csv.Sniffer().sniff(sample)
                    sep = dialect.delimiter
                    encoding = enc
                    break
            except Exception:
                continue
        
        if not encoding:
            encoding = 'utf-8' # Final fallback
            sep = ';' if ';' in open(file_path, 'r', encoding='utf-8', errors='replace').read(1024) else ','

        # Header detection: identify metadata rows to preserve design
        header_idx = find_header_row(file_path, encoding, sep)
        
        # Load CSV starting from the detected header row
        df = pd.read_csv(file_path, encoding=encoding, sep=sep, engine='python', dtype=str, header=header_idx)

        if action == "update" and updates:
            # Apply updates provided by the LLM
            # Find the primary article column to validate rows
            # Robust detection of the article/code column
            article_col = next((c for c in df.columns if any(k in str(c).lower() for k in ["article", "code", "réf", "n°"])), None)
            
            logger.info(f"CSV_UPDATE_EXECUTION | File: {filename} | Updates: {len(updates)}")
            for upd in updates:
                try:
                    row_idx = int(upd.get("row"))
                except (ValueError, TypeError):
                    continue

                col_name = upd.get("column")
                raw_val = upd.get("value")
                
                norm_val = normalize_number(raw_val)
                val = str(norm_val) if norm_val is not None else (str(raw_val) if raw_val is not None else "")
                
                # CRITICAL: Verify column exists in original headers to prevent adding new columns
                if col_name not in df.columns:
                    logger.warning(f"SKIP_NEW_COL | {col_name} is not in original CSV. Skipping.")
                    continue

                if row_idx < len(df):
                    # Prevent updating metadata columns
                    if "unnamed" in str(col_name).lower():
                        continue

                    # Ignore placeholders like 'noos', 'none', or 'nan'
                    if not raw_val or str(raw_val).lower() in ["noos", "none", "nan", "null"]:
                        continue

                    # Safety: Skip metadata rows or chapter titles
                    if article_col:
                        row_val = str(df.at[row_idx, article_col]).strip()
                        # Identify terminal articles (e.g., 72.22.1b.01) vs Titles (72.22)
                        digits = re.findall(r'\d+', row_val)
                        is_terminal = len(digits) >= 3
                        if not row_val or row_val.lower() == "nan" or not is_terminal or any(k in row_val.lower() for k in ["chantier", "client", "projet"]):
                            logger.debug(f"CSV_UPDATE_SKIP | Row {row_idx} ('{row_val}') is not a terminal article.")
                            continue

                    # Fill the original missing field
                    df.at[row_idx, col_name] = val
                    logger.info(f"FILLED_FIELD: {col_name} at Row {row_idx} with {val}")
            
            # Save logic: write to 'updated_' prefix but maintain cumulative state
            new_filename = filename if filename.startswith("updated_") else f"updated_{filename}"
            new_file_path = file_path.parent / new_filename
            
            # Preserve Metadata: Write original rows preceding the header first
            with open(new_file_path, 'w', encoding=encoding, newline='') as f:
                with open(file_path, 'r', encoding=encoding, errors='replace') as old_f:
                    for _ in range(header_idx):
                        f.write(old_f.readline())
                # Append the updated dataframe
                df.to_csv(f, index=False, encoding=encoding, sep=sep, quoting=csv.QUOTE_MINIMAL, na_rep="")
                
            return json.dumps({"status": "success", "message": f"Updated {len(updates)} fields in {filename}"})

        # Global Missing Field Detection
        # Identifies terminal articles (3+ segments) with empty technical columns
        missing_audit = []
        article_col = next((c for c in df.columns if any(k in str(c).lower() for k in ["article", "code", "réf", "n°"])), None)
        tech_cols = [c for c in df.columns if any(k in str(c).lower() for k in ["qt", "p.u", "somme", "prix", "unit"]) 
                     and "unnamed" not in str(c).lower()]
        
        if article_col:
            for idx, row in df.iterrows():
                art_val = str(row[article_col]).strip()
                # Check if it looks like a terminal article (e.g., 72.22.01)
                digits = re.findall(r'\d+', art_val)
                if len(digits) >= 3 and "chantier" not in art_val.lower():
                    missing_in_row = [c for c in tech_cols if not str(row[c]).strip() or str(row[c]).lower() == "nan"]
                    if missing_in_row:
                        missing_audit.append({"row": idx, "article": art_val, "missing_columns": missing_in_row})

        valid_columns = [c for c in df.columns if "unnamed" not in str(c).lower()]
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
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})
