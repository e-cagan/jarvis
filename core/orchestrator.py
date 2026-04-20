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

        from tools.consolidated.memory_manager import memory
        self.memory = memory

        self.state = ConversationState(max_messages=16)

        system_prompt = self._build_system_prompt()
        self.state.initialize(system_prompt)

        # Scheduler başlat ve callback'i ayarla
        from core.scheduler import JarvisScheduler
        from tools.consolidated.scheduler_tool import set_scheduler
        self.scheduler = JarvisScheduler()
        self.scheduler.set_callback(self._execute_scheduled_task)
        set_scheduler(self.scheduler)

        logger.info("Orchestrator başlatıldı (memory + scheduler destekli)")

        # Plugin sistemi — plugins/ dizinindeki tool'ları otomatik yükle
        from core.plugin_loader import PluginLoader
        from tools.consolidated.plugin_tool import set_plugin_loader
        self.plugin_loader = PluginLoader()
        plugin_count = self.plugin_loader.discover_and_load()
        set_plugin_loader(self.plugin_loader)

        if plugin_count > 0:
            # Plugin'ler yeni tool ekleyebilir — system prompt'u yeniden oluştur
            system_prompt = self._build_system_prompt()
            self.state.messages[0] = system_prompt

        logger.info("Orchestrator başlatıldı (memory + scheduler + %d plugin)", plugin_count)

    def _execute_scheduled_task(self, command):
        """
        Scheduler'dan gelen komutu çalıştırır.
        Yeni bir context'te çalışır — mevcut konuşmayı kirletmez.
        """
        logger.info("Zamanlı görev çalışıyor → '%s'", command)

        from rich.console import Console
        console = Console()
        console.print(f"\n[bold yellow]⏰ Zamanlı görev:[/bold yellow] {command}")

        # process() çağır — tool call dahil her şey çalışır
        result = self.process(command)
        console.print(f"[bold cyan]Jarvis →[/bold cyan] {result}\n")

        return result

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
    
    def process_stream(self, user_input):
        """
        Streaming versiyonu — text modda kullanılır.
        Tool call'larda streaming yok (tool sonucu beklenir).
        Son metin yanıtında token token yield eder.

        Dönüş:
            generator: Her iterasyonda bir token string'i
            veya tool call varsa tool'u çalıştırıp sonra streaming yapar
        """
        self.state.add_message({"role": "user", "content": user_input})
        logger.info("Kullanıcı → %s", user_input)

        tool_schemas = self.prompt_manager.get_tool_schemas()

        for round_num in range(self.max_tool_rounds):
            logger.debug("LLM round %d/%d (stream)", round_num + 1, self.max_tool_rounds)

            try:
                messages = self.state.get_messages()

                if not tool_schemas:
                    # Tool yok — düz streaming
                    result = self.llm.generate_stream_with_tools(messages, [])
                    if isinstance(result, dict):
                        text = result.get("content", "")
                        self.state.add_message({"role": "assistant", "content": text})
                        yield text
                        return
                    else:
                        full_text = ""
                        for token in result:
                            full_text += token
                            yield token
                        self.state.add_message({"role": "assistant", "content": full_text})
                        return

                result = self.llm.generate_stream_with_tools(messages, tool_schemas)

            except (ConnectionError, TimeoutError) as e:
                logger.error("LLM iletişim hatası: %s", e)
                yield f"Hata: LLM'e bağlanılamadı — {e}"
                return

            if isinstance(result, dict):
                # Tool call — execute et, loop devam etsin
                parsed = result
                if parsed.get("type") == "tool_call":
                    tool_name = parsed["name"]
                    tool_args = parsed["arguments"]

                    logger.info("Tool çağrısı → %s(%s)", tool_name, tool_args)
                    tool_result = self.tool_registry.execute(tool_name, tool_args)

                    self.state.add_message({
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [{"function": {"name": tool_name, "arguments": tool_args}}]
                    })
                    self.state.add_message({"role": "tool", "content": tool_result})
                    continue
                else:
                    text = parsed.get("content", "")
                    self.state.add_message({"role": "assistant", "content": text})
                    yield text
                    return
            else:
                # Generator — token token stream et
                full_text = ""
                for token in result:
                    full_text += token
                    yield token
                self.state.add_message({"role": "assistant", "content": full_text})
                logger.info("Jarvis (stream) → %s", full_text[:200])
                return

        yield "Üzgünüm, çok fazla adım gerekti."

    def reset(self):
        """Konuşma geçmişini sıfırlar. Uzun süreli hafıza korunur."""
        system_prompt = self._build_system_prompt()
        self.state.messages = [system_prompt]
        self.state._save()
        logger.info("Konuşma geçmişi sıfırlandı (hafıza korundu)")