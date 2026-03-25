# core/event_loop.py
# Ses tabanlı etkileşim döngüsü.
# Wake word → Dinle → Transkribe → İşle → Seslendir → Tekrarla

from rich.console import Console

from core.orchestrator import Orchestrator
from stt.whisper_stt import WhisperSTT
from stt.wake_word import WakeWordDetector
from tts.piper_tts import PiperTTS
from utils.audio import AudioRecorder
from utils.logger import setup_logger

logger = setup_logger("event_loop")
console = Console()


class VoiceEventLoop:
    """
    Ses tabanlı Jarvis döngüsü.

    Akış:
    1. Wake word bekle ("Hey Jarvis")
    2. Kullanıcıyı dinle (VAD ile konuşma algıla)
    3. Sesi metne çevir (Whisper)
    4. Metni işle (Orchestrator — LLM + tool'lar)
    5. Yanıtı seslendir (Piper)
    6. Wake word beklemeye geri dön
    """

    def __init__(self):
        console.print("[dim]Bileşenler yükleniyor...[/dim]")

        self.stt = WhisperSTT()
        self.tts = PiperTTS()
        self.recorder = AudioRecorder()
        self.orchestrator = Orchestrator()
        self.wake_word = WakeWordDetector()

        logger.info("VoiceEventLoop başlatıldı — tüm bileşenler hazır")

    def run(self):
        """Ana ses döngüsü."""
        console.print("\n[bold cyan]Jarvis sesli modda hazır![/bold cyan]")
        console.print("[dim]\"Hey Jarvis\" diyerek başla... (Ctrl+C ile çık)[/dim]\n")

        self._greet()

        while True:
            try:
                # 1. Wake word bekle
                console.print("[dim]\"Hey Jarvis\" diyerek uyandır...[/dim]")
                self.wake_word.wait_for_wakeword()

                # Kısa bir onay sesi / geri bildirim
                console.print("[bold cyan]Evet?[/bold cyan]")

                # 2. Dinle
                console.print("[dim]Dinliyorum...[/dim]")
                audio = self.recorder.listen()

                if audio is None:
                    logger.warning("Ses kaydı başarısız, tekrar bekleniyor")
                    continue

                # 3. Transkribe et
                text = self.stt.transcribe(audio)

                if not text:
                    logger.debug("Transkripsiyon boş, tekrar bekleniyor")
                    continue

                console.print(f"\n[bold green]Sen →[/bold green] {text}")

                # Çıkış komutları
                if self._is_exit_command(text):
                    self._farewell()
                    break

                # Sıfırlama
                if self._is_reset_command(text):
                    self.orchestrator.reset()
                    self.tts.speak("Konuşma geçmişi sıfırlandı.")
                    console.print("[dim]Konuşma geçmişi sıfırlandı.[/dim]")
                    continue

                # 4. İşle
                response = self.orchestrator.process(text)
                console.print(f"\n[bold cyan]Jarvis →[/bold cyan] {response}")

                # 5. Seslendir
                self.tts.speak(response)

            except KeyboardInterrupt:
                self._farewell()
                break
            except Exception as e:
                logger.error("Döngü hatası: %s", e)
                console.print(f"[bold red]Hata:[/bold red] {e}")

    def _greet(self):
        greeting = "Hazırım. Hey Jarvis diyerek beni çağırabilirsin."
        console.print(f"\n[bold cyan]Jarvis →[/bold cyan] {greeting}")
        self.tts.speak(greeting)

    def _farewell(self):
        farewell = "Görüşürüz!"
        console.print(f"\n[bold cyan]Jarvis →[/bold cyan] {farewell}")
        self.tts.speak(farewell)

    def _is_exit_command(self, text):
        normalized = text.strip().lower().rstrip(".,!?")
        exit_phrases = [
            "çık", "kapat", "kapan", "görüşürüz",
            "hoşça kal", "kapat jarvis", "çık jarvis",
            "quit", "exit"
        ]
        return normalized in exit_phrases

    def _is_reset_command(self, text):
        normalized = text.strip().lower().rstrip(".,!?")
        return normalized in ["sıfırla", "reset", "temizle"]