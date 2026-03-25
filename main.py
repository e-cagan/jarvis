# main.py
# Jarvis'in giriş noktası.
# İki mod: text (terminal) ve voice (sesli).
# Çalıştırma:
#   python3 main.py          → mod seçim ekranı
#   python3 main.py --text   → doğrudan text mod
#   python3 main.py --voice  → doğrudan voice mod

import sys

from rich.console import Console
from rich.panel import Panel

# Tool'ları import et — import sırasında @registry.register çalışır
from tools.system.terminal import run_terminal
from tools.system.file_ops import read_file, write_file, list_directory, delete_file, move_file, copy_file, append_to_file
from tools.system.app_launcher import open_app, close_app, list_running_apps
from tools.system.sysinfo import system_info
from tools.system.notes import add_note, list_notes, delete_note, edit_note, search_notes
from tools.system.memory import remember, recall_memory, forget
from tools.system.media import media_control
from tools.web.search import web_search, web_fetch

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
    """Text tabanlı REPL döngüsü."""
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

            response = orchestrator.process(user_input)
            console.print(f"\n[bold cyan]Jarvis →[/bold cyan] {response}")

        except KeyboardInterrupt:
            console.print("\n[dim]Görüşürüz![/dim]")
            break
        except Exception as e:
            logger.error("Beklenmeyen hata: %s", e)
            console.print(f"[bold red]Hata:[/bold red] {e}")


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