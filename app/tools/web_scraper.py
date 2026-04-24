import os
import asyncio
import json
from pathlib import Path
from dotenv import load_dotenv
from tavily import TavilyClient
from langchain_core.tools import tool
import logging

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
env_path = ROOT_DIR / ".env"

if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

logger = logging.getLogger(__name__)

_tavily_client = None

def get_tavily_client():
    global _tavily_client
    if _tavily_client is None:
        api_key = os.getenv("TAVILY_API-KEY") or os.getenv("TAVILY_API_KEY")
        if not api_key:
            raise ValueError(f"TAVILY_API_KEY not found. Check .env at: {env_path}")
        _tavily_client = TavilyClient(api_key=api_key)
    return _tavily_client

KNOWLEDGE_BASE_APPS = [
    {"name": "App Documentation", "url": "https://netstore.rexel.be/NS/servlet/be.rex.ns.cf.RexHomeServlet?nprg=159"},
    {"name": "App Support", "url": "https://www.cebeo.be/fr-be"},
    {"name": "App Wiki", "url": "https://leshop.lightelec.eu/fr-be/catalogue.aspx"},
    {"name": "App KB", "url": "https://smartsd.com/fr"},
    {"name": "App Main", "url": "https://www.rassecurity.com/compte"},
]

@tool
async def scrape_knowledge_base(app_index: int = None, url: str = None) -> str:
    """
    Extracts structured content from a site or product page via Tavily.
    """
    if url is None:
        if app_index is None or not (0 <= app_index < len(KNOWLEDGE_BASE_APPS)):
            return "Error: Provide a valid app_index (0-4) or a direct URL."
        app = KNOWLEDGE_BASE_APPS[app_index]
        target_url = app["url"]
        source_name = app["name"]
    else:
        target_url = url
        source_name = "External Product Page"
    
    try:
        logger.info(f"Tavily extraction in progress: {target_url}")
        client = get_tavily_client()
        extraction = await asyncio.to_thread(client.extract, urls=[target_url])
        
        if not extraction or not extraction.get("results"):
            return f"Tavily could not extract content for {target_url}."

        result = extraction["results"][0]
        raw_text = result.get("raw_content", "")
        clean_text = " ".join(raw_text.split())
        content = clean_text[:12000]

        return f"Data from {source_name} (via Tavily):\nURL: {target_url}\n\n{content}"

    except Exception as e:
        logger.error(f"Tavily error for {target_url}: {e}")
        return f"Failed to retrieve data via Tavily. Error: {str(e)}"

@tool
async def tavily_search(query: str) -> str:
    """
    Search the web for missing information (price, specs, SKU) when the URL is unknown.
    """
    try:
        client = get_tavily_client()
        search_result = await asyncio.to_thread(
            client.search, 
            query=query, 
            search_depth="advanced", 
            max_results=5
        )
        
        results = search_result.get("results", [])
        if not results:
            return "No web results found for this query."
            
        formatted_results = ["Web Search Results:"]
        for res in results:
            formatted_results.append(f"- {res.get('title')} ({res.get('url')}): {res.get('content')}")
            
        return "\n".join(formatted_results)
    except Exception as e:
        logger.error(f"Tavily search error: {e}")
        return f"Search failed: {str(e)}"