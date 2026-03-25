# main.py
# Jarvis'in giriş noktası.
# Terminal üzerinden text-based REPL döngüsü çalıştırır.
# Phase 2'de STT/TTS eklendiğinde ses döngüsü event_loop.py'ye taşınacak.

from rich.console import Console
from rich.panel import Panel

# Tool'ları import et — import sırasında @registry.register çalışır ve tool'lar kaydolur
# Yeni tool eklendiğinde buraya bir import satırı eklenmeli
from tools.system.terminal import run_terminal
from tools.system.file_ops import read_file, write_file, list_directory, delete_file, move_file, append_to_file, copy_file
from tools.system.app_launcher import open_app, close_app, list_running_apps
from tools.web.search import web_search

from core.orchestrator import Orchestrator
from utils.logger import setup_logger


logger = setup_logger("main")
console = Console()


def print_banner():
    """Başlangıç banner'ı — Jarvis'in açılış ekranı."""
    banner_text = (
        "[bold cyan]JARVIS[/bold cyan] — Kişisel AI Asistan\n"
        "[dim]Phase 1: Text-based Terminal Interface[/dim]\n"
        "[dim]Çıkmak için 'q' veya 'çık' yazın[/dim]"
    )
    console.print(Panel(banner_text, border_style="cyan"))


def main():
    """
    Ana döngü.

    Akış:
    1. Orchestrator'ı başlat (LLM client, prompt manager, registry hepsi init olur)
    2. Banner göster
    3. Sonsuz döngüde:
       - Kullanıcıdan input al
       - Özel komutları kontrol et (çık, sıfırla)
       - Orchestrator'a gönder
       - Yanıtı göster
    """
    # Orchestrator'ı başlat
    try:
        orchestrator = Orchestrator()
    except Exception as e:
        console.print(f"[bold red]Başlatma hatası:[/bold red] {e}")
        return

    print_banner()

    # REPL döngüsü
    while True:
        try:
            # Kullanıcıdan input al
            # rich'in input'u renk desteği sağlıyor
            user_input = console.input("\n[bold green]Sen →[/bold green] ").strip()

            # Boş girdi — atla
            if not user_input:
                continue

            # Çıkış komutları
            if user_input.lower() in ("q", "çık", "quit", "exit"):
                console.print("[dim]Görüşürüz![/dim]")
                break

            # Konuşma sıfırlama
            if user_input.lower() in ("sıfırla", "reset", "temizle"):
                orchestrator.reset()
                console.print("[dim]Konuşma geçmişi sıfırlandı.[/dim]")
                continue

            # Orchestrator'a gönder ve yanıtı al
            response = orchestrator.process(user_input)

            # Yanıtı göster
            console.print(f"\n[bold cyan]Jarvis →[/bold cyan] {response}")

        except KeyboardInterrupt:
            # Ctrl+C ile çıkış
            console.print("\n[dim]Görüşürüz![/dim]")
            break

        except Exception as e:
            # Beklenmeyen hata — döngüyü kırma, logla ve devam et
            logger.error("Beklenmeyen hata: %s", e)
            console.print(f"[bold red]Hata:[/bold red] {e}")


# Bu dosya doğrudan çalıştırıldığında main()'i başlat
# Başka bir dosyadan import edildiğinde çalışmaz
if __name__ == "__main__":
    main()