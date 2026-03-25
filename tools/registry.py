# tools/registry.py
# Decorator-based tool kayıt sistemi.
# Yeni tool eklemek = bir fonksiyon yazıp @tool decorator'ı koymak.
# Registry tüm tool'ların listesini, açıklamalarını ve parametre şemalarını tutar.
# İki tüketici var: PromptManager (LLM'e tool tanımı gönderir) ve Orchestrator (tool'u çalıştırır).

from utils.logger import setup_logger

logger = setup_logger("registry")


class ToolRegistry:
    """
    Tool'ları saklayan ve yöneten merkezi kayıt sistemi.

    Her tool şu bilgileri içerir:
    - name: Tool'un benzersiz adı (LLM bu isimle çağırır)
    - description: Ne yaptığının açıklaması (LLM bunu okuyup karar verir)
    - parameters: JSON Schema formatında parametre tanımları
    - function: Çalıştırılacak Python fonksiyonu
    """

    def __init__(self):
        # Kayıtlı tool'ları tutan dict: {"tool_adı": {metadata + function}}
        self._tools = {}

    def register(self, name, description, parameters):
        """
        Decorator factory — tool fonksiyonunu registry'ye kaydeder.

        Kullanım:
            registry = ToolRegistry()

            @registry.register(
                name="run_terminal",
                description="Terminal komutu çalıştırır",
                parameters={
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "Çalıştırılacak shell komutu"
                        }
                    },
                    "required": ["command"]
                }
            )
            def run_terminal(command):
                ...

        Bu çağrı zinciri şöyle çalışır:
        1. register(name, desc, params) çağrılır → decorator fonksiyonunu döndürür
        2. decorator(func) çağrılır → func'ı registry'ye kaydeder
        3. Orijinal func değişmeden geri döner (wrap etmiyoruz)
        """

        def decorator(func):
            self._tools[name] = {
                "name": name,
                "description": description,
                "parameters": parameters,
                "function": func
            }
            logger.info("Tool kaydedildi → %s", name)
            return func    # Fonksiyonu olduğu gibi döndür, değiştirmiyoruz

        return decorator

    def get_tool(self, name):
        """
        İsme göre tool bilgisi döndürür.
        Orchestrator tool çalıştırırken bunu kullanacak.

        Dönüş:
            dict veya None: Tool bulunursa metadata + function, bulunamazsa None
        """
        return self._tools.get(name)

    def get_all_schemas(self):
        """
        Tüm tool'ların LLM'e gönderilecek schema listesini döndürür.
        PromptManager bunu çağırıp Ollama'ya tool tanımları olarak gönderecek.

        Dönüş:
            list[dict]: Her tool için {name, description, parameters}
                        function dahil DEĞİL — LLM'in fonksiyon referansına ihtiyacı yok.
        """
        schemas = []
        for tool_data in self._tools.values():
            schemas.append({
                "name": tool_data["name"],
                "description": tool_data["description"],
                "parameters": tool_data["parameters"]
            })
        return schemas

    def execute(self, name, arguments):
        """
        Bir tool'u adıyla çağırıp sonucunu döndürür.

        Parametreler:
            name (str): Çalıştırılacak tool adı
            arguments (dict): Tool'a geçilecek argümanlar (LLM'den gelen)

        Dönüş:
            str: Tool'un çalışma sonucu (her zaman string — LLM'e geri gidecek)

        Hata:
            Bilinmeyen tool → hata mesajı döner (exception fırlatmaz)
            Tool çalışırken hata → hata mesajı döner
        """
        tool = self._tools.get(name)

        if not tool:
            logger.error("Bilinmeyen tool: %s", name)
            return f"Hata: '{name}' adında bir tool bulunamadı."

        logger.info("Tool çalıştırılıyor → %s(%s)", name, arguments)

        try:
            # **arguments ile dict'i keyword arguments'a açıyoruz
            # {"command": "ls -la"} → func(command="ls -la")
            result = tool["function"](**arguments)
            logger.debug("Tool sonucu → %s", result[:200] if len(str(result)) > 200 else result)
            return str(result)

        except Exception as e:
            logger.error("Tool hatası [%s]: %s", name, e)
            return f"Hata: Tool çalışırken sorun oluştu — {e}"


# Modül seviyesinde tek bir global instance
# Tüm tool dosyaları bu instance'ı import edip @registry.register kullanacak
# Singleton pattern — projenin her yerinde aynı registry'ye erişiyoruz
registry = ToolRegistry()