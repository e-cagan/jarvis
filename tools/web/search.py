# tools/web/search.py
# Web arama tool'u — DuckDuckGo üzerinden arama yapar.
# API key gerektirmez, ücretsiz, kişisel kullanım için yeterli.
# İleride Google API veya başka bir provider ile swap edilebilir.

import requests
from bs4 import BeautifulSoup
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


@registry.register(
    name="web_fetch",
    description="Bir web sayfasının içeriğini çeker ve metin olarak döndürür. "
                "Arama sonuçlarından detaylı bilgi almak veya belirli bir sayfayı okumak için kullanılır.",
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "İçeriği çekilecek web sayfasının URL'si"
            }
        },
        "required": ["url"]
    }
)
def web_fetch(url):
    """
    Web sayfasının içeriğini çeker, HTML'i temizleyip düz metin döndürür.

    BeautifulSoup ile HTML parse edilir, script/style tagları temizlenir,
    sadece okunabilir metin içerik kalır.

    Çıktı 5000 karakterle sınırlı — LLM context window'unu korumak için.
    """
    logger.info("Web fetch → %s", url)

    try:
        response = requests.get(
            url,
            timeout=15,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
        )
        response.raise_for_status()

        # HTML → temiz metin
        soup = BeautifulSoup(response.text, "html.parser")

        # Gereksiz elementleri kaldır
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
            tag.decompose()

        # Metin çıkar
        text = soup.get_text(separator="\n", strip=True)

        # Birden fazla boş satırı teke düşür
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        clean_text = "\n".join(lines)

        # Uzunluk limiti
        if len(clean_text) > 5000:
            clean_text = clean_text[:5000] + "\n\n... (içerik kırpıldı)"

        logger.info("Web fetch tamamlandı → %d karakter", len(clean_text))
        return clean_text

    except requests.Timeout:
        return "Hata: Sayfa yüklenemedi — zaman aşımı."
    except requests.RequestException as e:
        logger.error("Web fetch hatası: %s", e)
        return f"Hata: Sayfa yüklenemedi — {e}"