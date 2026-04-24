import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any
from tavily import TavilyClient
from app.core.config import get_settings

def scrape_predefined_sources(query: str, urls: List[str], session: requests.Session = None) -> str:
    """
    Scrapes specific URLs to find missing CSV information.
    """
    aggregated_context = ""
    
    for url in urls:
        try:
            response = (session or requests).get(url, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                # Remove script and style elements
                for script in soup(["script", "style"]):
                    script.decompose()
                
                text = soup.get_text(separator=' ')
                # Basic cleaning
                lines = (line.strip() for line in text.splitlines())
                chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                clean_text = '\n'.join(chunk for chunk in chunks if chunk)
                
                # In a real scenario, we would use a vector search here 
                # instead of appending everything.
                if query.lower() in clean_text.lower():
                    aggregated_context += f"\nSource {url}:\n{clean_text[:2000]}..."
        except Exception as e:
            continue
            
    return aggregated_context if aggregated_context else "No relevant information found on web pages."

def tavily_search_for_info(query: str, max_results: int = 5) -> str:
    """
    Performs a web search using Tavily API to find information relevant to the query.
    This is ideal for general web searches to fill missing CSV data.
    """
    settings = get_settings()
    if not settings.tavily_api_key:
        return "Tavily API key not configured. Cannot perform web search."

    tavily = TavilyClient(api_key=settings.tavily_api_key)
    try:
        response = tavily.search(query=query, search_depth="advanced", max_results=max_results, include_answer=True)
        
        context = ""
        if response.get("answer"):
            context += f"Tavily Answer: {response['answer']}\n\n"
        context += "Relevant Snippets:\n"
        for result in response.get("results", []):
            context += f"- Source: {result['url']}\n  Content: {result['content']}\n\n"
        return context if context.strip() != "Relevant Snippets:" else "No relevant information found via Tavily search."
    except Exception as e:
        return f"Error during Tavily search: {str(e)}"

def login_and_scrape(
    login_url: str, 
    credentials: Dict[str, str], 
    target_urls: List[str], 
    query: str
) -> str:
    """
    Performs a login and then scrapes target URLs using the authenticated session.
    This is a conceptual example for simple form-based logins.
    """
    session = requests.Session()
    
    try:
        # Step 1: Perform the login
        # You might need to inspect the website's login form to get the correct
        # POST URL and parameter names (e.g., 'username', 'password', 'csrf_token').
        login_response = session.post(login_url, data=credentials, timeout=15)
        login_response.raise_for_status() # Raise an exception for HTTP errors

        # Professional check: Look for common success indicators or absence of 'error' keywords
        # For French sites, we check for both French and English success markers
        success_keywords = ["login successful", "connexion réussie", "tableau de bord", "mon compte"]
        is_success = any(k in login_response.text.lower() for k in success_keywords)
        
        if not is_success and login_response.status_code != 200:
            return f"Login failed for {login_url}. Status: {login_response.status_code}"

        # Step 2: Scrape the target URLs using the authenticated session
        print(f"Login successful to {login_url}. Proceeding to scrape target URLs.")
        return scrape_predefined_sources(query, target_urls, session=session)

    except requests.exceptions.RequestException as e:
        return f"Error during login or scraping: {e}"
    except Exception as e:
        return f"An unexpected error occurred: {e}"