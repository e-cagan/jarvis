# core/orchestrator.py
# Pipeline'ın merkezi koordinatörü.
# Kullanıcı mesajını alır → LLM'e gönderir → tool call varsa çalıştırır → yanıtı döndürür.
# Tüm modülleri (LLM client, prompt manager, tool registry, response parser) birleştirir.
# Hiçbir modülün iç detayını bilmez — sadece interface'lerini kullanır.

from llm.ollama_client import OllamaClient
from llm.prompt_manager import PromptManager
from llm.response_parser import parse_response
from tools.registry import registry
from utils.logger import setup_logger

logger = setup_logger("orchestrator")


class Orchestrator:
    """
    Jarvis pipeline'ının beyni.

    Sorumlulukları:
    - Conversation state (mesaj geçmişi) yönetimi
    - LLM ile iletişim koordinasyonu
    - Tool call → execute → summarize döngüsü
    - Hata durumlarında graceful fallback
    """

    def __init__(self):
        # Modülleri başlat
        self.llm = OllamaClient()
        self.prompt_manager = PromptManager(tool_registry=registry)
        self.tool_registry = registry

        # Konuşma geçmişi — her turda LLM'e gönderilir
        # İlk eleman her zaman system prompt
        self.messages = [self.prompt_manager.build_system_prompt()]

        # Tool call döngüsü için üst limit (sonsuz döngü koruması)
        self.max_tool_rounds = 5

        logger.info("Orchestrator başlatıldı")

    def process(self, user_input):
        """
        Kullanıcıdan gelen mesajı işleyip yanıt döndürür.
        Bu, pipeline'ın ana giriş noktası — main.py sadece bunu çağırır.

        Akış:
        1. Kullanıcı mesajını geçmişe ekle
        2. LLM'e gönder (tool tanımlarıyla birlikte)
        3. Yanıtı parse et
        4. Tool call varsa → çalıştır → sonucu geçmişe ekle → LLM'e tekrar gönder
        5. Düz metin gelene kadar tekrarla (max_tool_rounds'a kadar)
        6. Son metin yanıtı döndür

        Parametreler:
            user_input (str): Kullanıcının yazdığı mesaj

        Dönüş:
            str: Jarvis'in yanıtı
        """
        # Kullanıcı mesajını geçmişe ekle
        self.messages.append({"role": "user", "content": user_input})
        logger.info("Kullanıcı → %s", user_input)

        # Tool tanımlarını al
        tool_schemas = self.prompt_manager.get_tool_schemas()

        # Tool call döngüsü
        for round_num in range(self.max_tool_rounds):
            logger.debug("LLM round %d/%d", round_num + 1, self.max_tool_rounds)

            # LLM'e gönder
            try:
                if tool_schemas:
                    raw_response = self.llm.generate_with_tools(self.messages, tool_schemas)
                else:
                    # Hiç tool kayıtlı değilse düz generate kullan
                    text = self.llm.generate(self.messages)
                    raw_response = {"type": "text", "content": text}

            except (ConnectionError, TimeoutError) as e:
                logger.error("LLM iletişim hatası: %s", e)
                return f"Hata: LLM'e bağlanılamadı — {e}"

            # Yanıtı parse et
            parsed = parse_response(raw_response)

            if parsed["type"] == "text":
                # Düz metin yanıt — döngüden çık, kullanıcıya döndür
                assistant_text = parsed["content"]
                self.messages.append({"role": "assistant", "content": assistant_text})
                logger.info("Jarvis → %s", assistant_text[:200])
                return assistant_text

            elif parsed["type"] == "tool_call":
                # Tool çağrısı — çalıştır ve sonucu geçmişe ekle
                tool_name = parsed["name"]
                tool_args = parsed["arguments"]

                logger.info("Tool çağrısı → %s(%s)", tool_name, tool_args)

                # Tool'u çalıştır
                tool_result = self.tool_registry.execute(tool_name, tool_args)

                # LLM'in tool çağrısını geçmişe ekle
                # Ollama'nın chat formatında assistant mesajında tool_calls olmalı
                self.messages.append({
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "function": {
                            "name": tool_name,
                            "arguments": tool_args
                        }
                    }]
                })

                # Tool sonucunu geçmişe ekle
                # role: "tool" — Ollama bu role ile tool sonuçlarını tanır
                self.messages.append({
                    "role": "tool",
                    "content": tool_result
                })

                logger.debug("Tool sonucu geçmişe eklendi, tekrar LLM'e gönderiliyor")
                # Döngü devam eder — LLM sonucu özetleyecek

        # max_tool_rounds'a ulaşıldı — güvenlik çıkışı
        logger.warning("Maksimum tool round'una ulaşıldı (%d)", self.max_tool_rounds)
        return "Üzgünüm, isteğinizi işlerken çok fazla adım gerekti. Lütfen daha spesifik bir istekte bulunun."

    def reset(self):
        """
        Konuşma geçmişini sıfırlar.
        System prompt korunur, sadece user/assistant mesajları temizlenir.
        Kullanıcı 'sıfırla' veya 'temizle' dediğinde çağrılabilir.
        """
        self.messages = [self.prompt_manager.build_system_prompt()]
        logger.info("Konuşma geçmişi sıfırlandı")