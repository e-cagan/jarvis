# llm/base.py
# LLM modülünün abstract interface tanımı.
# Tüm LLM client'ları (Ollama, API tabanlı vs.) bu class'ı inherit eder.
# Orchestrator bu interface'e bağımlıdır, somut implementasyona değil.

from abc import ABC, abstractmethod


class LLMBase(ABC):
    """
    Tüm LLM client'larının uyması gereken sözleşme (contract).

    Alt sınıflar şu metodları MUTLAKA implement etmeli:
    - generate(): Düz metin yanıt üretir
    - generate_with_tools(): Tool tanımlarıyla birlikte yanıt üretir
    """

    @abstractmethod
    def generate(self, messages):
        """
        Mesaj geçmişi alıp düz metin yanıt döndürür.

        Parametreler:
            messages (list[dict]): Konuşma geçmişi.
                Her dict {"role": "user"|"assistant"|"system", "content": "..."} formatında.

        Dönüş:
            str: Modelin ürettiği metin yanıt.
        """
        pass

    @abstractmethod
    def generate_with_tools(self, messages, tools):
        """
        Mesaj geçmişi ve tool tanımlarıyla yanıt üretir.
        Model ya düz metin döner ya da bir tool çağrısı döner.

        Parametreler:
            messages (list[dict]): Konuşma geçmişi.
            tools (list[dict]): Kullanılabilir tool tanımları.
                Her tool {"name": str, "description": str, "parameters": dict} formatında.

        Dönüş:
            dict: İki olası format:
                Düz yanıt   → {"type": "text", "content": "..."}
                Tool çağrısı → {"type": "tool_call", "name": "...", "arguments": {...}}
        """
        pass