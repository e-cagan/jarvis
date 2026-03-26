# tools/consolidated/web_tools.py
# Birleştirilmiş web tool'u.

import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS

from tools.registry import registry
from utils.logger import setup_logger

logger = setup_logger("web_tools")


@registry.register(
    name="web",
    description="Web işlemleri. Desteklenen action'lar: "
                "search (internette ara), fetch (bir sayfanın içeriğini çek).",
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Yapılacak işlem: search, fetch"
            },
            "query": {
                "type": "string",
                "description": "search için: arama sorgusu. fetch için: URL"
            },
            "max_results": {
                "type": "integer",
                "description": "search için: maks sonuç sayısı (varsayılan 5)"
            }
        },
        "required": ["action", "query"]
    }
)
def web(action, query, max_results=5):
    """Tek fonksiyondan tüm web operasyonları."""
    action = action.lower().strip()

    if action == "search":
        logger.info("Web araması → '%s'", query)
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
            if not results:
                return f"'{query}' için sonuç bulunamadı."
            formatted = []
            for i, r in enumerate(results, 1):
                formatted.append(f"{i}. {r.get('title', '')}\n   URL: {r.get('href', '')}\n   {r.get('body', '')}")
            return "\n\n".join(formatted)
        except Exception as e:
            return f"Arama hatası: {e}"

    elif action == "fetch":
        logger.info("Web fetch → %s", query)
        try:
            resp = requests.get(query, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
                tag.decompose()
            lines = [l.strip() for l in soup.get_text(separator="\n", strip=True).splitlines() if l.strip()]
            text = "\n".join(lines)
            if len(text) > 5000:
                text = text[:5000] + "\n... (kırpıldı)"
            return text
        except Exception as e:
            return f"Fetch hatası: {e}"

    else:
        return f"Bilinmeyen action: {action}. Geçerli: search, fetch"