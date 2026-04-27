import sys
import os
from pathlib import Path
import json
import asyncio

# Add the project root to the Python path so we can import app modules
project_root = str(Path(__file__).parent.parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

from app.tools.csv_tool import manage_csv_data, list_session_files
from app.tools.pdf_tool import manage_pdf_data
from app.core.config import get_settings

async def run_analysis(session_id: str):
    settings = get_settings()
    print(f"\n{'='*60}")
    print(f"ANALYZING DATA PROCESSING FOR SESSION: {session_id}")
    print(f"Upload Directory: {settings.upload_dir}")
    print(f"{'='*60}\n")

    # 1. Check for files
    files = list_session_files(session_id)
    if not files:
        print(f" [!] No files found for session '{session_id}'.")
        print(f"     Make sure files exist in: {Path(settings.upload_dir) / session_id}")
        return

    print(f" [+] Found {len(files)} file(s): {', '.join(files)}")

    # 2. Analyze CSV processing (Scraping/Chunking logic)
    for filename in files:
        print(f"\n--- Processing: {filename} ---")
        
        if filename.lower().endswith('.csv'):
            # This calls the logic used by your LangGraph agents
            output = manage_csv_data(session_id, filename)
            
            print(f"\n[1. RAW AGENT CONTEXT (What the LLM sees)]:")
            print("-" * 60)
            print(output)
            print("-" * 60)

            # 3. French Validation Logic
            print("\n[2. FRENCH DATA VALIDATION]:")
            if "Error" not in output:
                try:
                    # Parse the JSON string directly
                    data = json.loads(output)
                    print(f" [+] Column Count: {len(data['columns'])} (If this is 1, the separator ';' was likely missed)")
                    print(f" [+] Accented Character Check: ", end="")
                    accented_cols = [c for c in data['columns'] if any(ord(char) > 127 for char in c)]
                    print(f"Found {len(accented_cols)} accented column(s): {accented_cols}" if accented_cols else "No accented characters found.")
                except:
                    print(" [!] Could not parse summary for detailed validation.")

        elif filename.lower().endswith('.pdf'):
            output = await manage_pdf_data(session_id, filename)
            print(f"\n[1. RAW AGENT CONTEXT (What the LLM sees)]:")
            print("-" * 60)
            print(output)
            print("-" * 60)
            
            print("\n[2. FRENCH PDF VALIDATION]:")
            if "Error" not in output:
                try:
                    data = json.loads(output)
                    # Basic check for processing results
                    # Basic check for French language markers
                    fr_markers = [' le ', ' la ', ' les ', ' est ', ' dans ', ' pour ']
                    print(f" [+] Extraction Method: {data.get('extraction_method')}")
                    print(f" [+] Chunk Count: {data.get('chunk_count')}")
                except:
                    print(" [!] Could not parse PDF summary for validation.")
        else:
            print(f" [i] Skipping {filename}: Analysis logic for this file type is not yet implemented in csv_tool.py")

if __name__ == "__main__":
    # Replace 'test_session' with an actual folder name in your uploads directory
    target_session = "222" 
    if len(sys.argv) > 1:
        target_session = sys.argv[1]
        
    asyncio.run(run_analysis(target_session))
