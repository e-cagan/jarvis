# llm/prompt_manager.py
# LLM'e gönderilecek system prompt'u oluşturur.
# Config'den asistan ayarlarını, registry'den tool tanımlarını çeker.
# İki mod destekler:
#   1. Native tool calling (tool tanımları ayrı parametre olarak gider)
#   2. Fallback (tool tanımları system prompt'un içine metin olarak gömülür)

import json
import os
import yaml

from utils.logger import setup_logger

logger = setup_logger("prompt_manager")


def _load_assistant_config():
    """Config'den assistant bölümünü okur."""
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config.yaml"
    )

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    return config.get("assistant", {})


class PromptManager:
    """
    System prompt oluşturma ve yönetme.

    İki sorumluluğu var:
    1. Modelin kimliğini ve davranış kurallarını tanımlayan system prompt
    2. Tool tanımlarını LLM'in anlayacağı formata dönüştürme
    """

    def __init__(self, tool_registry):
        """
        Parametreler:
            tool_registry (ToolRegistry): Kayıtlı tool'ların listesini almak için.
                Dependency injection — PromptManager registry'yi dışarıdan alıyor,
                kendi oluşturmuyor. Bu test edilebilirliği artırır.
        """
        self.config = _load_assistant_config()
        self.registry = tool_registry

        self.name = self.config.get("name", "Jarvis")
        self.language = self.config.get("language", "tr")

        logger.info("PromptManager başlatıldı → %s (%s)", self.name, self.language)

    def build_system_prompt(self):
        """
        Modelin kimliğini ve davranış kurallarını içeren system prompt'u oluşturur.
        Bu prompt her istekte messages listesinin ilk elemanı olarak gönderilir.

        Prompt tasarım kararları:
        - Kısa ve net kurallar: Uzun prompt = model kuralları atlar
        - Dil belirtmek: Küçük modeller dil değiştirme eğiliminde, explicit olmak lazım
        - Tool kullanım kuralları: Model gereksiz yere tool çağırmasın
        - Yanıt formatı: Kısa ve öz, terminal asistanı gibi

        Dönüş:
            dict: {"role": "system", "content": "..."} formatında mesaj
        """
        # Tool isimlerini ve açıklamalarını prompt'a ekle
        # Model hangi tool'ların mevcut olduğunu bilmeli
        tool_schemas = self.registry.get_all_schemas()
        tool_descriptions = ""
        for tool in tool_schemas:
            tool_descriptions += f"- {tool['name']}: {tool['description']}\n"

        prompt = f"""Sen {self.name}, kişisel bir yapay zeka asistanısın.

## Temel Kurallar
- Her zaman Türkçe yanıt ver.
- Kısa ve öz cevaplar ver — gereksiz açıklama yapma.
- Kullanıcının isteğini yerine getirmek için gerektiğinde tool'ları kullan.
- Tool kullanmana gerek yoksa doğrudan yanıt ver.

## Mevcut Tool'lar
{tool_descriptions}
## Tool Kullanım Kuralları
- Sadece gerektiğinde tool çağır. Basit selamlama veya sohbet için tool kullanma.
- Tool çağırdıktan sonra sonucu kullanıcıya kısa ve anlaşılır şekilde özetle.
- Bir tool hata döndürürse, kullanıcıya durumu açıkla ve mümkünse alternatif öner.
- Birden fazla adım gerektiren görevlerde tool'ları sırayla çağır. Kullanıcıya "şu komutu çalıştırın" gibi talimatlar VERME — tool'ları kendin kullan.
"""

        logger.debug("System prompt oluşturuldu → %d karakter", len(prompt))

        return {"role": "system", "content": prompt.strip()}

    def get_tool_schemas(self):
        """
        Ollama'nın native tool calling formatına uygun tool listesini döndürür.
        Bu liste Ollama API'sine 'tools' parametresi olarak gönderilecek.

        Dönüş:
            list[dict]: Registry'deki tüm tool schema'ları
        """
        return self.registry.get_all_schemas()

    def build_fallback_prompt(self):
        """
        Native tool calling başarısız olursa kullanılacak alternatif system prompt.
        Tool tanımları JSON olarak prompt'un içine gömülür.
        Model, tool çağırmak istediğinde belirli bir JSON formatında yanıt vermesi istenir.

        Bu yaklaşım daha az güvenilir ama her modelde çalışır.

        Dönüş:
            dict: {"role": "system", "content": "..."} formatında mesaj
        """
        tool_schemas = self.registry.get_all_schemas()
        tools_json = json.dumps(tool_schemas, ensure_ascii=False, indent=2)

        prompt = f"""Sen {self.name}, kişisel bir yapay zeka asistanısın.
Her zaman Türkçe yanıt ver. Kısa ve öz cevaplar ver.

## Kullanılabilir Tool'lar
{tools_json}

## Yanıt Formatı
Bir tool çağırmak istediğinde SADECE şu JSON formatında yanıt ver, başka hiçbir şey ekleme:
{{"tool_call": {{"name": "tool_adı", "arguments": {{"param": "değer"}}}}}}

Tool çağırmana gerek yoksa normal metin olarak yanıt ver.
"""

        logger.debug("Fallback prompt oluşturuldu → %d karakter", len(prompt))

        return {"role": "system", "content": prompt.strip()}