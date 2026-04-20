# main.py
# Jarvis'in giriş noktası.
# İki mod: text (terminal) ve voice (sesli).
# Çalıştırma:
#   python3 main.py          → mod seçim ekranı
#   python3 main.py --text   → doğrudan text mod
#   python3 main.py --voice  → doğrudan voice mod

import sys
import logging

from rich.console import Console
from rich.panel import Panel

# Tool'ları import et — import sırasında @registry.register çalışır
from tools.system.terminal import run_terminal
from tools.system.sysinfo import system_info
from tools.system.media import media_control
from tools.consolidated.file_manager import file_manager
from tools.consolidated.notes_manager import notes
from tools.consolidated.app_control import app_control
from tools.consolidated.memory_manager import memory_tool
from tools.consolidated.web_tools import web
from tools.consolidated.email_tool import email_tool
from tools.consolidated.scheduler_tool import scheduler
from tools.consolidated.plugin_tool import plugins

from core.orchestrator import Orchestrator
from utils.logger import setup_logger

logger = setup_logger("main")
console = Console()


def print_banner():
    """Başlangıç banner'ı."""
    banner_text = (
        "[bold cyan]JARVIS[/bold cyan] — Kişisel AI Asistan\n"
        "[dim]Çıkmak için 'q' veya 'çık' yazın[/dim]"
    )
    console.print(Panel(banner_text, border_style="cyan"))


def run_text_mode():
    """Text tabanlı REPL döngüsü — streaming destekli."""
    try:
        orchestrator = Orchestrator()
    except Exception as e:
        console.print(f"[bold red]Başlatma hatası:[/bold red] {e}")
        return

    print_banner()

    while True:
        try:
            user_input = console.input("\n[bold green]Sen →[/bold green] ").strip()

            if not user_input:
                continue

            if user_input.lower() in ("q", "çık", "quit", "exit"):
                console.print("[dim]Görüşürüz![/dim]")
                break

            if user_input.lower() in ("sıfırla", "reset", "temizle"):
                orchestrator.reset()
                console.print("[dim]Konuşma geçmişi sıfırlandı.[/dim]")
                continue

            logging.getLogger().setLevel(logging.WARNING)  # Streaming sırasında logları sustur

            console.print("\n[bold cyan]Jarvis →[/bold cyan] ", end="")
            for token in orchestrator.process_stream(user_input):
                console.print(token, end="", highlight=False)
            console.print()

            logging.getLogger().setLevel(logging.DEBUG)  # Logları geri aç

        except KeyboardInterrupt:
            console.print("\n[dim]Görüşürüz![/dim]")
            break
        except Exception as e:
            logger.error("Beklenmeyen hata: %s", e)
            console.print(f"\n[bold red]Hata:[/bold red] {e}")


def run_voice_mode():
    """Ses tabanlı döngü."""
    from core.event_loop import VoiceEventLoop

    try:
        loop = VoiceEventLoop()
        loop.run()
    except Exception as e:
        console.print(f"[bold red]Başlatma hatası:[/bold red] {e}")
        logger.error("Voice mode başlatma hatası: %s", e)


def main():
    """Mod seçimi ve başlatma."""
    # Komut satırı argümanları
    if "--text" in sys.argv:
        run_text_mode()
        return
    if "--voice" in sys.argv:
        run_voice_mode()
        return

    # İnteraktif mod seçimi
    console.print(Panel(
        "[bold cyan]JARVIS[/bold cyan] — Mod Seçimi\n\n"
        "  [bold]1.[/bold] Text modu  (terminal üzerinden yazarak)\n"
        "  [bold]2.[/bold] Voice modu (mikrofon ile konuşarak)",
        border_style="cyan"
    ))

    choice = console.input("\n[bold]Seçimin (1/2):[/bold] ").strip()

    if choice == "2":
        run_voice_mode()
    else:
        run_text_mode()


if __name__ == "__main__":
    main()