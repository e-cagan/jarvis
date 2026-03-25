# tools/web/search.py
# Web arama tool'u — DuckDuckGo üzerinden arama yapar.
# API key gerektirmez, ücretsiz, kişisel kullanım için yeterli.
# İleride Google API veya başka bir provider ile swap edilebilir.

from duckduckgo_search import DDGS

from tools.registry import registry
from utils.logger import setup_logger

logger = setup_logger("web_search")


@registry.register(
    name="web_search",
    description="İnternette arama yapar ve sonuçları döndürür. "
                "Güncel bilgi, haberler, teknik sorular, hava durumu gibi konular için kullanılır.",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Aranacak sorgu (örn: 'Python 3.12 yenilikleri', 'İstanbul hava durumu')"
            },
            "max_results": {
                "type": "integer",
                "description": "Döndürülecek maksimum sonuç sayısı (varsayılan: 5)"
            }
        },
        "required": ["query"]
    }
)
def web_search(query, max_results=5):
    """
    DuckDuckGo üzerinden web araması yapar.

    DDGS().text() metodu arama sonuçlarını dict listesi olarak döndürür.
    Her sonuçta title, href (URL), ve body (snippet) alanları var.
    Sonuçları LLM'in okuyabileceği düz metin formatına çeviriyoruz.

    Parametreler:
        query (str): Arama sorgusu
        max_results (int): Maksimum sonuç sayısı (default 5)

    Dönüş:
        str: Formatlanmış arama sonuçları
    """
    logger.info("Web araması → '%s' (max: %d)", query, max_results)

    try:
        # DDGS context manager olarak kullanılıyor — bağlantıyı düzgün kapatır
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))

        if not results:
            return f"'{query}' için sonuç bulunamadı."

        # Sonuçları LLM'in anlayacağı formata çevir
        formatted = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "Başlık yok")
            url = r.get("href", "")
            snippet = r.get("body", "Açıklama yok")
            formatted.append(f"{i}. {title}\n   URL: {url}\n   {snippet}")

        output = f"'{query}' için arama sonuçları:\n\n" + "\n\n".join(formatted)

        logger.info("Arama tamamlandı → %d sonuç", len(results))
        return output

    except Exception as e:
        logger.error("Web arama hatası: %s", e)
        return f"Arama hatası: {e}"