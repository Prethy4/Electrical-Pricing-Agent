import logging
import json
from pathlib import Path
from typing import Dict, Any
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

async def extract_product(url: str, session_data_path: str = "session.json") -> Dict[str, Any]:
    """
    Extracts content from a URL using Playwright. 
    Falls back to raw HTML extraction if CSS selectors fail.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        
        # Session reuse for sites requiring login
        context_args = {}
        if Path(session_data_path).exists():
            context_args["storage_state"] = session_data_path
            
        context = await browser.new_context(**context_args)
        page = await context.new_page()
        
        try:
            logger.info(f"WEB_REQUEST | URL: {url}")
            await page.goto(url, wait_until="networkidle", timeout=30000)
            
            # Attempt to get primary content (Title/Price/Description)
            # This is a generic fallback; in a real scenario, this would be more targeted.
            content = await page.content()
            title = await page.title()
            
            logger.info(f"WEB_RESULT | Successfully retrieved content for: {title}")
            
            return {
                "value": content,
                "title": title,
                "confidence": 0.9,
                "source": "web"
            }
        except Exception as e:
            logger.error(f"WEB_RESULT | Extraction failed for {url}: {str(e)}")
            return {"value": None, "confidence": 0, "source": "web", "error": str(e)}
        finally:
            await browser.close()
