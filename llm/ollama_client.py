# llm/ollama_client.py
# Ollama HTTP API ile iletişim kuran LLM client.
# LLMBase interface'ini implement eder.
# Projenin geri kalanı Ollama'nın varlığından habersiz —
# sadece LLMBase'deki generate() ve generate_with_tools() metodlarını çağırır.

import requests
import yaml
import os

from llm.base import LLMBase
from utils.logger import setup_logger

logger = setup_logger("ollama_client")


def _load_llm_config():
    """
    config.private.yaml'dan LLM ayarlarını okur.
    Neden burada ayrı okuyoruz? Çünkü bu modül sadece kendi config'ini bilmeli,
    tüm config'i taşımak gereksiz coupling yaratır.
    """
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config.private.yaml"
    )

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    return config.get("llm", {})


class OllamaClient(LLMBase):
    """
    Ollama HTTP API üzerinden LLM ile iletişim kurar.

    Ollama localhost:11434 portunda bir REST API sunuyor.
    Bu class o API'ye POST request atıp yanıt alıyor.
    """

    def __init__(self):
        config = _load_llm_config()

        # Config'den değerleri al, yoksa default kullan
        self.base_url = config.get("base_url", "http://localhost:11434")
        self.model = config.get("model", "qwen2.5:7b")
        self.temperature = config.get("temperature", 0.1)
        self.max_tokens = config.get("max_tokens", 2048)

        logger.info("OllamaClient başlatıldı → model: %s, url: %s", self.model, self.base_url)

    def generate(self, messages):
        """
        Mesaj geçmişi alıp düz metin yanıt döndürür.
        Tool calling yok — sadece sohbet.

        /api/chat endpoint'ine POST request atıyor.
        stream: false ile tüm yanıtı tek seferde alıyoruz.
        """
        # Ollama'nın beklediği request body
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,                # Tüm yanıtı tek seferde al
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens   # Ollama'da max_tokens yerine num_predict
            }
        }

        logger.debug("Ollama'ya istek atılıyor (generate) → %d mesaj", len(messages))

        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=120       # LLM yanıt süresi uzun olabilir
            )
            response.raise_for_status()    # HTTP hata kodu gelirse exception fırlat

        except requests.ConnectionError:
            logger.error("Ollama'ya bağlanılamadı. 'ollama serve' çalışıyor mu?")
            raise ConnectionError("Ollama sunucusuna bağlanılamadı. 'ollama serve' komutunu çalıştırın.")

        except requests.Timeout:
            logger.error("Ollama yanıt zaman aşımı (120s)")
            raise TimeoutError("Ollama yanıt vermedi — model çok büyük olabilir.")

        data = response.json()
        content = data.get("message", {}).get("content", "")

        logger.debug("Ollama yanıtı alındı → %d karakter", len(content))

        return content

    def generate_with_tools(self, messages, tools):
        """
        Tool tanımlarıyla birlikte istek atar.
        Model ya düz metin döner ya da bir tool çağrısı döner.

        Ollama tool formatı OpenAI standardını takip ediyor:
        tools: [{"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}]

        Dönüş standardımız (LLMBase contract'ı):
            Düz yanıt   → {"type": "text", "content": "..."}
            Tool çağrısı → {"type": "tool_call", "name": "...", "arguments": {...}}
        """
        # Ollama'nın beklediği tool formatına çevir
        # Registry'den gelen basit format → Ollama'nın OpenAI-uyumlu formatı
        ollama_tools = []
        for tool in tools:
            ollama_tools.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["parameters"]
                }
            })

        payload = {
            "model": self.model,
            "messages": messages,
            "tools": ollama_tools,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens
            }
        }

        logger.debug(
            "Ollama'ya istek atılıyor (with_tools) → %d mesaj, %d tool",
            len(messages), len(tools)
        )

        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=120
            )
            response.raise_for_status()

        except requests.ConnectionError:
            logger.error("Ollama'ya bağlanılamadı. 'ollama serve' çalışıyor mu?")
            raise ConnectionError("Ollama sunucusuna bağlanılamadı. 'ollama serve' komutunu çalıştırın.")

        except requests.Timeout:
            logger.error("Ollama yanıt zaman aşımı (120s)")
            raise TimeoutError("Ollama yanıt vermedi — model çok büyük olabilir.")

        data = response.json()
        message = data.get("message", {})

        # Tool call var mı kontrol et
        tool_calls = message.get("tool_calls")

        if tool_calls and len(tool_calls) > 0:
            # Model bir tool çağırmak istiyor
            first_call = tool_calls[0]    # Şimdilik sadece ilk tool call'u işliyoruz
            func_data = first_call.get("function", {})

            result = {
                "type": "tool_call",
                "name": func_data.get("name", ""),
                "arguments": func_data.get("arguments", {})
            }
            logger.info("Tool call algılandı → %s(%s)", result["name"], result["arguments"])
            return result

        else:
            # Düz metin yanıt
            content = message.get("content", "")
            logger.debug("Düz metin yanıt → %d karakter", len(content))
            return {"type": "text", "content": content}
    
    def generate_stream_with_tools(self, messages, tools):
        """
        Streaming + tool calling destekli yanıt.
        Tool call → dict döner. Text → generator döner.
        """
        ollama_tools = []
        for tool in tools:
            ollama_tools.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["parameters"]
                }
            })

        payload = {
            "model": self.model,
            "messages": messages,
            "tools": ollama_tools,
            "stream": True,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens
            }
        }

        logger.debug("Ollama streaming istek → %d mesaj, %d tool", len(messages), len(tools))

        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                stream=True,
                timeout=120
            )
            response.raise_for_status()
        except requests.ConnectionError:
            raise ConnectionError("Ollama sunucusuna bağlanılamadı.")
        except requests.Timeout:
            raise TimeoutError("Ollama yanıt vermedi.")

        import json as json_module

        # Tek bir iterator oluştur — tüm okumalar bundan yapılacak
        lines_iter = response.iter_lines()

        # İlk chunk'ı oku — tool call mı text mi?
        first_chunk = None
        for line in lines_iter:
            if line:
                first_chunk = json_module.loads(line)
                break

        if first_chunk is None:
            response.close()
            return {"type": "text", "content": ""}

        message = first_chunk.get("message", {})
        tool_calls = message.get("tool_calls")

        if tool_calls and len(tool_calls) > 0:
            func_data = tool_calls[0].get("function", {})
            result = {
                "type": "tool_call",
                "name": func_data.get("name", ""),
                "arguments": func_data.get("arguments", {})
            }
            logger.info("Stream tool call → %s(%s)", result["name"], result["arguments"])
            response.close()
            return result

        # Text — aynı iterator'ı kullanarak generator döndür
        def token_generator():
            # İlk chunk'ın içeriği
            first_content = message.get("content", "")
            if first_content:
                yield first_content

            # Kalan chunk'lar — AYNI iterator
            for line in lines_iter:
                if line:
                    try:
                        chunk = json_module.loads(line)
                        if chunk.get("done"):
                            break
                        content = chunk.get("message", {}).get("content", "")
                        if content:
                            yield content
                    except json_module.JSONDecodeError:
                        continue

        return token_generator()