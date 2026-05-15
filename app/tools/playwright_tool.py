import logging
import asyncio
import os
from typing import Optional
from playwright.async_api import async_playwright
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

@tool
async def scrape_authenticated_website(url: str, query: str, username: Optional[str] = None, password: Optional[str] = None) -> str:
    """
    Uses Playwright to log into a website and extract price/technical data for a specific item.
    Handles dynamic content and authentication. If username/password are not provided, 
    it attempts to use credentials from environment variables.
    """
    try:
        # Fallback to environment variables if not provided by the agent
        if not username or not password:
            if "rexel" in url.lower():
                username = os.getenv("REXEL_USER")
                password = os.getenv("REXEL_PASS")
            elif "rassecurity" in url.lower():
                username = os.getenv("RAS_USER")
                password = os.getenv("RAS_PASS")
            else:
                username = os.getenv("TECHNICAL_SITE_USERNAME")
                password = os.getenv("TECHNICAL_SITE_PASSWORD")

        if not username or not password:
             logger.warning(f"No credentials found for {url}. Attempting guest access.")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(viewport={'width': 1280, 'height': 720})
            page = await context.new_page()
            
            logger.info(f"Navigating to {url} for query: {query}")
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)

            # Generic login logic - can be refined per site if selectors are known
            # Attempt to find login fields
            if username and password:
                try:
                    await asyncio.sleep(2)
                    user_selectors = ['input[type="email"]', 'input[name*="user"]', 'input[id*="login"]', 'input[name="login"]', 'input[name*="username"]']
                    user_field = await page.locator(", ".join(user_selectors)).first
                    await user_field.wait_for(state="visible", timeout=5000)
                    await user_field.fill(username)
                    
                    pw_field = await page.locator('input[type="password"]').first
                    await pw_field.fill(password)
                    
                    await page.keyboard.press("Enter")
                    await page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    logger.warning("Could not find standard login fields, proceeding as guest or assuming already logged in.")

            # Step 2: Search for the product if a search box is visible
            try:
                search_selectors = ['input[type="search"]', 'input[name="q"]', 'input[name*="search"]', 'input[placeholder*="search"]', 'input[placeholder*="recherche"]']
                search_box = await page.locator(", ".join(search_selectors)).first
                if await search_box.is_visible():
                    await search_box.fill(query)
                    await page.keyboard.press("Enter")
                    await page.wait_for_load_state("networkidle", timeout=15000)
                    await asyncio.sleep(2) # Wait for results to render
            except Exception as e:
                logger.info(f"Search box not found or failed: {str(e)}. Scraping current page.")
            
            # Extract text
            text_content = await page.evaluate("() => document.body.innerText")
            
            # Basic filtering to reduce noise
            lines = text_content.split('\n')
            relevant_lines = []
            for i, line in enumerate(lines):
                if query.lower() in line.lower() or "€" in line or "price" in line.lower():
                    relevant_lines.append(line.strip())
            
            await browser.close()
            
            if not relevant_lines:
                return f"No direct matches found for '{query}' on {url}. Raw extract: {text_content[:1000]}"
                
            return f"Data found on {url}:\n" + "\n".join(relevant_lines[:20])
    except Exception as e:
        logger.error(f"Playwright error: {str(e)}")
        return f"Failed to scrape {url} via Playwright: {str(e)}"
