# core/orchestrator.py
# Pipeline'ın merkezi koordinatörü — artık memory destekli.

from llm.ollama_client import OllamaClient
from llm.prompt_manager import PromptManager
from llm.response_parser import parse_response
from tools.registry import registry
from core.state import ConversationState
from utils.logger import setup_logger

logger = setup_logger("orchestrator")


class Orchestrator:

    def __init__(self):
        self.llm = OllamaClient()
        self.prompt_manager = PromptManager(tool_registry=registry)
        self.tool_registry = registry
        self.max_tool_rounds = 5

        # Memory sistemi — memory tool'undan global instance'ı al
        # Bu import burada çünkü circular import'u önlemek için
        from tools.consolidated.memory_manager import memory
        self.memory = memory

        # Conversation state — session persistence
        self.state = ConversationState(max_messages=40)

        # System prompt'u memory bilgileriyle oluştur ve state'i başlat
        system_prompt = self._build_system_prompt()
        self.state.initialize(system_prompt)

        logger.info("Orchestrator başlatıldı (memory destekli)")

    def _build_system_prompt(self):
        """Memory bilgilerini system prompt'a enjekte eder."""
        base_prompt = self.prompt_manager.build_system_prompt()

        # Memory context'i prompt'a ekle
        memory_context = self.memory.get_context_string()
        if memory_context:
            base_prompt["content"] += memory_context

        return base_prompt

    def process(self, user_input):
        logger.info("Kullanıcı → %s", user_input)

        # Kullanıcı mesajını state'e ekle
        self.state.add_message({"role": "user", "content": user_input})

        tool_schemas = self.prompt_manager.get_tool_schemas()

        for round_num in range(self.max_tool_rounds):
            logger.debug("LLM round %d/%d", round_num + 1, self.max_tool_rounds)

            try:
                messages = self.state.get_messages()

                if tool_schemas:
                    raw_response = self.llm.generate_with_tools(messages, tool_schemas)
                else:
                    text = self.llm.generate(messages)
                    raw_response = {"type": "text", "content": text}

            except (ConnectionError, TimeoutError) as e:
                logger.error("LLM iletişim hatası: %s", e)
                return f"Hata: LLM'e bağlanılamadı — {e}"

            parsed = parse_response(raw_response)

            if parsed["type"] == "text":
                assistant_text = parsed["content"]
                self.state.add_message({"role": "assistant", "content": assistant_text})
                logger.info("Jarvis → %s", assistant_text[:200])
                return assistant_text

            elif parsed["type"] == "tool_call":
                tool_name = parsed["name"]
                tool_args = parsed["arguments"]

                logger.info("Tool çağrısı → %s(%s)", tool_name, tool_args)
                tool_result = self.tool_registry.execute(tool_name, tool_args)

                self.state.add_message({
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "function": {
                            "name": tool_name,
                            "arguments": tool_args
                        }
                    }]
                })

                self.state.add_message({
                    "role": "tool",
                    "content": tool_result
                })

                logger.debug("Tool sonucu geçmişe eklendi, tekrar LLM'e gönderiliyor")

        logger.warning("Maksimum tool round'una ulaşıldı (%d)", self.max_tool_rounds)
        return "Üzgünüm, isteğinizi işlerken çok fazla adım gerekti."

    def reset(self):
        """Konuşma geçmişini sıfırlar. Uzun süreli hafıza korunur."""
        system_prompt = self._build_system_prompt()
        self.state.messages = [system_prompt]
        self.state._save()
        logger.info("Konuşma geçmişi sıfırlandı (hafıza korundu)")